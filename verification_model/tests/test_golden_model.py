"""
Unit tests for the golden model — hardware-accurate 3×3 convolution accelerator.

Run from the asic_suite/ directory:
    python -m pytest tests/test_golden_model.py -v

Or run directly:
    python tests/test_golden_model.py
"""
import sys
import os
import unittest

import numpy as np

# Allow import from asic_suite/ when run directly or via pytest from that dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.golden_model import run_golden_model, run_golden_model_fast

_MASK_20BIT = 0xFFFFF


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_image(fill: int = 128) -> np.ndarray:
    """Return a solid 256×256 uint8 image."""
    return np.full((256, 256), fill, dtype=np.uint8)


def _make_ramp_image() -> np.ndarray:
    """Return a 256×256 image where pixel[r,c] = (r + c) % 256."""
    r = np.arange(256, dtype=np.uint8)
    c = np.arange(256, dtype=np.uint8)
    return ((r[:, None].astype(np.int32) + c[None, :].astype(np.int32)) % 256).astype(np.uint8)


def _reference_conv(img: np.ndarray, kernel: np.ndarray,
                    bias: int, threshold: int) -> np.ndarray:
    """
    Pure-Python reference (deliberately different implementation from the module)
    using scipy.ndimage for cross-validation.  Falls back to a manual loop if
    scipy is unavailable.
    """
    try:
        from scipy.ndimage import correlate
        img64 = img.astype(np.int64)
        k64   = kernel.astype(np.int64)
        # correlate = cross-correlation (not convolution) — matches hardware patch sum
        mac = correlate(img64, k64, mode='constant', cval=0).astype(np.int64)
        mac = (mac + int(bias)) & _MASK_20BIT
        # Extract valid region only (rows 2-255, cols 2-255 → 254×254)
        return (mac[2:, 2:] > int(threshold)).astype(np.uint8)
    except ImportError:
        # Manual fallback
        out = np.zeros((254, 254), dtype=np.uint8)
        img64 = img.astype(np.int64)
        for row in range(254):
            for col in range(254):
                win = img64[row:row+3, col:col+3]
                s = int(np.sum(win * kernel.astype(np.int64))) + int(bias)
                out[row, col] = 1 if (s & _MASK_20BIT) > int(threshold) else 0
        return out


# ──────────────────────────────────────────────────────────────────────────────
# Test Cases
# ──────────────────────────────────────────────────────────────────────────────

class TestOutputShape(unittest.TestCase):
    """Both functions must always return exactly (254, 254) uint8."""

    def _check(self, fn):
        img    = _make_image(100)
        kernel = [[1,0,0],[0,0,0],[0,0,0]]
        result = fn(img, kernel, bias=0, threshold=50)
        self.assertEqual(result.shape, (254, 254))
        self.assertEqual(result.dtype, np.uint8)

    def test_shape_reference(self):
        self._check(run_golden_model)

    def test_shape_fast(self):
        self._check(run_golden_model_fast)


class TestReferenceMatchesFast(unittest.TestCase):
    """run_golden_model and run_golden_model_fast must produce bit-identical results."""

    def _check(self, img, kernel, bias, threshold, label=""):
        ref  = run_golden_model(img, kernel, bias=bias, threshold=threshold)
        fast = run_golden_model_fast(img, kernel, bias=bias, threshold=threshold)
        np.testing.assert_array_equal(
            ref, fast,
            err_msg=f"reference ≠ fast for: {label}"
        )

    def test_identity_kernel_uniform_image(self):
        """Center-only kernel on uniform image."""
        k = [[0,0,0],[0,1,0],[0,0,0]]
        self._check(_make_image(200), k, bias=0, threshold=150, label="identity uniform")

    def test_all_ones_kernel_uniform_image(self):
        """Sum of 9×pixel + bias — uniform image."""
        k = [[1,1,1],[1,1,1],[1,1,1]]
        self._check(_make_image(10), k, bias=5, threshold=100, label="all-ones uniform")

    def test_ramp_image(self):
        """Varied image content."""
        k = [[1,2,1],[2,4,2],[1,2,1]]   # Gaussian-like
        self._check(_make_ramp_image(), k, bias=0, threshold=1000, label="ramp Gaussian")

    def test_random_image_and_kernel(self):
        """Pseudo-random image and kernel."""
        rng = np.random.default_rng(42)
        img = rng.integers(0, 256, (256, 256), dtype=np.uint8)
        k   = rng.integers(0, 16, (3, 3)).tolist()
        self._check(img, k, bias=10, threshold=500, label="random")

    def test_threshold_boundary(self):
        """Pixels exactly at threshold must NOT fire (hardware uses strict >)."""
        # identity kernel: mac = pixel + bias; set threshold = pixel + bias exactly
        k   = [[0,0,0],[0,1,0],[0,0,0]]
        img = _make_image(100)   # all pixels = 100
        # threshold = 100 + 0 = 100 → should all be 0 (not >)
        ref  = run_golden_model(img, k, bias=0, threshold=100)
        fast = run_golden_model_fast(img, k, bias=0, threshold=100)
        self.assertTrue(np.all(ref == 0),  "reference: pixels at threshold should not fire")
        self.assertTrue(np.all(fast == 0), "fast: pixels at threshold should not fire")
        # threshold = 99 → should all be 1
        ref2  = run_golden_model(img, k, bias=0, threshold=99)
        fast2 = run_golden_model_fast(img, k, bias=0, threshold=99)
        self.assertTrue(np.all(ref2 == 1),  "reference: pixels above threshold should fire")
        self.assertTrue(np.all(fast2 == 1), "fast: pixels above threshold should fire")


