# -*- coding: utf-8 -*-
#
# Licensed under the terms of the BSD 3-Clause or the CeCILL-B License
# (see cdl/__init__.py for details)

"""
Log viewer test
"""

from cdl.utils.qthelpers import qt_app_context
from cdl.widgets.logviewer import exec_cdl_logviewer_dialog

SHOW = True  # Show test in GUI-based test launcher


def test_log_viewer():
    """Test log viewer window"""
    with qt_app_context():
        exec_cdl_logviewer_dialog()


if __name__ == "__main__":
    test_log_viewer()