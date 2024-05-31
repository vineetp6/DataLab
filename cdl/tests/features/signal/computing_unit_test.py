# Copyright (c) DataLab Platform Developers, BSD 3-Clause license, see LICENSE file.

"""
Unit tests for signal computing functions
-----------------------------------------

Features from the "Computing" menu are covered by this test.
The "Computing" menu contains functions to compute signal properties like
bandwidth, ENOB, etc.
"""

# pylint: disable=invalid-name  # Allows short reference names like x, y, ...
# pylint: disable=duplicate-code
# guitest: show

from __future__ import annotations

import pytest

import cdl.core.computation.signal as cps
import cdl.obj
import cdl.param
from cdl.tests.data import get_test_signal
from cdl.utils.tests import check_scalar_result


@pytest.mark.validation
def test_signal_bandwidth_3db() -> None:
    """Validation test for the bandwidth computation."""
    obj = get_test_signal("bandwidth.txt")
    df = cps.compute_bandwidth_3db(obj).to_dataframe()
    check_scalar_result("Bandwitdh@-3dB", df.L[0], 39.0, rtol=0.001)


@pytest.mark.validation
def test_dynamic_parameters() -> None:
    """Validation test for dynamic parameters computation."""
    obj = get_test_signal("dynamic_parameters.txt")
    param = cdl.param.DynamicParam.create(full_scale=1.0)
    df = cps.compute_dynamic_parameters(obj, param).to_dataframe()
    check_scalar_result("ENOB", df.ENOB[0], 5.1, rtol=0.001)
    check_scalar_result("SINAD", df.SINAD[0], 32.49, rtol=0.001)
    check_scalar_result("THD", df.THD[0], -30.18, rtol=0.001)
    check_scalar_result("SFDR", df.SFDR[0], 34.03, rtol=0.001)
    check_scalar_result("Freq", df.Freq[0], 49998377.464, rtol=0.001)
    check_scalar_result("SNR", df.SNR[0], 101.52, rtol=0.001)


@pytest.mark.validation
def test_signal_sampling_rate_period() -> None:
    """Validation test for the sampling rate and period computation."""
    obj = get_test_signal("dynamic_parameters.txt")
    df = cps.compute_sampling_rate_period(obj).to_dataframe()
    check_scalar_result("Sampling rate", df["fs"][0], 1.0e10, rtol=0.001)
    check_scalar_result("Period", df["T"][0], 1.0e-10, rtol=0.001)


@pytest.mark.validation
def test_signal_contrast() -> None:
    """Validation test for the contrast computation."""
    obj = get_test_signal("fw1e2.txt")
    df = cps.compute_contrast(obj).to_dataframe()
    check_scalar_result("Contrast", df.contrast[0], 0.825, rtol=0.001)


@pytest.mark.validation
def test_signal_x_at_minmax() -> None:
    """Validation test for the x value at min/max computation."""
    obj = get_test_signal("fw1e2.txt")
    df = cps.compute_x_at_minmax(obj).to_dataframe()
    check_scalar_result("X@Ymin", df["X@Ymin"][0], 0.803, rtol=0.001)
    check_scalar_result("X@Ymax", df["X@Ymax"][0], 5.184, rtol=0.001)


if __name__ == "__main__":
    test_signal_bandwidth_3db()
    test_dynamic_parameters()
    test_signal_sampling_rate_period()
    test_signal_contrast()
    test_signal_x_at_minmax()
