# Copyright (c) DataLab Platform Developers, BSD 3-Clause license, see LICENSE file.

"""
Configuration test

Checking .ini configuration file management.
"""

# guitest: show

import os
import os.path as osp

from qtpy import QtCore as QC
from qtpy import QtWidgets as QW

from cdl import app
from cdl.config import Conf
from cdl.env import execenv
from cdl.utils.conf import CONF
from cdl.utils.qthelpers import cdl_app_context
from cdl.utils.tests import get_test_fnames

SEC_MAIN = Conf.main
OPT_MAX = SEC_MAIN.window_maximized
OPT_POS = SEC_MAIN.window_position
OPT_SIZ = SEC_MAIN.window_size
OPT_DIR = SEC_MAIN.base_dir

SEC_CONS = Conf.console
OPT_CON = SEC_CONS.console_enabled

CONFIGS = (
    {
        SEC_MAIN.get_name(): {
            OPT_MAX.option: False,
            OPT_POS.option: (250, 250),
            OPT_SIZ.option: (1300, 700),
            OPT_DIR.option: "",
        },
        SEC_CONS.get_name(): {
            OPT_CON.option: False,
        },
    },
    {
        SEC_MAIN.get_name(): {
            OPT_MAX.option: False,
            OPT_POS.option: (100, 100),
            OPT_SIZ.option: (750, 600),
            OPT_DIR.option: osp.dirname(__file__),
        },
        SEC_CONS.get_name(): {
            OPT_CON.option: False,
        },
    },
    {
        SEC_MAIN.get_name(): {
            OPT_MAX.option: True,
            OPT_POS.option: (10, 10),
            OPT_SIZ.option: (750, 600),
            OPT_DIR.option: "",
        },
        SEC_CONS.get_name(): {
            OPT_CON.option: True,
        },
    },
)


def apply_conf(conf, name):
    """Apply configuration"""
    execenv.print(f"  Applying configuration {name}:")
    fname = CONF.filename()
    try:
        os.remove(fname)
        execenv.print(f"    Removed configuration file {fname}")
    except FileNotFoundError:
        execenv.print(f"    Configuration file {fname} was not found")
    for section, settings in conf.items():
        for option, value in settings.items():
            execenv.print(f"    Writing [{section}][{option}] = {value}")
            CONF.set(section, option, value)
    CONF.save()


def assert_in_interval(val1, val2, interval, context):
    """Raise an AssertionError if val1 is in [val2-interval/2,val2+interval/2]"""
    itv1, itv2 = val2 - 0.5 * interval, val2 + 0.5 * interval
    try:
        assert itv1 <= val1 <= itv2
    except AssertionError as exc:
        if os.name == "posix" and "WSL" in os.uname().release:
            # Ignore if executing the test on WSL: position of windows is not reliable
            # on WSL (e.g. Gnome) and the test will fail
            pass
        else:
            raise AssertionError(f"{context}: {itv1} <= {val1} <= {itv2}") from exc


def check_conf(conf, name, win: QW.QMainWindow, h5files):
    """Check configuration"""
    execenv.print(f"  Checking configuration {name}: ")
    sec_main_name = SEC_MAIN.get_name()
    sec_cons_name = SEC_CONS.get_name()
    sec_main = conf[sec_main_name]
    sec_cons = conf[sec_cons_name]
    execenv.print(f"    Checking [{sec_main_name}][{OPT_MAX.option}]: ", end="")
    assert sec_main[OPT_MAX.option] == (
        win.windowState() == QC.Qt.WindowState.WindowMaximized
    )
    execenv.print("OK")
    execenv.print(f"    Checking [{sec_main_name}][{OPT_POS.option}]: ", end="")
    if not sec_main[OPT_MAX.option]:  # Check position/size only when not maximized
        #  Check position, taking into account screen offset (e.g. Linux/Gnome)
        conf_x, conf_y = sec_main[OPT_POS.option]
        conf_w, conf_h = sec_main[OPT_SIZ.option]
        available_go = QW.QDesktopWidget().availableGeometry()
        x_offset, y_offset = available_go.x(), available_go.y()
        assert_in_interval(win.x(), conf_x - x_offset, 0, "X position")
        assert_in_interval(win.y(), conf_y - y_offset / 2, 15 + y_offset, "Y position")
        #  Check size
        assert_in_interval(win.width(), conf_w, 5, "Width")
        assert_in_interval(win.height(), conf_h, 5, "Height")
        execenv.print(f"OK {win.x(), win.y(), win.width(), win.height()}")
    else:
        execenv.print("Passed (maximized)")
    execenv.print(f"    Checking [{sec_cons_name}][{OPT_CON.option}]: ", end="")
    assert sec_cons[OPT_CON.option] == (win.console is not None)
    execenv.print("OK")
    execenv.print(f"    Checking [{sec_main_name}][{OPT_DIR.option}]: ", end="")
    if h5files is None:
        assert conf[SEC_MAIN.get_name()][OPT_DIR.option] == OPT_DIR.get()
        execenv.print("OK (written in conf file)")
    else:
        assert OPT_DIR.get() == osp.dirname(h5files[0])
        execenv.print("OK (changed to HDF5 file path)")


def test_config():
    """Testing DataLab configuration file"""
    with execenv.context(unattended=True):
        h5files = [get_test_fnames("*.h5")[1]]
        execenv.print("Testing DataLab configuration settings:")
        for index, conf in enumerate(CONFIGS):
            name = f"CONFIG{index}"
            apply_conf(conf, name)
            with cdl_app_context(exec_loop=True) as qapp:
                win = app.create(splash=False, h5files=h5files)
                qapp.processEvents()
                check_conf(conf, name, win, h5files)
            h5files = None
        execenv.print("=> Everything is OK")


if __name__ == "__main__":
    test_config()
