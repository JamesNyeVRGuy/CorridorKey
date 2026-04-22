"""Tests for CRKY-210: TiledCNNRefiner and the tiled_refiner engine flag.

The tiled refiner swaps the single-pass CNN refiner for one that
processes input in 512x512 tiles with 128px overlap. Because the
refiner's receptive field is ~65px, the 128px overlap covers it and
the output is mathematically lossless (down to floating-point
accumulation order).

Two sets of tests:
1. Class-level: blend ramp shape, small-input passthrough, equivalence
   to the untiled refiner on an input that exercises actual tiling.
2. Engine-level: _resolve_tiled_refiner honours env var, kwarg, and
   CUDA VRAM heuristic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch

from CorridorKeyModule.core.model_transformer import (
    DEFAULT_TILE_OVERLAP,
    DEFAULT_TILE_SIZE,
    CNNRefinerModule,
    TiledCNNRefiner,
)
from CorridorKeyModule.inference_engine import CorridorKeyEngine

# ---------------------------------------------------------------------------
# TiledCNNRefiner class
# ---------------------------------------------------------------------------


def test_defaults_match_oblivius_port_constants():
    assert DEFAULT_TILE_SIZE == 512
    assert DEFAULT_TILE_OVERLAP == 128


def test_blend_weight_shape_and_corners():
    refiner = TiledCNNRefiner(tile_size=64, tile_overlap=16)
    w = refiner._create_blend_weight(64, 64, 16, torch.device("cpu"), torch.float32)
    assert w.shape == (1, 1, 64, 64)
    # Corner pixel is (ramp[0] * ramp[0]) = 0; interior is 1.
    assert w[0, 0, 0, 0].item() == pytest.approx(0.0)
    assert w[0, 0, 32, 32].item() == pytest.approx(1.0)
    # Edge midpoints: one axis is in interior (1.0), other is the first
    # ramp step, product = ramp[0] = 0.
    assert w[0, 0, 0, 32].item() == pytest.approx(0.0)


def test_blend_weight_zero_overlap_is_all_ones():
    refiner = TiledCNNRefiner(tile_size=8, tile_overlap=0)
    w = refiner._create_blend_weight(8, 8, 0, torch.device("cpu"), torch.float32)
    assert torch.equal(w, torch.ones(1, 1, 8, 8))


def test_small_input_skips_tiling_and_matches_parent_forward():
    """When tile_size >= H and W, forward falls through to a single _process_tile."""
    torch.manual_seed(0)
    tiled = TiledCNNRefiner(tile_size=64, tile_overlap=16)
    tiled.eval()

    img = torch.randn(1, 3, 32, 32)  # smaller than tile_size
    coarse = torch.randn(1, 4, 32, 32)

    # Reference: the parent forward builds cat internally, so compare the
    # single-tile output from the tiled refiner against parent forward on
    # the same weights.
    plain = CNNRefinerModule()
    plain.load_state_dict({k: v.clone() for k, v in tiled.state_dict().items()})
    plain.eval()

    with torch.no_grad():
        tiled_out = tiled(img, coarse)
        plain_out = plain(img, coarse)
    assert torch.allclose(tiled_out, plain_out, atol=1e-6, rtol=1e-6)


def test_tiled_output_has_correct_shape_and_is_finite():
    """Tiling must produce an output with the same shape as the input and
    no NaN/Inf values, even when the loop runs several times.
    """
    torch.manual_seed(1)
    tiled = TiledCNNRefiner(tile_size=48, tile_overlap=16)
    tiled.eval()
    img = torch.randn(1, 3, 96, 112)
    coarse = torch.randn(1, 4, 96, 112)
    with torch.no_grad():
        out = tiled(img, coarse)
    assert out.shape == (1, 4, 96, 112)
    assert torch.isfinite(out).all()


@pytest.mark.gpu
def test_tiled_matches_untiled_within_vfx_tolerance():
    """Tiled vs untiled on a representative size.

    Oblivius's 'mathematically lossless' claim is an overclaim: the linear
    ramp from 0 to 1 over ``overlap`` pixels gives small non-zero weight to
    the neighbouring tile's prediction before that tile has reached full
    receptive field. The residual error is bounded by (RF / overlap) times
    the local prediction magnitude; in practice this stays well under 5e-2
    for the defaults (tile=512, overlap=128, RF~=63). That's below VFX
    noise for alpha mattes but not bit-identical.
    """
    if not torch.cuda.is_available():
        pytest.skip("CUDA required")

    torch.manual_seed(2)
    tiled = TiledCNNRefiner(tile_size=DEFAULT_TILE_SIZE, tile_overlap=DEFAULT_TILE_OVERLAP).cuda().eval()
    plain = CNNRefinerModule().cuda().eval()
    plain.load_state_dict({k: v.clone() for k, v in tiled.state_dict().items()})

    H = W = 1024
    img = torch.randn(1, 3, H, W, device="cuda")
    coarse = torch.randn(1, 4, H, W, device="cuda")
    with torch.no_grad():
        tiled_out = tiled(img, coarse)
        plain_out = plain(img, coarse)

    margin = DEFAULT_TILE_OVERLAP
    t = tiled_out[..., margin:-margin, margin:-margin]
    p = plain_out[..., margin:-margin, margin:-margin]
    max_diff = (t - p).abs().max().item()
    assert max_diff < 5e-2, f"tiled vs untiled max diff in interior = {max_diff}"


def test_blend_cache_reuses_entries_by_shape():
    refiner = TiledCNNRefiner(tile_size=32, tile_overlap=8)
    refiner.eval()
    img = torch.randn(1, 3, 80, 80)
    coarse = torch.randn(1, 4, 80, 80)
    with torch.no_grad():
        refiner(img, coarse)
    # Full-size tiles should produce one blend shape; edge tiles may add
    # additional shapes. At minimum the full-size shape is cached.
    assert (32, 32) in refiner._blend_cache
    assert refiner._blend_cache[(32, 32)].shape == (1, 1, 32, 32)


# ---------------------------------------------------------------------------
# Engine-level flag resolution
# ---------------------------------------------------------------------------


def _engine_resolver(device: str = "cpu") -> CorridorKeyEngine:
    engine = object.__new__(CorridorKeyEngine)
    engine.device = torch.device(device)
    return engine


def test_resolve_tiled_explicit_true():
    assert _engine_resolver()._resolve_tiled_refiner(True) is True


def test_resolve_tiled_explicit_false():
    assert _engine_resolver()._resolve_tiled_refiner(False) is False


def test_resolve_tiled_auto_on_cpu_is_false():
    assert _engine_resolver("cpu")._resolve_tiled_refiner("auto") is False


def test_resolve_tiled_env_var_overrides_kwarg():
    import os as _os

    with patch.dict(_os.environ, {"CORRIDORKEY_TILED_REFINER": "1"}):
        assert _engine_resolver()._resolve_tiled_refiner(False) is True
    with patch.dict(_os.environ, {"CORRIDORKEY_TILED_REFINER": "0"}):
        assert _engine_resolver()._resolve_tiled_refiner(True) is False


def test_resolve_tiled_auto_enables_under_threshold():
    engine = _engine_resolver("cpu")
    engine.device = torch.device("cuda:0")
    props = MagicMock()
    props.total_memory = 8 * (1024**3)  # 8 GB
    with patch("torch.cuda.get_device_properties", return_value=props):
        assert engine._resolve_tiled_refiner("auto") is True


def test_resolve_tiled_auto_disables_above_threshold():
    engine = _engine_resolver("cpu")
    engine.device = torch.device("cuda:0")
    props = MagicMock()
    props.total_memory = 24 * (1024**3)  # 24 GB
    with patch("torch.cuda.get_device_properties", return_value=props):
        assert engine._resolve_tiled_refiner("auto") is False
