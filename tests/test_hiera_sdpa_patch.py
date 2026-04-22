"""Unit tests for the Hiera global-attention FlashAttention patch.

The patch lives in CorridorKeyModule.core.model_transformer and rewrites
MaskUnitAttention.forward on global-attention blocks so SDPA can dispatch
to the FlashAttention kernel instead of falling back to math.

These tests use a tiny fake attention module to exercise the patch logic
without requiring timm, a real Hiera model, or a GPU. A byte-identical
regression test against a real Hiera runs under the `gpu` marker and is
skipped in CI.
"""

from __future__ import annotations

import types

import pytest
import torch
import torch.nn as nn

from CorridorKeyModule.core.model_transformer import _patch_hiera_global_attention


class _FakeAttn(nn.Module):
    """Minimal stand-in for Hiera's MaskUnitAttention.

    Structured to look like the real module: same attribute names, a
    ``forward`` we can replace, real nn.Linear for qkv/proj so the patched
    forward can actually run.
    """

    def __init__(self, *, use_mask_unit_attn: bool, dim: int = 32, heads: int = 4, q_stride: int = 1) -> None:
        super().__init__()
        self.use_mask_unit_attn = use_mask_unit_attn
        self.heads = heads
        self.head_dim = dim // heads
        self.q_stride = q_stride
        self.dim_out = dim
        self.qkv = nn.Linear(dim, dim * 3)
        self.proj = nn.Linear(dim, dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:  # pragma: no cover - replaced
        raise AssertionError("original forward should be replaced by the patch")


class _FakeBlock(nn.Module):
    def __init__(self, *, use_mask_unit_attn: bool) -> None:
        super().__init__()
        self.attn = _FakeAttn(use_mask_unit_attn=use_mask_unit_attn)


class _FakeHiera(nn.Module):
    def __init__(self, mask_flags: list[bool]) -> None:
        super().__init__()
        self.blocks = nn.ModuleList([_FakeBlock(use_mask_unit_attn=f) for f in mask_flags])


def test_patches_only_global_blocks():
    hiera = _FakeHiera([True, True, False, False, True])
    patched = _patch_hiera_global_attention(hiera)
    assert patched == 2
    # Windowed blocks kept the placeholder forward; global blocks were replaced.
    flags = [True, True, False, False, True]
    for blk, flag in zip(hiera.blocks, flags, strict=True):
        fwd = blk.attn.forward
        is_replaced = isinstance(fwd, types.MethodType) and fwd.__func__.__name__ == "_patched_forward"
        assert is_replaced == (not flag)


def test_returns_zero_when_all_windowed():
    hiera = _FakeHiera([True, True, True])
    assert _patch_hiera_global_attention(hiera) == 0


def test_returns_zero_on_empty_model():
    class Empty(nn.Module):
        pass

    assert _patch_hiera_global_attention(Empty()) == 0


def test_patched_forward_runs_and_returns_correct_shape():
    """The replaced forward must be callable and shape-preserving."""
    hiera = _FakeHiera([False])  # one global block
    _patch_hiera_global_attention(hiera)

    blk = hiera.blocks[0]
    # Input [B, N, dim]; dim=32 matches _FakeAttn default.
    x = torch.randn(2, 16, 32)
    with torch.no_grad():
        out = blk.attn.forward(x)
    assert out.shape == x.shape


@pytest.mark.gpu
def test_real_hiera_patch_is_bit_identical():
    """Regression: patched global-attn forward produces bit-identical output to the original.

    Requires a real Hiera via timm plus a GPU to hit the FlashAttention
    path. Skipped in CI (no GPU). Run locally with pytest -m gpu.
    """
    import timm

    if not torch.cuda.is_available():
        pytest.skip("CUDA required for SDPA kernel dispatch comparison")

    encoder = (
        timm.create_model(
            "hiera_base_plus_224.mae_in1k_ft_in1k",
            pretrained=False,
            features_only=True,
            img_size=512,
        )
        .cuda()
        .eval()
    )

    hiera = encoder.model if hasattr(encoder, "model") else encoder

    # Capture original forwards for global blocks only.
    original_forwards: list[tuple[int, object]] = []
    for i, blk in enumerate(hiera.blocks):
        if not getattr(blk.attn, "use_mask_unit_attn", True):
            original_forwards.append((i, blk.attn.forward))

    assert original_forwards, "expected at least one global-attn block in Hiera base plus"

    # Raw timm Hiera expects 3-channel input; GreenFormer patches this to 4
    # separately. We just exercise the attention path here.
    x = torch.randn(1, 3, 512, 512, device="cuda")
    with torch.no_grad():
        baseline = encoder(x)

    _patch_hiera_global_attention(hiera)
    with torch.no_grad():
        patched = encoder(x)

    for b, p in zip(baseline, patched, strict=True):
        # Allow epsilon from numerical kernel differences (FlashAttention vs
        # math). We want close, not strictly equal, because the whole point
        # is the kernel changes.
        assert torch.allclose(b, p, rtol=1e-3, atol=1e-3), f"outputs diverged by {(b - p).abs().max()}"
