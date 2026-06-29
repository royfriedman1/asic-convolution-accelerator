"""
Golden Model for 3x3 Convolution Accelerator
Precisely emulates the hardware's 20-bit accumulator with wrap-around.

Hardware Spec:
  - Input : 256x256 pixels, 8-bit unsigned, raster-scan order
  - Kernel : 3x3, 8-bit unsigned weights (0-255)
  - Bias   : 8-bit unsigned (0-255)
  - MAC    : sum(pixel * weight) + bias, result masked to 20-bit (wrap-around)
  - Output : 1-bit per pixel — 1 if mac_sum_20bit > threshold, else 0
  - Valid region: rows 2-255, cols 2-255 (first 2 rows/cols are pipeline flush)
  - Output size : 254x254 (valid only)
"""

import numpy as np

_MASK_20BIT = 0xFFFFF  # 2^20 - 1


def _validate_inputs(img_array: np.ndarray, matrix, bias: int, threshold: int) -> None:
    """Raise ValueError for inputs that violate the hardware spec."""
    if img_array.ndim != 2 or img_array.shape != (256, 256):
        raise ValueError(
            f"img_array must be (256, 256) grayscale; got shape {img_array.shape}"
        )
    m = np.asarray(matrix)
    if m.size != 9:
        raise ValueError(f"kernel must have exactly 9 weights; got {m.size}")
    if not (0 <= int(bias) <= 255):
        raise ValueError(f"bias must be 0-255; got {bias}")
    if not (0 <= int(threshold) <= _MASK_20BIT):
        raise ValueError(f"threshold must be 0-{_MASK_20BIT}; got {threshold}")


def run_golden_model(
    img_array: np.ndarray,
    matrix: list | np.ndarray,
    bias: int,
    threshold: int,
) -> np.ndarray:
    """
    Run the hardware-accurate golden model.

    Parameters
    ----------
    img_array  : (256, 256) uint8 grayscale image
    matrix     : 3x3 kernel weights (0-255, uint8-compatible)
    bias       : accumulator bias (0-255)
    threshold  : 20-bit comparison threshold (0-1_048_575)

    Returns
    -------
    (254, 254) uint8 binary feature map — values are 0 or 1
    """
    _validate_inputs(img_array, matrix, bias, threshold)
    img = img_array.astype(np.int64)
    weights = np.array(matrix, dtype=np.int64).reshape(3, 3)
    b = int(bias) & 0xFF
    t = int(threshold) & _MASK_20BIT

    out_h = img.shape[0] - 2
    out_w = img.shape[1] - 2
    output = np.zeros((out_h, out_w), dtype=np.uint8)

    for row in range(out_h):
        for col in range(out_w):
            window = img[row: row + 3, col: col + 3]
            mac_sum = int(np.sum(window * weights)) + b
            mac_hw = mac_sum & _MASK_20BIT   # 20-bit wrap-around
            output[row, col] = 1 if mac_hw > t else 0

    return output


def run_golden_model_fast(
    img_array: np.ndarray,
    matrix: list | np.ndarray,
    bias: int,
    threshold: int,
) -> np.ndarray:
    """
    Vectorised version — same result as run_golden_model but ~100x faster.
    Uses numpy stride tricks; suitable for real-time preview.
    """
    _validate_inputs(img_array, matrix, bias, threshold)
    img = np.ascontiguousarray(img_array, dtype=np.int64)
    weights = np.array(matrix, dtype=np.int64).reshape(3, 3)
    b = int(bias) & 0xFF
    t = int(threshold) & _MASK_20BIT

    out_h = img.shape[0] - 2
    out_w = img.shape[1] - 2

    from numpy.lib.stride_tricks import as_strided
    patch_shape = (out_h, out_w, 3, 3)
    patch_strides = (img.strides[0], img.strides[1], img.strides[0], img.strides[1])
    patches = as_strided(img, shape=patch_shape, strides=patch_strides)

    mac = np.einsum('hwkl,kl->hw', patches, weights).astype(np.int64) + b
    mac_hw = mac & _MASK_20BIT

    return (mac_hw > t).astype(np.uint8)


def run_golden_model_fast_with_sums(
    img_array: np.ndarray,
    matrix: list | np.ndarray,
    bias: int,
    threshold: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Same as run_golden_model_fast but also returns the 254×254 array of
    20-bit MAC accumulator values before threshold comparison.

    Returns
    -------
    binary_output : (254, 254) uint8  — 0 or 1
    mac_sums      : (254, 254) uint32 — 20-bit values (0–1,048,575)
    """
    _validate_inputs(img_array, matrix, bias, threshold)
    img = np.ascontiguousarray(img_array, dtype=np.int64)
    weights = np.array(matrix, dtype=np.int64).reshape(3, 3)
    b = int(bias) & 0xFF
    t = int(threshold) & _MASK_20BIT

    out_h = img.shape[0] - 2
    out_w = img.shape[1] - 2

    from numpy.lib.stride_tricks import as_strided
    patch_shape = (out_h, out_w, 3, 3)
    patch_strides = (img.strides[0], img.strides[1], img.strides[0], img.strides[1])
    patches = as_strided(img, shape=patch_shape, strides=patch_strides)

    mac = np.einsum('hwkl,kl->hw', patches, weights).astype(np.int64) + b
    mac_hw = mac & _MASK_20BIT

    return (mac_hw > t).astype(np.uint8), mac_hw.astype(np.uint32)


