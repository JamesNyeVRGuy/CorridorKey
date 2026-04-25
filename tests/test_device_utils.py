"""Unit tests for device_utils — cross-platform device selection.

Tests cover all code paths in detect_best_device(), resolve_device(),
and clear_device_cache() using monkeypatch to mock hardware availability.
No GPU required.
"""

from unittest.mock import MagicMock

import pytest
import torch

from device_utils import (
    DEVICE_ENV_VAR,
    MIN_CUDA_COMPUTE_CAPABILITY,
    GPUInfo,
    check_gpu_torch_compat,
    clear_device_cache,
    detect_best_device,
    resolve_device,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_gpu(monkeypatch, *, cuda=False, mps=False):
    """Mock CUDA and MPS availability flags."""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: cuda)
    # MPS lives behind torch.backends.mps; ensure the attr path exists
    mps_backend = MagicMock()
    mps_backend.is_available = MagicMock(return_value=mps)
    monkeypatch.setattr(torch.backends, "mps", mps_backend)


def _patch_rocm(monkeypatch, *, rocm=True):
    """Mock ROCm host detection and runtime setup."""
    monkeypatch.setattr("device_utils.is_rocm_system", lambda: rocm)
    monkeypatch.setattr("device_utils.setup_rocm_env", lambda: None)


# ---------------------------------------------------------------------------
# detect_best_device
# ---------------------------------------------------------------------------


