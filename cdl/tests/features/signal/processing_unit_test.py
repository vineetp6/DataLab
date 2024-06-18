# Copyright (c) DataLab Platform Developers, BSD 3-Clause license, see LICENSE file.

"""
Unit tests for signal processing functions
------------------------------------------

Features from the "Processing" menu are covered by this test.
The "Processing" menu contains functions to process signals, such as
calibration, smoothing, and baseline correction.

Some of the functions are tested here, such as the signal calibration.
Other functions may be tested in different files, depending on the
complexity of the function.
"""

# pylint: disable=invalid-name  # Allows short reference names like x, y, ...
# pylint: disable=duplicate-code
# guitest: show

from __future__ import annotations

import numpy as np
import pytest
import scipy.ndimage as spi
import scipy.signal as sps

import cdl.computation.signal as cps
import cdl.obj
import cdl.param
from cdl.tests.data import get_test_signal
from cdl.utils.tests import check_array_result, check_scalar_result


@pytest.mark.validation
def test_signal_calibration() -> None:
    """Validation test for the signal calibration processing."""
    src = get_test_signal("paracetamol.txt")
    param = cdl.param.XYCalibrateParam()

    # Test with a = 1 and b = 0: should do nothing
    param.a, param.b = 1.0, 0.0
    for axis, _taxis in param.axes:
        param.axis = axis
        dst = cps.compute_calibration(src, param)
        exp = src.xydata
        check_array_result("Calibration[identity]", dst.xydata, exp)

    # Testing with random values of a and b
    param.a, param.b = 0.5, 0.1
    for axis, _taxis in param.axes:
        param.axis = axis
        exp_x1, exp_y1 = src.xydata.copy()
        if axis == "x":
            exp_x1 = param.a * exp_x1 + param.b
        else:
            exp_y1 = param.a * exp_y1 + param.b
        dst = cps.compute_calibration(src, param)
        res_x1, res_y1 = dst.xydata
        title = f"Calibration[{axis},a={param.a},b={param.b}]"
        check_array_result(f"{title}.x", res_x1, exp_x1)
        check_array_result(f"{title}.y", res_y1, exp_y1)


@pytest.mark.validation
def test_signal_swap_axes() -> None:
    """Validation test for the signal axes swapping processing."""
    src = get_test_signal("paracetamol.txt")
    dst = cps.compute_swap_axes(src)
    exp_y, exp_x = src.xydata
    check_array_result("SwapAxes|x", dst.x, exp_x)
    check_array_result("SwapAxes|y", dst.y, exp_y)


@pytest.mark.validation
def test_signal_swap_normalize() -> None:
    """Validation test for the signal normalization processing."""
    src = get_test_signal("paracetamol.txt")
    param = cdl.param.NormalizeParam()

    # Given the fact that the normalization methods implementations are
    # straightforward, we do not need to compare arrays with each other,
    # we simply need to check if some properties are satisfied.
    for method_value, _method_name in param.methods:
        param.method = method_value
        dst = cps.compute_normalize(src, param)
        title = f"Normalize[method='{param.method}']"
        if param.method == "maximum":
            exp_min, exp_max = src.data.min() / src.data.max(), 1.0
        elif param.method == "amplitude":
            exp_min, exp_max = 0.0, 1.0
        elif param.method == "area":
            area = src.data.sum()
            exp_min, exp_max = src.data.min() / area, src.data.max() / area
        elif param.method == "energy":
            energy = np.sqrt(np.sum(np.abs(src.data) ** 2))
            exp_min, exp_max = src.data.min() / energy, src.data.max() / energy
        elif param.method == "rms":
            rms = np.sqrt(np.mean(np.abs(src.data) ** 2))
            exp_min, exp_max = src.data.min() / rms, src.data.max() / rms
        check_scalar_result(f"{title}|min", dst.data.min(), exp_min)
        check_scalar_result(f"{title}|max", dst.data.max(), exp_max)


@pytest.mark.validation
def test_signal_clip() -> None:
    """Validation test for the signal clipping processing."""
    src = get_test_signal("paracetamol.txt")
    param = cdl.param.ClipParam()

    for lower, upper in ((float("-inf"), float("inf")), (250.0, 500.0)):
        param.lower, param.upper = lower, upper
        dst = cps.compute_clip(src, param)
        exp = np.clip(src.data, param.lower, param.upper)
        check_array_result(f"Clip[{lower},{upper}]", dst.data, exp)


@pytest.mark.validation
def test_signal_convolution() -> None:
    """Validation test for the signal convolution processing."""
    src1 = get_test_signal("paracetamol.txt")
    snew = cdl.obj.new_signal_param("Gaussian", stype=cdl.obj.SignalTypes.GAUSS)
    addparam = cdl.obj.GaussLorentzVoigtParam.create(sigma=10.0)
    src2 = cdl.obj.create_signal_from_param(snew, addparam=addparam, edit=False)

    dst = cps.compute_convolution(src1, src2)
    exp = np.convolve(src1.data, src2.data, mode="same")
    check_array_result("Convolution", dst.data, exp)


