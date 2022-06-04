# -*- coding: utf-8 -*-
#
# Licensed under the terms of the BSD 3-Clause or the CeCILL-B License
# (see codraft/__init__.py for details)

"""
ROI test:

  - Defining Region of Interest on a signal
  - Defining Region of Interest on an image
"""

# pylint: disable=invalid-name  # Allows short reference names like x, y, ...

import numpy as np

from codraft.core.gui.image import ImagePanel
from codraft.core.gui.processor.image import PeakDetectionParam
from codraft.core.gui.processor.signal import FWHMParam
from codraft.core.gui.signal import SignalPanel
from codraft.core.model.signal import SignalParam
from codraft.tests import codraft_app_context
from codraft.tests.data import create_test_image3, create_test_signal1

SHOW = True  # Show test in GUI-based test launcher


def test_signal_features(panel: SignalPanel):
    """Test all signal features related to ROI"""
    panel.processor.compute_fwhm(FWHMParam())
    panel.processor.compute_fw1e2()
    panel.processor.extract_roi()


def test_image_features(panel: ImagePanel):
    """Test all image features related to ROI"""
    panel.processor.compute_centroid()
    panel.processor.compute_enclosing_circle()
    panel.processor.compute_peak_detection(PeakDetectionParam())
    panel.processor.extract_roi()


def create_test_image_with_roi(size=None):
    """Create test image with ROIs"""
    ima = create_test_image3(size)
    dy, dx = ima.size
    roi1 = [dx // 2, dy // 2, dx - 25, dy]
    roi2 = [dx // 4, dy // 4, dx // 2, dy // 2]
    ima.roi = np.array([roi1, roi2], int)
    return ima


def array_2d_to_str(arr: np.ndarray) -> str:
    """Return 2-D array characteristics as string"""
    return f"{arr.shape[0]} x {arr.shape[1]} array (min={arr.min()}, max={arr.max()})"


def array_1d_to_str(arr: np.ndarray) -> str:
    """Return 1-D array characteristics as string"""
    return f"{arr.size} columns array (min={arr.min()}, max={arr.max()})"


def print_obj_shapes(obj):
    """Print object and associated ROI array shapes"""
    print(f"  Accessing object '{obj.title}':")
    func = array_1d_to_str if isinstance(obj, SignalParam) else array_2d_to_str
    print(f"    data: {func(obj.data)}")
    if obj.roi is not None:
        for idx in range(obj.roi.shape[0]):
            roi_data = obj.get_data(idx)
            if isinstance(obj, SignalParam):
                roi_data = roi_data[1]  # y data
            print(f"    ROI[{idx}]: {func(roi_data)}")


def test():
    """Run ROI unit test scenario"""
    size = 200
    with codraft_app_context() as win:
        print("ROI application test:")
        # === Signal ROI extraction test ===
        panel = win.signalpanel
        sig1 = create_test_signal1(size)
        panel.add_object(sig1)
        test_signal_features(panel)
        sig2 = create_test_signal1(size)
        sig2.roi = np.array([[26, 41], [125, 146]], int)
        panel.add_object(sig2)
        print_obj_shapes(sig2)
        panel.processor.edit_regions_of_interest()
        win.take_screenshot("s_roi_signal")
        test_signal_features(panel)
        # === Image ROI extraction test ===
        panel = win.imagepanel
        ima1 = create_test_image3(size)
        panel.add_object(ima1)
        test_image_features(panel)
        ima2 = create_test_image_with_roi(size)
        panel.add_object(ima2)
        print_obj_shapes(ima2)
        panel.processor.edit_regions_of_interest()
        win.take_screenshot("i_roi_image")
        test_image_features(panel)


if __name__ == "__main__":
    test()