class TestDetectBestDevice:
    """Priority chain: CUDA > MPS > CPU."""

    def test_returns_cuda_when_available(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True, mps=True)
        assert detect_best_device() == "cuda"

    def test_rocm_host_still_returns_cuda_when_torch_sees_gpu(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True, mps=False)
        _patch_rocm(monkeypatch, rocm=True)
        assert detect_best_device() == "cuda"

    def test_returns_mps_when_no_cuda(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=True)
        assert detect_best_device() == "mps"

    def test_returns_cpu_when_nothing(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        assert detect_best_device() == "cpu"

    def test_rocm_host_logs_and_falls_back_to_cpu_when_no_gpu_backend(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        _patch_rocm(monkeypatch, rocm=True)
        assert detect_best_device() == "cpu"


# ---------------------------------------------------------------------------
# resolve_device
# ---------------------------------------------------------------------------


class TestResolveDevice:
    """Priority chain: CLI arg > env var > auto-detect."""

    # --- auto-detect path ---

    def test_none_triggers_auto_detect(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        monkeypatch.delenv(DEVICE_ENV_VAR, raising=False)
        assert resolve_device(None) == "cpu"

    def test_auto_string_triggers_auto_detect(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True)
        monkeypatch.delenv(DEVICE_ENV_VAR, raising=False)
        assert resolve_device("auto") == "cuda"

    # --- env var fallback ---

    def test_env_var_used_when_no_cli_arg(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True, mps=True)
        monkeypatch.setenv(DEVICE_ENV_VAR, "cpu")
        assert resolve_device(None) == "cpu"

    def test_env_var_auto_triggers_detect(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=True)
        monkeypatch.setenv(DEVICE_ENV_VAR, "auto")
        assert resolve_device(None) == "mps"

    # --- CLI arg overrides env var ---

    def test_cli_arg_overrides_env_var(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True, mps=True)
        monkeypatch.setenv(DEVICE_ENV_VAR, "mps")
        assert resolve_device("cuda") == "cuda"

    # --- explicit valid devices ---

    def test_explicit_cuda(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True)
        assert resolve_device("cuda") == "cuda"

    def test_explicit_cuda_on_rocm_host_uses_cuda_backend_when_available(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=True)
        _patch_rocm(monkeypatch, rocm=True)
        assert resolve_device("cuda") == "cuda"

    def test_explicit_mps(self, monkeypatch):
        _patch_gpu(monkeypatch, mps=True)
        assert resolve_device("mps") == "mps"

    def test_explicit_cpu(self, monkeypatch):
        assert resolve_device("cpu") == "cpu"

    def test_case_insensitive(self, monkeypatch):
        assert resolve_device("CPU") == "cpu"

    # --- unavailable backend errors ---

    def test_cuda_unavailable_raises(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False)
        _patch_rocm(monkeypatch, rocm=False)
        with pytest.raises(RuntimeError, match="CUDA requested"):
            resolve_device("cuda")

    def test_cuda_unavailable_on_rocm_host_raises_rocm_specific_error(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False)
        _patch_rocm(monkeypatch, rocm=True)
        with pytest.raises(RuntimeError, match="ROCm host"):
            resolve_device("cuda")

    def test_mps_no_backend_raises(self, monkeypatch):
        # Simulate PyTorch build without MPS module in torch.backends
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        # Replace torch.backends with an object that lacks "mps" entirely
        fake_backends = type("Backends", (), {})()
        monkeypatch.setattr(torch, "backends", fake_backends)
        with pytest.raises(RuntimeError, match="no MPS support"):
            resolve_device("mps")

    def test_mps_unavailable_raises(self, monkeypatch):
        _patch_gpu(monkeypatch, cuda=False, mps=False)
        with pytest.raises(RuntimeError, match="not available on this machine"):
            resolve_device("mps")

    # --- invalid device string ---

    def test_invalid_device_raises(self, monkeypatch):
        with pytest.raises(RuntimeError, match="Unknown device"):
            resolve_device("tpu")


# ---------------------------------------------------------------------------
# clear_device_cache
# ---------------------------------------------------------------------------


class TestClearDeviceCache:
    """Dispatches to correct backend cache clear."""

    def test_cuda_clears_cache(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.cuda, "empty_cache", mock_empty)
        clear_device_cache("cuda")
        mock_empty.assert_called_once()

    def test_mps_clears_cache(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.mps, "empty_cache", mock_empty)
        clear_device_cache("mps")
        mock_empty.assert_called_once()

    def test_cpu_is_noop(self):
        # Should not raise
        clear_device_cache("cpu")

    def test_accepts_torch_device_object(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.cuda, "empty_cache", mock_empty)
        clear_device_cache(torch.device("cuda"))
        mock_empty.assert_called_once()

    def test_accepts_mps_device_object(self, monkeypatch):
        mock_empty = MagicMock()
        monkeypatch.setattr(torch.mps, "empty_cache", mock_empty)
        clear_device_cache(torch.device("mps"))
        mock_empty.assert_called_once()


# ---------------------------------------------------------------------------
# check_gpu_torch_compat
# ---------------------------------------------------------------------------


class TestCheckGpuTorchCompat:
    """Gate GPUs by the torch build's actual compute capability support (CRKY-188).

    Tests the static-fallback path by patching _torch_arch_list to return
    None (unavailable), then the dynamic path with a stubbed arch list.
    """

    def _make(self, cc: str) -> GPUInfo:
        return GPUInfo(index=0, name="Test GPU", vram_total_gb=24.0, vram_free_gb=24.0, compute_capability=cc)

    # --- static-fallback path (torch arch list unavailable) ---

    def test_pascal_rejected_via_static_floor(self, monkeypatch):
        monkeypatch.setattr("device_utils._torch_arch_list", lambda: None)
        ok, reason = check_gpu_torch_compat(self._make("6.1"))
        assert ok is False
        assert "6.1" in reason
        assert "below the minimum" in reason

    def test_maxwell_rejected_via_static_floor(self, monkeypatch):
        monkeypatch.setattr("device_utils._torch_arch_list", lambda: None)
        ok, reason = check_gpu_torch_compat(self._make("5.2"))
        assert ok is False
        assert "5.2" in reason

    def test_volta_accepted_via_static_floor(self, monkeypatch):
        monkeypatch.setattr("device_utils._torch_arch_list", lambda: None)
        ok, _ = check_gpu_torch_compat(self._make("7.0"))
        assert ok is True

    # --- dynamic path (torch reports its actual arch list) ---

    def test_pascal_accepted_when_torch_has_sm_61(self, monkeypatch):
        """If torch was built with Pascal kernels, Pascal should pass the gate."""
        monkeypatch.setattr(
            "device_utils._torch_arch_list",
            lambda: [(6, 1), (7, 0), (7, 5), (8, 0), (8, 6)],
        )
        ok, reason = check_gpu_torch_compat(self._make("6.1"))
        assert ok is True, f"expected Pascal accepted, got: {reason}"

    def test_pascal_rejected_when_torch_lacks_sm_61(self, monkeypatch):
        """Modern torch wheel without Pascal: 1080 Ti rejected with the actual supported list."""
        monkeypatch.setattr(
            "device_utils._torch_arch_list",
            lambda: [(7, 0), (7, 5), (8, 0), (8, 6), (9, 0), (12, 0)],
        )
        ok, reason = check_gpu_torch_compat(self._make("6.1"))
        assert ok is False
        assert "sm_70" in reason  # supported list should be listed

    def test_blackwell_accepted(self, monkeypatch):
        monkeypatch.setattr(
            "device_utils._torch_arch_list",
            lambda: [(7, 0), (7, 5), (8, 0), (12, 0)],
        )
        ok, _ = check_gpu_torch_compat(self._make("12.0"))
        assert ok is True

    # --- non-NVIDIA / unparseable cases ---

    def test_empty_cc_not_gated(self):
        ok, reason = check_gpu_torch_compat(self._make(""))
        assert ok is True
        assert reason == ""

    def test_unparseable_cc_not_gated(self):
        ok, _ = check_gpu_torch_compat(self._make("gfx1030"))
        assert ok is True

    def test_min_constant_is_sensible(self):
        # The fallback constant should match the most common torch wheel floor.
        # Update deliberately if torch drops further.
        assert MIN_CUDA_COMPUTE_CAPABILITY == (7, 0)
