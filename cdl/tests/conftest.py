# Copyright (c) DataLab Platform Developers, BSD 3-Clause license, see LICENSE file.

"""
DataLab pytest configuration
----------------------------

This file contains the configuration for running pytest in DataLab. It is
executed before running any tests.
"""

import os

import cv2
import guidata
import h5py
import numpy
import plotpy
import pytest
import qtpy
import qwt
import scipy
import skimage

import cdl
from cdl.env import execenv
from cdl.plugins import get_available_plugins

# Turn on unattended mode for executing tests without user interaction
execenv.unattended = True
execenv.verbose = "quiet"

INITIAL_CWD = os.getcwd()


def pytest_report_header(config):
    """Add additional information to the pytest report header."""
    nfstr = ", ".join(
        f"{plugin.info.name} {plugin.info.version}"
        for plugin in get_available_plugins()
    )
    qtbindings_version = qtpy.PYSIDE_VERSION
    if qtbindings_version is None:
        qtbindings_version = qtpy.PYQT_VERSION
    infolist = [
        f"DataLab {cdl.__version__} [Plugins: {nfstr if nfstr else 'None'}]",
        f"guidata {guidata.__version__}, PlotPy {plotpy.__version__}",
        f"PythonQwt {qwt.__version__}, "
        f"{qtpy.API_NAME} {qtbindings_version} [Qt version: {qtpy.QT_VERSION}]",
        f"NumPy {numpy.__version__}, SciPy {scipy.__version__}, "
        f"h5py {h5py.__version__}, "
        f"scikit-image {skimage.__version__}, OpenCV {cv2.__version__}",
    ]
    for vname in ("CDL_DATA", "PYTHONPATH", "DEBUG"):
        value = os.environ.get(vname, "")
        if value:
            infolist.append(f"{vname}: {value}")
    return infolist


def pytest_configure(config):
    """Add custom markers to pytest."""
    config.addinivalue_line(
        "markers",
        "validation: mark a test as a validation test (ground truth or analytical)",
    )


@pytest.fixture(autouse=True)
def reset_cwd(request):
    """Reset the current working directory to the initial one after each test."""
    yield
    os.chdir(INITIAL_CWD)
