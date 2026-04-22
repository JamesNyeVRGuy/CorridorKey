"""Tests for CRKY-207: persistent device-tensor refiner scale.

The old behavior registered a transient forward hook per frame when
refiner_scale != 1.0, which broke torch.compile graph caching. The new
behavior installs a single hook at engine init that multiplies by a
1-element device tensor; per-frame scale changes go through .fill_()
on that tensor so the graph shape stays constant.
"""

from __future__ import annotations

import torch
import torch.nn as nn

from CorridorKeyModule.inference_engine import CorridorKeyEngine


class _StubRefiner(nn.Module):
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x


class _StubModel:
    def __init__(self, refiner: nn.Module | None) -> None:
        self.refiner = refiner


def _bare_engine(refiner: nn.Module | None) -> CorridorKeyEngine:
    """Build just enough of an engine to exercise _install_refiner_scale_hook."""
    engine = object.__new__(CorridorKeyEngine)
    engine.device = torch.device("cpu")
    engine.model_precision = torch.float32
    engine.model = _StubModel(refiner)
    return engine


def test_scale_tensor_starts_at_one():
    engine = _bare_engine(_StubRefiner())
    engine._install_refiner_scale_hook()

    assert engine._refiner_scale_t.numel() == 1
    assert engine._refiner_scale_t.item() == 1.0
    assert engine._refiner_scale_t.device == torch.device("cpu")
    assert engine._refiner_scale_t.dtype == torch.float32
    assert engine._refiner_hook_handle is not None


def test_no_hook_when_refiner_is_none():
    engine = _bare_engine(None)
    engine._install_refiner_scale_hook()

    assert engine._refiner_scale_t is not None
    assert engine._refiner_hook_handle is None


def test_hook_is_passthrough_at_default_scale():
    refiner = _StubRefiner()
    engine = _bare_engine(refiner)
    engine._install_refiner_scale_hook()

    x = torch.tensor([3.0, 7.0, -1.5])
    assert torch.equal(refiner(x), x)


def test_fill_updates_scale_without_reregistering_hook():
    """The whole point: fill_() changes the multiply without touching the hook."""
    refiner = _StubRefiner()
    engine = _bare_engine(refiner)
    engine._install_refiner_scale_hook()

    handle_before = engine._refiner_hook_handle
    x = torch.tensor([3.0, 7.0])

    engine._refiner_scale_t.fill_(2.5)
    assert torch.equal(refiner(x), x * 2.5)

    engine._refiner_scale_t.fill_(0.1)
    assert torch.allclose(refiner(x), x * 0.1)

    engine._refiner_scale_t.fill_(1.0)
    assert torch.equal(refiner(x), x)

    # Hook handle must not have been replaced by the updates.
    assert engine._refiner_hook_handle is handle_before


def test_scale_tensor_is_on_engine_device():
    """The tensor must be on self.device so it lands inside CUDA graphs."""
    engine = _bare_engine(_StubRefiner())
    engine.device = torch.device("cpu")
    engine._install_refiner_scale_hook()
    assert engine._refiner_scale_t.device == engine.device
