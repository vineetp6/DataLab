# -*- coding: utf-8 -*-
#
# Licensed under the terms of the BSD 3-Clause
# (see cdl/LICENSE for details)

"""
DataLab plugin system
"""

from __future__ import annotations

import abc
import dataclasses
import importlib
import os
import os.path as osp
import pkgutil
import sys
from typing import TYPE_CHECKING

from qtpy import QtWidgets as QW

from cdl.config import MOD_NAME, Conf, _

if TYPE_CHECKING:  # pragma: no cover
    from cdl.core.gui import main
    from cdl.core.gui.panel.image import ImagePanel
    from cdl.core.gui.panel.signal import SignalPanel


PLUGIN_PYTHONPATH = Conf.get_path("plugins")

if not osp.isdir(PLUGIN_PYTHONPATH):
    os.makedirs(PLUGIN_PYTHONPATH)

sys.path.append(PLUGIN_PYTHONPATH)


class PluginRegistry(type):
    """Metaclass for registering plugins"""

    _plugin_classes: list[PluginBase] = []
    _plugin_instances: list[PluginBase] = []

    def __init__(cls, name, bases, attrs):
        super().__init__(name, bases, attrs)
        if name != "PluginBase":
            cls._plugin_classes.append(cls)

    @classmethod
    def get_plugin_classes(cls) -> list[PluginBase]:
        """Return plugin classes"""
        return cls._plugin_classes

    @classmethod
    def get_plugins(cls) -> list[PluginBase]:
        """Return plugin instances"""
        return cls._plugin_instances

    @classmethod
    def get_plugin(cls, name_or_class) -> PluginBase | None:
        """Return plugin instance"""
        for plugin in cls._plugin_instances:
            if name_or_class in (plugin.info.name, plugin.__class__):
                return plugin
        return None

    @classmethod
    def register_plugin(cls, plugin: PluginBase):
        """Register plugin"""
        if plugin.info.name in [plug.info.name for plug in cls._plugin_instances]:
            raise ValueError(f"Plugin {plugin.info.name} already registered")
        cls._plugin_instances.append(plugin)

    @classmethod
    def unregister_plugin(cls, plugin: PluginBase):
        """Unregister plugin"""
        cls._plugin_instances.remove(plugin)

    @classmethod
    def get_plugin_infos(cls) -> str:
        """Return plugin infos (names, versions, descriptions) in html format"""
        plugins = cls.get_plugins()
        if plugins:
            html = "<i>" + _("Registered plugins:") + "</i><br>"
            for plugin in plugins:
                html += f"• {plugin.info.name} ({plugin.info.version})"
                if plugin.info.description:
                    html += f": {plugin.info.description}"
                html += "<br>"
        else:
            html = "<i>" + _("No plugins available") + "</i>"
        return html


@dataclasses.dataclass
class PluginInfo:
    """Plugin info"""

    name: str = None
    version: str = "0.0.0"
    description: str = ""
    icon: str = None


class PluginBaseMeta(PluginRegistry, abc.ABCMeta):
    """Mixed metaclass to avoid conflicts"""


class PluginBase(abc.ABC, metaclass=PluginBaseMeta):
    """Plugin base class"""

    PLUGIN_INFO: PluginInfo = None

    def __init__(self):
        self.main: main.CDLMainWindow = None
        self._is_registered = False
        self.info = self.PLUGIN_INFO
        if self.info is None:
            raise ValueError(f"Plugin info not set for {self.__class__.__name__}")

    @property
    def signalpanel(self) -> SignalPanel:
        """Return signal panel"""
        return self.main.signalpanel

    @property
    def imagepanel(self) -> ImagePanel:
        """Return image panel"""
        return self.main.imagepanel

    def show_warning(self, message: str):
        """Show warning message"""
        QW.QMessageBox.warning(self.main, _("Warning"), message)

    def show_error(self, message: str):
        """Show error message"""
        QW.QMessageBox.critical(self.main, _("Error"), message)

    def show_info(self, message: str):
        """Show info message"""
        QW.QMessageBox.information(self.main, _("Information"), message)

    def ask_yesno(
        self, message: str, title: str | None = None, cancelable: bool = False
    ) -> bool:
        """Ask yes/no question"""
        if title is None:
            title = _("Question")
        buttons = QW.QMessageBox.Yes | QW.QMessageBox.No
        if cancelable:
            buttons |= QW.QMessageBox.Cancel
        answer = QW.QMessageBox.question(self.main, title, message, buttons)
        if answer == QW.QMessageBox.Yes:
            return True
        if answer == QW.QMessageBox.No:
            return False
        return None

    def is_registered(self):
        """Return True if plugin is registered"""
        return self._is_registered

    def register(self, main: main.CDLMainWindow) -> None:
        """Register plugin"""
        if self._is_registered:
            return
        PluginRegistry.register_plugin(self)
        self._is_registered = True
        self.main = main
        self.register_hooks()

    def unregister(self):
        """Unregister plugin"""
        if not self._is_registered:
            return
        PluginRegistry.unregister_plugin(self)
        self._is_registered = False
        self.unregister_hooks()

    def register_hooks(self):
        """Register plugin hooks"""

    def unregister_hooks(self):
        """Unregister plugin hooks"""

    @abc.abstractmethod
    def create_actions(self):
        """Create actions"""


def discover_plugins() -> list[PluginBase]:
    """Discover plugins using naming convention"""
    return [
        importlib.import_module(name)
        for _finder, name, _ispkg in pkgutil.iter_modules()
        if name.startswith(f"{MOD_NAME}_")
    ]
