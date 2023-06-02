# -*- coding: utf-8 -*-
#
# Licensed under the terms of the BSD 3-Clause
# (see cdl/LICENSE for details)

"""
Application test for main window
--------------------------------

Testing the features of the main window of the application that are not
covered by other tests.
"""

import os

from cdl.env import execenv
from cdl.param import MovingMedianParam
from cdl.tests import cdl_app_context
from cdl.tests.data import create_test_signal1

SHOW = False  # Show test in GUI-based test launcher


def test():
    """Dictionnary/List in metadata (de)serialization test"""
    with cdl_app_context(console=False) as win:
        # Switch from panel to panel
        for panelname in ("macro", "image", "signal"):
            win.switch_to_panel(panelname)
        # Switch to an unknown panel
        try:
            win.switch_to_panel("unknown_panel")
            raise RuntimeError("Unknown panel should have raised an exception")
        except ValueError:
            pass

        # Add signals to signal panel
        panel = win.signalpanel
        sig1 = create_test_signal1(500)
        panel.add_object(sig1)
        panel.processor.compute_derivative()
        panel.processor.compute_wiener()

        # Get object titles
        titles = win.get_object_titles()
        execenv.print(f"Object titles:{os.linesep}{titles}")

        # Get object uuids
        uuids = win.get_object_uuids()
        execenv.print(f"Object uuids:{os.linesep}{uuids}")

        # Get object from title
        obj = win.get_object_from_title(titles[-1])
        execenv.print(f"Object (from title) '{obj.short_id}':{os.linesep}{obj}")

        # Get object
        obj = win.get_object(0)
        execenv.print(f"Object (from pos.)  '{obj.short_id}':{os.linesep}{obj}")

        # Get object by uuid
        obj = win.get_object_from_uuid(uuids[-1])
        execenv.print(f"Object (from uuid)  '{obj.short_id}':{os.linesep}{obj}")

        # Use "calc" method with parameters
        param = MovingMedianParam()
        param.n = 5
        win.calc("compute_moving_median", param)
        # Use "calc" method without parameters
        win.calc("compute_integral")
        # Use "calc" and choose an unknown computation method
        try:
            win.calc("unknown_method")
            raise RuntimeError("Unknown method should have raised an exception")
        except ValueError:
            pass

        # Force application menus to pop-up
        for menu in (
            win.file_menu,
            win.edit_menu,
            win.operation_menu,
            win.processing_menu,
            win.computing_menu,
            win.view_menu,
            win.help_menu,
        ):
            menu.popup(menu.pos())
        win.file_menu.popup(win.mapToGlobal(win.file_menu.pos()))

        # Open settings dialog
        win.settings_action.trigger()


if __name__ == "__main__":
    test()