@pytest.mark.validation
def test_signal_derivative() -> None:
    """Validation test for the signal derivative processing."""
    src = get_test_signal("paracetamol.txt")

    dst = cps.compute_derivative(src)

    x, y = src.xydata

    # Compute the derivative using a simple finite difference:
    dx = x[1:] - x[:-1]
    dy = y[1:] - y[:-1]
    dydx = dy / dx
    exp = np.zeros_like(y)
    exp[0] = dydx[0]
    exp[1:-1] = (dydx[:-1] * dx[1:] + dydx[1:] * dx[:-1]) / (dx[1:] + dx[:-1])
    exp[-1] = dydx[-1]

    check_array_result("Derivative", dst.y, exp)


@pytest.mark.validation
def test_signal_integral() -> None:
    """Validation test for the signal integral processing."""
    src = get_test_signal("paracetamol.txt")
    src.data /= np.max(src.data)

    # Check the integral of the derivative:
    dst = cps.compute_integral(cps.compute_derivative(src))
    # The integral of the derivative should be the original signal, up to a constant:
    dst.y += src.y[0]

    check_array_result("Integral[Derivative]", dst.y, src.y, atol=0.05)

    dst = cps.compute_integral(src)

    x, y = src.xydata

    # Compute the integral using a simple trapezoidal rule:
    exp = np.zeros_like(y)
    exp[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * (x[1:] - x[:-1]))
    exp[0] = exp[1]

    check_array_result("Integral", dst.y, exp, atol=0.05)


@pytest.mark.validation
def test_signal_offset_correction() -> None:
    """Validation test for the signal offset correction processing."""
    src = get_test_signal("paracetamol.txt")
    # Defining the ROI that will be used to estimate the offset
    imin, imax = 0, 20
    param = cdl.obj.ROI1DParam.create(xmin=src.x[imin], xmax=src.x[imax])
    dst = cps.compute_offset_correction(src, param)
    exp = src.data - np.mean(src.data[imin:imax])
    check_array_result("OffsetCorrection", dst.data, exp)


@pytest.mark.validation
def test_signal_gaussian_filter() -> None:
    """Validation test for the signal Gaussian filter processing."""
    src = get_test_signal("paracetamol.txt")
    for sigma in (10.0, 50.0):
        param = cdl.param.GaussianParam.create(sigma=sigma)
        dst = cps.compute_gaussian_filter(src, param)
        exp = spi.gaussian_filter(src.data, sigma=sigma)
        check_array_result(f"GaussianFilter[sigma={sigma}]", dst.data, exp)


@pytest.mark.validation
def test_signal_moving_average() -> None:
    """Validation test for the signal moving average processing."""
    src = get_test_signal("paracetamol.txt")
    param = cdl.param.MovingAverageParam.create(n=30)
    dst = cps.compute_moving_average(src, param)
    exp = spi.uniform_filter(src.data, size=param.n, mode="reflect")

    # Implementation note:
    # --------------------
    #
    # The SciPy's `uniform_filter` handles the edges more accurately than
    # a method based on a simple convolution with a kernel of ones like this:
    # (the following function was the original implementation of the moving average
    # in DataLab before it was replaced by the SciPy's `uniform_filter` function)
    #
    # def moving_average(y: np.ndarray, n: int) -> np.ndarray:
    #     y_padded = np.pad(y, (n // 2, n - 1 - n // 2), mode="edge")
    #     return np.convolve(y_padded, np.ones((n,)) / n, mode="valid")

    check_array_result(f"MovingAverage[n={param.n}]", dst.data, exp, rtol=0.1)


@pytest.mark.validation
def test_signal_moving_median() -> None:
    """Validation test for the signal moving median processing."""
    src = get_test_signal("paracetamol.txt")
    param = cdl.param.MovingMedianParam.create(n=15)
    dst = cps.compute_moving_median(src, param)
    exp = spi.median_filter(src.data, size=param.n, mode="reflect")
    check_array_result(f"MovingMedian[n={param.n}]", dst.data, exp, rtol=0.1)


@pytest.mark.validation
def test_signal_wiener() -> None:
    """Validation test for the signal Wiener filter processing."""
    src = get_test_signal("paracetamol.txt")
    dst = cps.compute_wiener(src)
    exp = sps.wiener(src.data)
    check_array_result("Wiener", dst.data, exp)


if __name__ == "__main__":
    test_signal_calibration()
    test_signal_swap_axes()
    test_signal_swap_normalize()
    test_signal_clip()
    test_signal_convolution()
    test_signal_derivative()
    test_signal_integral()
    test_signal_offset_correction()
    test_signal_gaussian_filter()
    test_signal_moving_average()
    test_signal_moving_median()
    test_signal_wiener()