class TestKnownVectors(unittest.TestCase):
    """Deterministic expected values computed by hand / spec."""

    def test_all_zeros_image_zero_bias(self):
        """Zero image, zero bias → mac = 0 for all pixels → output 0 when threshold >= 0."""
        img = _make_image(0)
        k   = [[255,255,255],[255,255,255],[255,255,255]]
        # mac = 0 + 0 = 0; threshold=0 → 0 > 0 is False
        out = run_golden_model_fast(img, k, bias=0, threshold=0)
        self.assertTrue(np.all(out == 0))

    def test_all_zeros_image_nonzero_bias(self):
        """Zero image with bias=50 → mac = 50; output 1 iff threshold < 50."""
        img = _make_image(0)
        k   = [[0]*3]*3
        out0 = run_golden_model_fast(img, k, bias=50, threshold=49)
        out1 = run_golden_model_fast(img, k, bias=50, threshold=50)
        self.assertTrue(np.all(out0 == 1), "bias=50 > threshold=49 should fire")
        self.assertTrue(np.all(out1 == 0), "bias=50 == threshold=50 should not fire (strict >)")

    def test_identity_kernel(self):
        """Center-only kernel: output pixel = 1 iff img[r+1,c+1] + bias > threshold."""
        k   = [[0,0,0],[0,1,0],[0,0,0]]
        img = _make_ramp_image()
        bias      = 0
        threshold = 127
        out = run_golden_model_fast(img, k, bias=bias, threshold=threshold)
        # Expected: center pixel of each 3×3 patch = img[r+1, c+1] (rows/cols 1..254)
        expected = (img[1:255, 1:255].astype(np.int64) > threshold).astype(np.uint8)
        np.testing.assert_array_equal(out, expected)

    def test_20bit_wraparound(self):
        """
        Verify 20-bit mask: large MAC value wraps to small → output 0 even though
        the unwrapped value would be huge.
        9 * 255 * 255 = 585,225 < 2^20 = 1,048,576  →  no wrap for max inputs.
        Verify no wrap actually occurs (safety check for the spec claim).
        """
        img = _make_image(255)
        k   = [[255]*3]*3
        max_mac = 9 * 255 * 255   # 585,225
        self.assertLess(max_mac, _MASK_20BIT,
                        "Spec guarantees no wrap for valid 8-bit inputs")
        out = run_golden_model_fast(img, k, bias=255, threshold=max_mac + 254)
        # mac = 585,225 + 255 = 585,480; threshold = 585,479 → should fire
        out2 = run_golden_model_fast(img, k, bias=255, threshold=585_479)
        self.assertTrue(np.all(out2 == 1))
        # threshold = 585,480 → should not fire (equal, not greater)
        out3 = run_golden_model_fast(img, k, bias=255, threshold=585_480)
        self.assertTrue(np.all(out3 == 0))

    def test_scipy_cross_validation(self):
        """Cross-validate fast model against scipy.ndimage.correlate reference."""
        rng = np.random.default_rng(7)
        img = rng.integers(0, 256, (256, 256), dtype=np.uint8)
        k   = np.array([[1,2,1],[0,1,0],[1,2,1]], dtype=np.int64)
        bias, threshold = 20, 800

        fast     = run_golden_model_fast(img, k.tolist(), bias=bias, threshold=threshold)
        expected = _reference_conv(img, k, bias=bias, threshold=threshold)
        np.testing.assert_array_equal(fast, expected,
                                      err_msg="fast model diverges from scipy reference")


class TestInputValidation(unittest.TestCase):
    """_validate_inputs should raise ValueError for bad inputs."""

    def test_wrong_image_shape(self):
        img = np.zeros((128, 128), dtype=np.uint8)
        with self.assertRaises(ValueError):
            run_golden_model(img, [[1,0,0],[0,0,0],[0,0,0]], bias=0, threshold=0)

    def test_3d_image(self):
        img = np.zeros((256, 256, 3), dtype=np.uint8)
        with self.assertRaises(ValueError):
            run_golden_model_fast(img, [[1,0,0],[0,0,0],[0,0,0]], bias=0, threshold=0)

    def test_wrong_kernel_size(self):
        img = np.zeros((256, 256), dtype=np.uint8)
        with self.assertRaises(ValueError):
            run_golden_model(img, [[1,0],[0,0]], bias=0, threshold=0)

    def test_bias_out_of_range(self):
        img = np.zeros((256, 256), dtype=np.uint8)
        with self.assertRaises(ValueError):
            run_golden_model(img, [[0]*3]*3, bias=256, threshold=0)

    def test_threshold_out_of_range(self):
        img = np.zeros((256, 256), dtype=np.uint8)
        with self.assertRaises(ValueError):
            run_golden_model(img, [[0]*3]*3, bias=0, threshold=_MASK_20BIT + 1)


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
