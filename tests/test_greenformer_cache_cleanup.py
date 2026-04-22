"""Tests for CRKY-209: empty_cache() at stage seams in GreenFormer.forward.

The flag gates two torch.cuda.empty_cache() calls inside forward: one after
the encoder pyramid is consumed by the decoders, one after the refiner
consumes the coarse prediction. Neither call changes the math; they just
return workspace to the allocator between stages so peak VRAM during
the refiner pass drops by 2-5 GB on 2K+ inputs.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import torch
import torch.nn as nn

from CorridorKeyModule.core.model_transformer import GreenFormer


def _bare_greenformer(cache_cleanup: bool, use_refiner: bool = False) -> GreenFormer:
    """Build GreenFormer-shaped object without the real Hiera/timm path.

    We only need to exercise the forward seams, not the encoder. Bypass
    __init__ and stitch in the minimum viable state.
    """
    gf = object.__new__(GreenFormer)
    nn.Module.__init__(gf)
    gf._cache_cleanup = cache_cleanup
    gf.use_refiner = use_refiner
    gf.refiner = None

    # Fake encoder: returns a list (so `del features` removes the reference).
    def _fake_encoder(x: torch.Tensor):
        b = x.shape[0]
        return [torch.zeros(b, 1, 1, 1)]

    gf.encoder = _fake_encoder  # type: ignore[assignment]
    # Decoders return small tensors the downstream logic can interpolate.
    shape = lambda out_c: lambda feats: torch.zeros(feats[0].shape[0], out_c, 4, 4)  # noqa: E731
    gf.alpha_decoder = shape(1)
    gf.fg_decoder = shape(3)
    return gf


def test_flag_defaults_true():
    """Default constructor (bypassed here) must set cache_cleanup True via the arg default."""
    # Inspect the signature rather than building the real model (which would load timm).
    import inspect

    sig = inspect.signature(GreenFormer.__init__)
    assert sig.parameters["cache_cleanup"].default is True


def test_flag_stored_on_instance():
    gf_on = _bare_greenformer(cache_cleanup=True)
    gf_off = _bare_greenformer(cache_cleanup=False)
    assert gf_on._cache_cleanup is True
    assert gf_off._cache_cleanup is False


def test_forward_does_not_call_empty_cache_on_cpu_input():
    """x.is_cuda guard must suppress empty_cache when the model runs on CPU."""
    gf = _bare_greenformer(cache_cleanup=True)
    x = torch.zeros(1, 4, 16, 16)  # CPU tensor

    with patch("torch.cuda.empty_cache") as mock_empty:
        with torch.no_grad():
            gf.forward(x)
    assert mock_empty.call_count == 0


def test_forward_calls_empty_cache_at_both_seams_when_flag_on_and_cuda():
    """When both the flag is on and x.is_cuda, empty_cache is called twice."""
    gf = _bare_greenformer(cache_cleanup=True)

    # Fake a CUDA tensor by monkeypatching the is_cuda property on a CPU tensor.
    x = torch.zeros(1, 4, 16, 16)
    mock_x = MagicMock(wraps=x)
    mock_x.shape = x.shape
    mock_x.is_cuda = True

    with patch("torch.cuda.empty_cache") as mock_empty:
        with torch.no_grad():
            gf.forward(x)  # real CPU tensor, is_cuda is False
        baseline_calls = mock_empty.call_count

    assert baseline_calls == 0, "baseline (CPU) must not call empty_cache"

    # Now patch Tensor.is_cuda globally to True for the duration of the call.
    with patch("torch.cuda.empty_cache") as mock_empty, patch.object(torch.Tensor, "is_cuda", new=True):
        with torch.no_grad():
            gf.forward(x)
    assert mock_empty.call_count == 2, f"expected 2 seams, got {mock_empty.call_count}"


def test_forward_skips_empty_cache_when_flag_off_even_on_cuda():
    gf = _bare_greenformer(cache_cleanup=False)
    x = torch.zeros(1, 4, 16, 16)
    with patch("torch.cuda.empty_cache") as mock_empty, patch.object(torch.Tensor, "is_cuda", new=True):
        with torch.no_grad():
            gf.forward(x)
    assert mock_empty.call_count == 0


@pytest.mark.gpu
def test_forward_output_is_unchanged_by_cache_cleanup_flag():
    """Regression: the empty_cache seams must not alter output.

    Uses a tiny random-init GreenFormer on CUDA. Skipped in CI.
    """
    if not torch.cuda.is_available():
        pytest.skip("CUDA required")

    # Build at small img_size to keep timm instantiation cheap.
    a = GreenFormer(img_size=64, cache_cleanup=True).cuda().eval()
    b = GreenFormer(img_size=64, cache_cleanup=False).cuda().eval()

    # Copy weights so the two models are identical parameter-wise.
    b.load_state_dict(a.state_dict())

    x = torch.randn(1, 4, 64, 64, device="cuda")
    with torch.no_grad():
        out_on = a(x)
        out_off = b(x)

    for key in ("alpha", "fg"):
        assert torch.equal(out_on[key], out_off[key]), f"{key} differed between flag=on and flag=off"
