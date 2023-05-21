# -*- coding: utf-8 -*-
#
# Licensed under the terms of the BSD 3-Clause
# (see cdl/LICENSE for details)

"""
DataLab main window
"""

# pylint: disable=invalid-name  # Allows short reference names like x, y, ...

from __future__ import annotations

import functools
import locale
import os
import os.path as osp
import sys
import time
import webbrowser
from typing import TYPE_CHECKING

import numpy as np
import scipy.ndimage as spi
import scipy.signal as sps
from guidata.configtools import get_icon
from guidata.dataset import datatypes as gdt
from guidata.qthelpers import add_actions, create_action, win32_fix_title_bar_background
from guidata.widgets.console import DockableConsole
from guiqwt.builder import make
from guiqwt.plot import CurveWidget, ImageWidget
from qtpy import QtCore as QC
from qtpy import QtGui as QG
from qtpy import QtWidgets as QW
from qtpy.compat import getopenfilenames, getsavefilename

from cdl import __docurl__, __homeurl__, __supporturl__, __version__, env
from cdl.config import (
    APP_DESC,
    APP_NAME,
    DATAPATH,
    IS_FROZEN,
    TEST_SEGFAULT_ERROR,
    Conf,
    _,
)
from cdl.core.gui.actionhandler import ActionCategory
from cdl.core.gui.docks import DockablePlotWidget
from cdl.core.gui.h5io import H5InputOutput
from cdl.core.gui.panel import base, image, macro, signal
from cdl.core.model.image import ImageParam
from cdl.core.model.signal import SignalParam
from cdl.env import execenv
from cdl.plugins import PluginBase, PluginRegistry, discover_plugins
from cdl.remotecontrol import RemoteServer
from cdl.utils import dephash
from cdl.utils import qthelpers as qth
from cdl.utils.misc import go_to_error
from cdl.widgets import instconfviewer, logviewer, status

if TYPE_CHECKING:  # pragma: no cover
    from cdl.core.gui.panel.base import BaseDataPanel
    from cdl.core.gui.panel.image import ImagePanel
    from cdl.core.gui.panel.macro import MacroPanel
    from cdl.core.gui.panel.signal import SignalPanel


def get_htmlhelp():
    """Return HTML Help documentation link adapted to locale, if it exists"""
    if os.name == "nt":
        for suffix in ("_" + locale.getlocale()[0][:2], ""):
            path = osp.join(DATAPATH, f"DataLab{suffix}.chm")
            if osp.isfile(path):
                return path
    return None


def remote_controlled(func):
    """Decorator for remote-controlled methods"""

    @functools.wraps(func)
    def method_wrapper(*args, **kwargs):
        """Decorator wrapper function"""
        win = args[0]  # extracting 'self' from method arguments
        already_busy = not win.ready_flag
        win.ready_flag = False
        try:
            output = func(*args, **kwargs)
        finally:
            if not already_busy:
                win.SIG_READY.emit()
                win.ready_flag = True
            QW.QApplication.processEvents()
        return output

    return method_wrapper


