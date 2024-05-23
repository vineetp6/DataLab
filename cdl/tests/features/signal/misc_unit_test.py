# Copyright (c) DataLab Platform Developers, BSD 3-Clause license, see LICENSE file.

"""
Miscellaneous signal tests
"""

# pylint: disable=invalid-name  # Allows short reference names like x, y, ...

from __future__ import annotations

import numpy as np
import pytest

import cdl.core.computation.signal as cps
import cdl.param
from cdl.obj import SignalTypes
from cdl.tests.data import create_periodic_signal


@pytest.mark.validation
def test_signal_addition() -> None:
    """Signal addition test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    s2 = create_periodic_signal(SignalTypes.SINUS)
    exp = s1.y + s2.y
    cps.compute_addition(s1, s2)
    res = s1.y
    assert np.allclose(res, exp), f"Signal addition failed: expected {exp}, got {res}"


@pytest.mark.validation
def test_signal_addition_constant() -> None:
    """Signal addition with constant test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    param = cdl.param.ConstantOperationParam.create(value=1.0)
    s2 = cps.compute_addition_constant(s1, param)
    assert np.allclose(s2.y, s1.y + param.value), "Signal addition with constant failed"


@pytest.mark.validation
def test_signal_product() -> None:
    """Signal multiplication test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    s2 = create_periodic_signal(SignalTypes.SINUS)
    exp = s1.y * s2.y
    cps.compute_product(s1, s2)
    res = s1.y
    assert np.allclose(
        res, exp
    ), f"Signal multiplication failed: expected {exp}, got {res}"


@pytest.mark.validation
def test_signal_product_constant() -> None:
    """Signal multiplication by constant test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    param = cdl.param.ConstantOperationParam.create(value=1.0)
    s2 = cps.compute_product_constant(s1, param)
    assert np.allclose(
        s2.y, s1.y * param.value
    ), "Signal multiplication by constant failed"


@pytest.mark.validation
def test_signal_difference() -> None:
    """Signal difference test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    s2 = create_periodic_signal(SignalTypes.SINUS)
    s3 = cps.compute_difference(s1, s2)
    assert np.allclose(s3.y, s1.y - s2.y), "Signal difference failed"


@pytest.mark.validation
def test_signal_difference_constant() -> None:
    """Signal difference with constant test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    param = cdl.param.ConstantOperationParam.create(value=1.0)
    s2 = cps.compute_difference_constant(s1, param)
    assert np.allclose(
        s2.y, s1.y - param.value
    ), "Signal difference with constant failed"


@pytest.mark.validation
def test_signal_divide() -> None:
    """Signal division test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    s2 = create_periodic_signal(SignalTypes.SINUS)
    s3 = cps.compute_division(s1, s2)
    assert np.allclose(s3.y, s1.y / s2.y), "Signal division failed"


@pytest.mark.validation
def test_signal_division_constant() -> None:
    """Signal division by constant test."""
    s1 = create_periodic_signal(SignalTypes.COSINUS)
    param = cdl.param.ConstantOperationParam.create(value=1.0)
    s2 = cps.compute_division_constant(s1, param)
    assert np.allclose(s2.y, s1.y / param.value), "Signal division by constant failed"


if __name__ == "__main__":
    test_signal_addition()
    test_signal_addition_constant()
    test_signal_product()
    test_signal_product_constant()
    test_signal_difference()
    test_signal_difference_constant()
    test_signal_divide()
    test_signal_division_constant()