class CDLMainWindow(QW.QMainWindow):
    """DataLab main window"""

    __instance = None

    SIG_READY = QC.Signal()
    SIG_SEND_OBJECT = QC.Signal(object)
    SIG_SEND_OBJECTLIST = QC.Signal(object)

    @staticmethod
    def get_instance(console=None, hide_on_close=False):
        """Return singleton instance"""
        if CDLMainWindow.__instance is None:
            return CDLMainWindow(console, hide_on_close)
        return CDLMainWindow.__instance

    def __init__(self, console=None, hide_on_close=False):
        """Initialize main window"""
        CDLMainWindow.__instance = self
        super().__init__()
        win32_fix_title_bar_background(self)
        self.setObjectName(APP_NAME)
        self.setWindowIcon(get_icon("DataLab.svg"))
        self.__restore_pos_and_size()

        self.ready_flag = True

        self.hide_on_close = hide_on_close
        self.__old_size = None
        self.__memory_warning = False
        self.memorystatus = None

        self.console = None
        self.macropanel: MacroPanel = None

        self.signal_toolbar: QW.QToolBar = None
        self.image_toolbar: QW.QToolBar = None
        self.signalpanel: SignalPanel = None
        self.imagepanel: ImagePanel = None
        self.tabwidget: QW.QTabWidget = None
        self.signal_image_docks = None
        self.h5inputoutput = H5InputOutput(self)

        self.openh5_action: QW.QAction = None
        self.saveh5_action: QW.QAction = None
        self.browseh5_action: QW.QAction = None
        self.quit_action: QW.QAction = None

        self.file_menu: QW.QMenu = None
        self.edit_menu: QW.QMenu = None
        self.operation_menu: QW.QMenu = None
        self.processing_menu: QW.QMenu = None
        self.computing_menu: QW.QMenu = None
        self.plugins_menu: QW.QMenu = None
        self.view_menu: QW.QMenu = None
        self.help_menu: QW.QMenu = None

        self.__is_modified = None
        self.set_modified(False)

        # Starting XML-RPC server thread
        self.remote_server = RemoteServer(self)
        if Conf.main.rpc_server_enabled.get():
            self.remote_server.SIG_SERVER_PORT.connect(self.xmlrpc_server_started)
            self.remote_server.start()

        # Setup actions and menus
        if console is None:
            console = Conf.console.enabled.get()
        self.setup(console)

    # ------API related to XML-RPC remote control
    @staticmethod
    def xmlrpc_server_started(port):
        """XML-RPC server has started, writing comm port in configuration file"""
        Conf.main.rpc_server_port.set(port)

    def __get_current_basedatapanel(self) -> BaseDataPanel:
        """Return the current BaseDataPanel,
        or the signal panel if macro panel is active

        Returns:
            BaseDataPanel: current panel
        """
        panel = self.tabwidget.currentWidget()
        if not isinstance(panel, base.BaseDataPanel):
            panel = self.signalpanel
        return panel

    def __get_specific_panel(self, panel: str | None) -> BaseDataPanel:
        """Return a specific BaseDataPanel.

        Args:
            panel (str | None): panel name (valid values: "signal", "image").
                If None, current panel is used.

        Returns:
            BaseDataPanel: panel

        Raises:
            ValueError: if panel is unknown
        """
        if panel is None:
            return self.__get_current_basedatapanel()
        if panel == "signal":
            return self.signalpanel
        if panel == "image":
            return self.imagepanel
        raise ValueError(f"Unknown panel: {panel}")

    def get_object_titles(self, panel: str | None = None) -> list[str]:
        """Get object (signal/image) list for current panel

        Args:
            panel (str | None): panel name (valid values: "signal", "image").
                If None, current panel is used.

        Returns:
            list[str]: list of object titles

        Raises:
            ValueError: if panel is unknown
        """
        return self.__get_specific_panel(panel).objmodel.get_object_titles()

    def get_object_by_title(
        self, title: str, panel: str | None = None
    ) -> SignalParam | ImageParam:
        """Get object (signal/image) from title

        Args:
            title (str): object
            panel (str | None): panel name (valid values: "signal", "image").
                If None, current panel is used.

        Returns:
            Union[SignalParam, ImageParam]: object

        Raises:
            ValueError: if object not found
            ValueError: if panel is unknown
        """
        return self.__get_specific_panel(panel).objmodel.get_object_by_title(title)

    def get_object(
        self,
        index: int | None = None,
        group_index: int | None = None,
        panel: str | None = None,
    ) -> SignalParam | ImageParam:
        """Get object (signal/image) from index.

        Args:
            index (int): Object index in current panel. Defaults to None.
            group_index (int, optional): Group index. Defaults to None.
            panel (str, optional): Panel name. Defaults to None.

        If `index` is not specified, returns the currently selected object.
        If `group_index` is not specified, return an object from the current group.
        If `panel` is not specified, return an object from the current panel.

        Returns:
            Union[SignalParam, ImageParam]: object

        Raises:
            IndexError: if object not found
        """
        panelw = self.__get_specific_panel(panel)
        if index is None:
            return panelw.objview.get_current_object()
        group_index = 0 if group_index is None else group_index
        return panelw.objmodel.get_object(index, group_index)

    def get_object_uuids(self, panel: str | None = None) -> list[str]:
        """Get object (signal/image) uuid list for current panel

        Args:
            panel (str | None): panel name (valid values: "signal", "image").
                If None, current panel is used.

        Returns:
            list[str]: list of object uuids

        Raises:
            ValueError: if panel is unknown
        """
        return self.__get_specific_panel(panel).objmodel.get_object_ids()

    def get_object_from_uuid(
        self, oid: str, panel: str | None = None
    ) -> SignalParam | ImageParam:
        """Get object (signal/image) from uuid

        Args:
            oid (str): object uuid
            panel (str | None): panel name (valid values: "signal", "image").
                If None, current panel is used.

        Returns:
            Union[SignalParam, ImageParam]: object

        Raises:
            ValueError: if object not found
        """
        return self.__get_specific_panel(panel).objmodel[oid]

    # ------Misc.
    @property
    def panels(self) -> tuple[SignalPanel, ImagePanel, MacroPanel]:
        """Return the tuple of implemented panels (signal, image)

        Returns:
            tuple[SignalPanel, ImagePanel, MacroPanel]: tuple of panels
        """
        return (self.signalpanel, self.imagepanel, self.macropanel)

    def __set_low_memory_state(self, state: bool) -> None:
        """Set memory warning state"""
        self.__memory_warning = state

    def confirm_memory_state(self) -> bool:  # pragma: no cover
        """Check memory warning state and eventually show a warning dialog

        Returns:
            bool: True if memory state is ok
        """
        if not env.execenv.unattended and self.__memory_warning:
            threshold = Conf.main.available_memory_threshold.get()
            answer = QW.QMessageBox.critical(
                self,
                _("Warning"),
                _("Available memory is below %d MB.<br><br>Do you want to continue?")
                % threshold,
                QW.QMessageBox.Yes | QW.QMessageBox.No,
            )
            return answer == QW.QMessageBox.Yes
        return True

    def check_stable_release(self) -> None:  # pragma: no cover
        """Check if this is a stable release"""
        if __version__.replace(".", "").isdigit():
            # This is a stable release
            return
        if "b" in __version__:
            # This is a beta release
            rel = _(
                "This software is in the <b>beta stage</b> of its release cycle. "
                "The focus of beta testing is providing a feature complete "
                "software for users interested in trying new features before "
                "the final release. However, <u>beta software may not behave as "
                "expected and will probably have more bugs or performance issues "
                "than completed software</u>."
            )
        else:
            # This is an alpha release
            rel = _(
                "This software is in the <b>alpha stage</b> of its release cycle. "
                "The focus of alpha testing is providing an incomplete software "
                "for early testing of specific features by users. "
                "Please note that <u>alpha software was not thoroughly tested</u> "
                "by the developer before it is released."
            )
        txtlist = [
            f"<b>{APP_NAME}</b> v{__version__}:",
            "",
            _("<i>This is not a stable release.</i>"),
            "",
            rel,
        ]
        QW.QMessageBox.warning(self, APP_NAME, "<br>".join(txtlist), QW.QMessageBox.Ok)

    def check_dependencies(self) -> None:  # pragma: no cover
        """Check dependencies"""
        if IS_FROZEN or Conf.main.ignore_dependency_check.get():
            # No need to check dependencies if DataLab has been frozen
            return
        try:
            state = dephash.check_dependencies_hash(DATAPATH)
            bad_deps = [name for name in state if not state[name]]
            if not bad_deps:
                # Everything is OK
                return
        except IOError:
            bad_deps = None
        txt0 = _("Non-compliant dependency:")
        if bad_deps is None or len(bad_deps) > 1:
            txt0 = _("Non-compliant dependencies:")
        if bad_deps is None:
            txtlist = [
                _("DataLab has not yet been qualified on your operating system."),
            ]
        else:
            txtlist = [
                "<u>" + txt0 + "</u> " + ", ".join(bad_deps),
                "",
                "",
                _(
                    "At least one dependency does not comply with DataLab "
                    "qualification standard reference (wrong dependency version "
                    "has been installed, or dependency source code has been "
                    "modified, or the application has not yet been qualified "
                    "on your operating system)."
                ),
            ]
        txtlist += [
            "",
            _(
                "This means that the application has not been officially qualified "
                "in this context and may not behave as expected."
            ),
            "",
            _(
                "Please click on the Ignore button "
                "to avoid showing this message at startup."
            ),
        ]
        txt = "<br>".join(txtlist)
        btn = QW.QMessageBox.information(
            self, APP_NAME, txt, QW.QMessageBox.Ok | QW.QMessageBox.Ignore
        )
        Conf.main.ignore_dependency_check.set(btn == QW.QMessageBox.Ignore)

    def check_for_previous_crash(self) -> None:  # pragma: no cover
        """Check for previous crash"""
        if execenv.unattended:
            self.show_log_viewer()
        elif Conf.main.faulthandler_log_available.get(
            False
        ) or Conf.main.traceback_log_available.get(False):
            txt = "<br>".join(
                [
                    logviewer.get_log_prompt_message(),
                    "",
                    _("Do you want to see available log files?"),
                ]
            )
            btns = QW.QMessageBox.StandardButton.Yes | QW.QMessageBox.StandardButton.No
            choice = QW.QMessageBox.warning(self, APP_NAME, txt, btns)
            if choice == QW.QMessageBox.StandardButton.Yes:
                self.show_log_viewer()

    def take_screenshot(self, name: str) -> None:  # pragma: no cover
        """Take main window screenshot"""
        self.memorystatus.set_demo_mode(True)
        qth.grab_save_window(self, f"{name}")
        self.memorystatus.set_demo_mode(False)

    def take_menu_screenshots(self) -> None:  # pragma: no cover
        """Take menu screenshots"""
        for panel in self.panels:
            if isinstance(panel, base.BaseDataPanel):
                self.tabwidget.setCurrentWidget(panel)
                for name in (
                    "file",
                    "edit",
                    "view",
                    "operation",
                    "processing",
                    "computing",
                    "help",
                ):
                    menu = getattr(self, f"{name}_menu")
                    menu.popup(self.pos())
                    qth.grab_save_window(menu, f"{panel.objectName()}_{name}")
                    menu.close()

    # ------GUI setup
    def __restore_pos_and_size(self) -> None:
        """Restore main window position and size from configuration"""
        pos = Conf.main.window_position.get(None)
        if pos is not None:
            posx, posy = pos
            self.move(QC.QPoint(posx, posy))
        size = Conf.main.window_size.get(None)
        if size is not None:
            width, height = size
            self.resize(QC.QSize(width, height))
        if pos is not None and size is not None:
            sgeo = self.screen().availableGeometry()
            out_inf = posx < -int(0.9 * width) or posy < -int(0.9 * height)
            out_sup = posx > int(0.9 * sgeo.width()) or posy > int(0.9 * sgeo.height())
            if len(QW.QApplication.screens()) == 1 and (out_inf or out_sup):
                #  Main window is offscreen
                posx = min(max(posx, 0), sgeo.width() - width)
                posy = min(max(posy, 0), sgeo.height() - height)
                self.move(QC.QPoint(posx, posy))

    def __save_pos_and_size(self) -> None:
        """Save main window position and size to configuration"""
        is_maximized = self.windowState() == QC.Qt.WindowMaximized
        Conf.main.window_maximized.set(is_maximized)
        if not is_maximized:
            size = self.size()
            Conf.main.window_size.set((size.width(), size.height()))
            pos = self.pos()
            Conf.main.window_position.set((pos.x(), pos.y()))

    def setup(self, console: bool = False) -> None:
        """Setup main window

        Args:
            console: True to setup console
        """
        self.__register_plugins()
        self.__configure_statusbar()
        self.__setup_commmon_actions()
        self.__add_signal_image_panels()
        self.__create_plugins_actions()
        self.__setup_central_widget()
        self.__add_menus()
        if console:
            self.__setup_console()
        self.__update_actions()
        self.__add_macro_panel()
        self.__configure_panels()

    def __register_plugins(self) -> None:
        """Register plugins"""
        with qth.try_or_log_error("Discovering plugins"):
            # Discovering plugins
            discover_plugins()
        for plugin_class in PluginRegistry.get_plugin_classes():
            with qth.try_or_log_error(f"Instantiating plugin {plugin_class.__name__}"):
                # Instantiating plugin
                plugin: PluginBase = plugin_class()
            with qth.try_or_log_error(f"Registering plugin {plugin.info.name}"):
                # Registering plugin
                plugin.register(self)

    def __create_plugins_actions(self) -> None:
        """Create plugins actions"""
        with self.signalpanel.acthandler.new_category(ActionCategory.PLUGINS):
            with self.imagepanel.acthandler.new_category(ActionCategory.PLUGINS):
                for plugin in PluginRegistry.get_plugins():
                    with qth.try_or_log_error(f"Create actions for {plugin.info.name}"):
                        plugin.create_actions()

    @staticmethod
    def __unregister_plugins() -> None:
        """Unregister plugins"""
        for plugin in PluginRegistry.get_plugins():
            # Unregistering plugin
            with qth.try_or_log_error(f"Unregistering plugin {plugin.info.name}"):
                plugin.unregister()

    def __configure_statusbar(self) -> None:
        """Configure status bar"""
        self.statusBar().showMessage(_("Welcome to %s!") % APP_NAME, 5000)
        threshold = Conf.main.available_memory_threshold.get()
        self.memorystatus = status.MemoryStatus(threshold)
        self.memorystatus.SIG_MEMORY_ALARM.connect(self.__set_low_memory_state)
        self.statusBar().addPermanentWidget(self.memorystatus)

    def __setup_commmon_actions(self) -> None:
        """Setup common actions"""
        self.openh5_action = create_action(
            self,
            _("Open HDF5 files..."),
            icon=get_icon("h5open.svg"),
            tip=_("Open one or several HDF5 files"),
            triggered=lambda checked=False: self.open_h5_files(import_all=True),
        )
        self.saveh5_action = create_action(
            self,
            _("Save to HDF5 file..."),
            icon=get_icon("h5save.svg"),
            tip=_("Save to HDF5 file"),
            triggered=self.save_to_h5_file,
        )
        self.browseh5_action = create_action(
            self,
            _("Browse HDF5 file..."),
            icon=get_icon("h5browser.svg"),
            tip=_("Browse an HDF5 file"),
            triggered=lambda checked=False: self.open_h5_files(import_all=None),
        )
        h5_toolbar = self.addToolBar(_("HDF5 I/O Toolbar"))
        add_actions(
            h5_toolbar, [self.openh5_action, self.saveh5_action, self.browseh5_action]
        )
        # Quit action for "File menu" (added when populating menu on demand)
        if self.hide_on_close:
            quit_text = _("Hide window")
            quit_tip = _("Hide DataLab window")
        else:
            quit_text = _("Quit")
            quit_tip = _("Quit application")
        self.quit_action = create_action(
            self,
            quit_text,
            shortcut=QG.QKeySequence(QG.QKeySequence.Quit),
            icon=get_icon("libre-gui-close.svg"),
            tip=quit_tip,
            triggered=self.close,
        )

    def __add_signal_panel(self) -> None:
        """Setup signal toolbar, widgets and panel"""
        self.signal_toolbar = self.addToolBar(_("Signal Processing Toolbar"))
        curveplot_toolbar = self.addToolBar(_("Curve Plotting Toolbar"))
        curvewidget = DockablePlotWidget(self, CurveWidget, curveplot_toolbar)
        curveplot = curvewidget.get_plot()
        curveplot.add_item(make.legend("TR"))
        self.signalpanel = signal.SignalPanel(
            self, curvewidget.plotwidget, self.signal_toolbar
        )
        self.signalpanel.SIG_STATUS_MESSAGE.connect(self.statusBar().showMessage)
        return curvewidget

    def __add_image_panel(self) -> None:
        """Setup image toolbar, widgets and panel"""
        self.image_toolbar = self.addToolBar(_("Image Processing Toolbar"))
        imagevis_toolbar = self.addToolBar(_("Image Visualization Toolbar"))
        imagewidget = DockablePlotWidget(self, ImageWidget, imagevis_toolbar)
        self.imagepanel = image.ImagePanel(
            self, imagewidget.plotwidget, self.image_toolbar
        )
        # -----------------------------------------------------------------------------
        # # Before eventually disabling the "peritem" mode by default, wait for the
        # # guiqwt bug to be fixed (peritem mode is not compatible with multiple image
        # # items):
        # for cspanel in (
        #     self.imagepanel.plotwidget.get_xcs_panel(),
        #     self.imagepanel.plotwidget.get_ycs_panel(),
        # ):
        #     cspanel.peritem_ac.setChecked(False)
        # -----------------------------------------------------------------------------
        self.imagepanel.SIG_STATUS_MESSAGE.connect(self.statusBar().showMessage)
        return imagewidget

    def __add_signal_image_panels(self) -> None:
        """Add signal and image panels"""
        self.tabwidget = QW.QTabWidget()
        cdock = self.__add_dockwidget(self.__add_signal_panel(), title=_("Curve panel"))
        idock = self.__add_dockwidget(self.__add_image_panel(), title=_("Image panel"))
        self.tabifyDockWidget(cdock, idock)
        self.signal_image_docks = cdock, idock
        self.tabwidget.currentChanged.connect(self.__tab_index_changed)
        self.signalpanel.SIG_OBJECT_ADDED.connect(
            lambda: self.switch_to_panel("signal")
        )
        self.imagepanel.SIG_OBJECT_ADDED.connect(lambda: self.switch_to_panel("image"))
        for panel in (self.signalpanel, self.imagepanel):
            panel.setup_panel()

    def __setup_central_widget(self) -> None:
        """Setup central widget (main panel)"""
        self.tabwidget.setMaximumWidth(500)
        self.tabwidget.addTab(self.signalpanel, get_icon("signal.svg"), _("Signals"))
        self.tabwidget.addTab(self.imagepanel, get_icon("image.svg"), _("Images"))
        self.setCentralWidget(self.tabwidget)

    def __add_menus(self) -> None:
        """Adding menus"""
        self.file_menu = self.menuBar().addMenu(_("File"))
        self.file_menu.aboutToShow.connect(self.__update_file_menu)
        self.edit_menu = self.menuBar().addMenu(_("&Edit"))
        self.operation_menu = self.menuBar().addMenu(_("Operations"))
        self.processing_menu = self.menuBar().addMenu(_("Processing"))
        self.computing_menu = self.menuBar().addMenu(_("Computing"))
        self.plugins_menu = self.menuBar().addMenu(_("Plugins"))
        self.view_menu = self.menuBar().addMenu(_("&View"))
        self.view_menu.aboutToShow.connect(self.__update_view_menu)
        self.help_menu = self.menuBar().addMenu("?")
        for menu in (
            self.edit_menu,
            self.operation_menu,
            self.processing_menu,
            self.computing_menu,
            self.plugins_menu,
        ):
            menu.aboutToShow.connect(self.__update_generic_menu)
        about_action = create_action(
            self,
            _("About..."),
            icon=get_icon("libre-gui-about.svg"),
            triggered=self.__about,
        )
        homepage_action = create_action(
            self,
            _("Project home page"),
            icon=get_icon("libre-gui-globe.svg"),
            triggered=lambda: webbrowser.open(__homeurl__),
        )
        issue_action = create_action(
            self,
            _("Bug report or feature request"),
            icon=get_icon("libre-gui-globe.svg"),
            triggered=lambda: webbrowser.open(__supporturl__),
        )
        onlinedoc_action = create_action(
            self,
            _("Online documentation"),
            icon=get_icon("libre-gui-help.svg"),
            triggered=lambda: webbrowser.open(__docurl__),
        )
        chmdoc_action = create_action(
            self,
            _("CHM documentation"),
            icon=get_icon("chm.svg"),
            triggered=lambda: os.startfile(get_htmlhelp()),
        )
        chmdoc_action.setVisible(get_htmlhelp() is not None)
        logv_action = create_action(
            self,
            _("Show log files..."),
            icon=get_icon("logs.svg"),
            triggered=self.show_log_viewer,
        )
        dep_action = create_action(
            self,
            _("About DataLab installation") + "...",
            icon=get_icon("logs.svg"),
            triggered=lambda: instconfviewer.exec_cdl_installconfig_dialog(self),
        )
        errtest_action = create_action(
            self, "Test segfault/Python error", triggered=self.test_segfault_error
        )
        errtest_action.setVisible(TEST_SEGFAULT_ERROR)
        about_action = create_action(
            self,
            _("About..."),
            icon=get_icon("libre-gui-about.svg"),
            triggered=self.__about,
        )
        add_actions(
            self.help_menu,
            (
                onlinedoc_action,
                chmdoc_action,
                None,
                errtest_action,
                logv_action,
                dep_action,
                None,
                homepage_action,
                issue_action,
                about_action,
            ),
        )

    def __setup_console(self) -> None:
        """Add an internal console"""
        ns = {
            "cdl": self,
            "np": np,
            "sps": sps,
            "spi": spi,
            "os": os,
            "sys": sys,
            "osp": osp,
            "time": time,
        }
        msg = (
            "Welcome to DataLab console!\n"
            "---------------------------\n"
            "You can access the main window with the 'cdl' variable.\n"
            "Example:\n"
            "  o = cdl.get_object()  # returns currently selected object\n"
            "  o.data  # returns object data\n"
            "Modules imported at startup: "
            "os, sys, os.path as osp, time, "
            "numpy as np, scipy.signal as sps, scipy.ndimage as spi"
        )
        debug = os.environ.get("DEBUG") == "1"
        self.console = DockableConsole(self, namespace=ns, message=msg, debug=debug)
        self.console.setMaximumBlockCount(Conf.console.max_line_count.get(5000))
        self.console.go_to_error.connect(go_to_error)
        console_dock = self.__add_dockwidget(self.console, _("Console"))
        console_dock.hide()
        self.console.interpreter.widget_proxy.sig_new_prompt.connect(
            lambda txt: self.repopulate_panel_trees()
        )

    def __add_macro_panel(self) -> None:
        """Add macro panel"""
        self.macropanel = macro.MacroPanel()
        macrodock = self.__add_dockwidget(self.macropanel, _("Macro manager"))
        self.tabifyDockWidget(self.signal_image_docks[1], macrodock)
        self.signal_image_docks[0].raise_()

    def __configure_panels(self) -> None:
        """Configure panels"""
        for panel in self.panels:
            panel.SIG_OBJECT_ADDED.connect(self.set_modified)
            panel.SIG_OBJECT_REMOVED.connect(self.set_modified)
        self.macropanel.SIG_OBJECT_MODIFIED.connect(self.set_modified)
        # Restoring current tab from last session
        tab_idx = Conf.main.current_tab.get(None)
        if tab_idx is not None:
            self.tabwidget.setCurrentIndex(tab_idx)

    # ------Remote control
    @remote_controlled
    def switch_to_panel(self, panel: str) -> None:
        """Switch to panel.

        Args:
            panel (str): panel name (valid values: "signal", "image", "macro")

        Raises:
            ValueError: unknown panel
        """
        if panel == "signal":
            self.tabwidget.setCurrentWidget(self.signalpanel)
        elif panel == "image":
            self.tabwidget.setCurrentWidget(self.imagepanel)
        elif panel == "macro":
            self.tabwidget.setCurrentWidget(self.macropanel)
        else:
            raise ValueError(f"Unknown panel {panel}")

    @remote_controlled
    def calc(self, name: str, param: gdt.DataSet | None = None) -> None:
        """Call compute function `name` in current panel's processor

        Args:
            name (str): function name
            param (DataSet): optional parameters (default: None)

        Raises:
            ValueError: unknown function
        """
        panel = self.tabwidget.currentWidget()
        for funcname in (name, f"compute_{name}"):
            func = getattr(panel.processor, funcname, None)
            if func is not None:
                break
        else:
            raise ValueError(f"Unknown function {funcname}")
        if param is None:
            func()
        else:
            func(param)

    # ------GUI refresh
    def has_objects(self) -> bool:
        """Return True if sig/ima panels have any object"""
        return sum([panel.object_number for panel in self.panels]) > 0

    def set_modified(self, state: bool = True) -> None:
        """Set mainwindow modified state"""
        state = state and self.has_objects()
        self.__is_modified = state
        self.setWindowTitle(APP_NAME + ("*" if state else ""))

    def __add_dockwidget(self, child, title: str) -> QW.QDockWidget:
        """Add QDockWidget and toggleViewAction"""
        dockwidget, location = child.create_dockwidget(title)
        self.addDockWidget(location, dockwidget)
        return dockwidget

    def repopulate_panel_trees(self) -> None:
        """Repopulate all panel trees"""
        for panel in self.panels:
            if isinstance(panel, base.BaseDataPanel):
                panel.objview.populate_tree()

    def __update_actions(self) -> None:
        """Update selection dependent actions"""
        is_signal = self.tabwidget.currentWidget() is self.signalpanel
        panel = self.signalpanel if is_signal else self.imagepanel
        panel.selection_changed()
        self.signal_toolbar.setVisible(is_signal)
        self.image_toolbar.setVisible(not is_signal)
        if self.plugins_menu is not None:
            plugin_actions = panel.get_category_actions(ActionCategory.PLUGINS)
            self.plugins_menu.setEnabled(len(plugin_actions) > 0)

    def __tab_index_changed(self, index: int) -> None:
        """Switch from signal to image mode, or vice-versa"""
        dock = self.signal_image_docks[index]
        dock.raise_()
        self.__update_actions()

    def __update_generic_menu(self, menu: QW.QMenu | None = None) -> None:
        """Update menu before showing up -- Generic method"""
        if menu is None:
            menu = self.sender()
        menu.clear()
        panel = self.tabwidget.currentWidget()
        category = {
            self.file_menu: ActionCategory.FILE,
            self.edit_menu: ActionCategory.EDIT,
            self.view_menu: ActionCategory.VIEW,
            self.operation_menu: ActionCategory.OPERATION,
            self.processing_menu: ActionCategory.PROCESSING,
            self.computing_menu: ActionCategory.COMPUTING,
            self.plugins_menu: ActionCategory.PLUGINS,
        }[menu]
        actions = panel.get_category_actions(category)
        add_actions(menu, actions)

    def __update_file_menu(self) -> None:
        """Update file menu before showing up"""
        self.saveh5_action.setEnabled(self.has_objects())
        self.__update_generic_menu(self.file_menu)
        add_actions(
            self.file_menu,
            [
                None,
                self.openh5_action,
                self.saveh5_action,
                self.browseh5_action,
                None,
                self.quit_action,
            ],
        )

    def __update_view_menu(self) -> None:
        """Update view menu before showing up"""
        self.__update_generic_menu(self.view_menu)
        add_actions(self.view_menu, [None] + self.createPopupMenu().actions())

    # ------Common features
    @remote_controlled
    def reset_all(self) -> None:
        """Reset all application data"""
        for panel in self.panels:
            panel.remove_all_objects()

    @staticmethod
    def __check_h5file(filename: str, operation: str) -> str:
        """Check HDF5 filename"""
        filename = osp.abspath(osp.normpath(filename))
        bname = osp.basename(filename)
        if operation == "load" and not osp.isfile(filename):
            raise IOError(f'File not found "{bname}"')
        if not filename.endswith(".h5"):
            raise IOError(f'Invalid HDF5 file "{bname}"')
        Conf.main.base_dir.set(filename)
        return filename

    @remote_controlled
    def save_to_h5_file(self, filename=None) -> None:
        """Save to a DataLab HDF5 file

        Args:
            filename (str): HDF5 filename. If None, a file dialog is opened.

        Raises:
            IOError: if filename is invalid or file cannot be saved.
        """
        if filename is None:
            basedir = Conf.main.base_dir.get()
            with qth.save_restore_stds():
                filters = f'{_("HDF5 files")} (*.h5)'
                filename, _filter = getsavefilename(self, _("Save"), basedir, filters)
            if not filename:
                return
        with qth.qt_try_loadsave_file(self, filename, "save"):
            filename = self.__check_h5file(filename, "save")
            self.h5inputoutput.save_file(filename)
            self.set_modified(False)

    @remote_controlled
    def open_h5_files(
        self,
        h5files: list[str] | None = None,
        import_all: bool | None = None,
        reset_all: bool | None = None,
    ) -> None:
        """Open a DataLab HDF5 file or import from any other HDF5 file.

        Args:
            h5files: HDF5 filenames (optionally with dataset name, separated by ":")
            import_all (bool): Import all datasets from HDF5 files
            reset_all (bool): Reset all application data before importing

        Returns:
            None
        """
        if not self.confirm_memory_state():
            return
        if reset_all is None:
            reset_all = False
            if self.has_objects():
                answer = QW.QMessageBox.question(
                    self,
                    _("Warning"),
                    _(
                        "Do you want to remove all signals and images "
                        "before importing data from HDF5 files?"
                    ),
                    QW.QMessageBox.Yes | QW.QMessageBox.No,
                )
                if answer == QW.QMessageBox.Yes:
                    reset_all = True
        if h5files is None:
            basedir = Conf.main.base_dir.get()
            with qth.save_restore_stds():
                filters = f'{_("HDF5 files")} (*.h5)'
                h5files, _filter = getopenfilenames(self, _("Open"), basedir, filters)
        for fname_with_dset in h5files:
            if "," in fname_with_dset:
                filename, dsetname = fname_with_dset.split(",")
            else:
                filename, dsetname = fname_with_dset, None
            if import_all is None and dsetname is None:
                self.import_h5_file(filename, reset_all)
            else:
                with qth.qt_try_loadsave_file(self, filename, "load"):
                    filename = self.__check_h5file(filename, "load")
                    if dsetname is None:
                        self.h5inputoutput.open_file(filename, import_all, reset_all)
                    else:
                        self.h5inputoutput.import_dataset_from_file(filename, dsetname)
            reset_all = False

    @remote_controlled
    def import_h5_file(self, filename: str, reset_all: bool | None = None) -> None:
        """Import HDF5 file into DataLab

        Args:
            filename (str): HDF5 filename (optionally with dataset name,
            separated by ":")
            reset_all (bool): Delete all DataLab signals/images before importing data

        Returns:
            None
        """
        with qth.qt_try_loadsave_file(self, filename, "load"):
            filename = self.__check_h5file(filename, "load")
            self.h5inputoutput.import_file(filename, False, reset_all)

    @remote_controlled
    def add_object(self, obj: SignalParam | ImageParam) -> None:
        """Add object - signal or image

        Args:
            obj (SignalParam or ImageParam): object to add (signal or image)

        Returns:
            None
        """
        if self.confirm_memory_state():
            if isinstance(obj, SignalParam):
                self.signalpanel.add_object(obj)
            elif isinstance(obj, ImageParam):
                self.imagepanel.add_object(obj)
            else:
                raise TypeError(f"Unsupported object type {type(obj)}")

    @remote_controlled
    def open_object(self, filename: str) -> None:
        """Open object from file in current panel (signal/image)

        Args:
            filename (str): HDF5 filename

        Returns:
            None
        """
        panel = self.tabwidget.currentWidget()
        panel.open_object(filename)

    # ------?
    def __about(self) -> None:  # pragma: no cover
        """About dialog box"""
        self.check_stable_release()
        if self.remote_server.port is None:
            xrpcstate = f'<font color="red">{_("not started")}</font>'
        else:
            xrpcstate = _("started (port %s)") % self.remote_server.port
            xrpcstate = f"<font color='green'>{xrpcstate}</font>"
        if Conf.main.process_isolation_enabled.get():
            pistate = f"<font color='green'>{_('enabled')}</font>"
        else:
            pistate = f"<font color='red'>{_('disabled')}</font>"
        adv_conf = "<br>".join(
            [
                "<i>" + _("Advanced configuration:") + "</i>",
                "• " + _("XML-RPC server:") + " " + xrpcstate,
                "• " + _("Process isolation:") + " " + pistate,
            ]
        )
        pinfos = PluginRegistry.get_plugin_infos()
        created_by = _("Created by")
        dev_by = _("Developed and maintained by %s open-source project team") % APP_NAME
        cpyright = "2023 CEA, Codra"
        QW.QMessageBox.about(
            self,
            _("About") + " " + APP_NAME,
            f"""<b>{APP_NAME}</b> v{__version__}<br>{APP_DESC}
              <p>{created_by} Pierre Raybaut<br>{dev_by}<br>Copyright &copy; {cpyright}
              <p>{adv_conf}<br><br>{pinfos}""",
        )

    def show_log_viewer(self) -> None:
        """Show error logs"""
        logviewer.exec_cdl_logviewer_dialog(self)

    @staticmethod
    def test_segfault_error() -> None:
        """Generate errors (both fault and traceback)"""
        import ctypes  # pylint: disable=import-outside-toplevel

        ctypes.string_at(0)
        raise RuntimeError("!!! Testing RuntimeError !!!")

    def show(self) -> None:
        """Reimplement QMainWindow method"""
        super().show()
        if self.__old_size is not None:
            self.resize(self.__old_size)

    # ------Close window
    def closeEvent(self, event):
        """Reimplement QMainWindow method"""
        if self.hide_on_close:
            self.__old_size = self.size()
            self.hide()
        else:
            if not env.execenv.unattended and self.__is_modified:
                answer = QW.QMessageBox.warning(
                    self,
                    _("Quit"),
                    _(
                        "Do you want to save all signals and images "
                        "to an HDF5 file before quitting DataLab?"
                    ),
                    QW.QMessageBox.Yes | QW.QMessageBox.No | QW.QMessageBox.Cancel,
                )
                if answer == QW.QMessageBox.Yes:
                    self.save_to_h5_file()
                    if self.__is_modified:
                        event.ignore()
                        return
                elif answer == QW.QMessageBox.Cancel:
                    event.ignore()
                    return
            for panel in self.panels:
                panel.close()
            if self.console is not None:
                try:
                    self.console.close()
                except RuntimeError:
                    # TODO: [P3] Investigate further why the following error occurs when
                    # restarting the mainwindow (this is *not* a production case):
                    # "RuntimeError: wrapped C/C++ object of type DockableConsole
                    #  has been deleted".
                    # Another solution to avoid this error would be to really restart
                    # the application (run each unit test in a separate process), but
                    # it would represent too much effort for an error occuring in test
                    # configurations only.
                    pass
            self.reset_all()
            self.__save_pos_and_size()
            self.__unregister_plugins()

            # Saving current tab for next session
            Conf.main.current_tab.set(self.tabwidget.currentIndex())

            event.accept()
