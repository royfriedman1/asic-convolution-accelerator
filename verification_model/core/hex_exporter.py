"""
Hex file exporter — generates $readmemh-compatible files for Verilog testbenches.

Stimulus file layout (one byte per line, uppercase hex):
  Lines  0– 8  : 9 kernel weights  (W[0][0]..W[2][2], row-major)
  Line      9  : bias
  Lines 10–12  : threshold (little-endian, 3 bytes)
  Lines 13–65548 : 65 536 image pixels (row-major)

Scoreboard file (one entry per line, no header):
  254×254 = 64,516 raw values (0 or 1), row-major order.
  Matches the testbench output — only pixel_valid_out=1 pixels captured.
"""

from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Stimulus
# ──────────────────────────────────────────────────────────────────────────────

def export_stimulus(
    image: np.ndarray,
    weights: np.ndarray,
    bias: int,
    threshold: int,
    filepath: str,
) -> int:
    """
    Write the unified stimulus .hex file.

    Returns total number of bytes written.
    """
    weights_flat = np.array(weights, dtype=np.uint8).flatten()
    assert weights_flat.size == 9, "Kernel must be 3x3 (9 elements)"

    bias_byte = int(bias) & 0xFF
    thr = int(threshold) & 0xFFFFF   # 20-bit

    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(filepath, "w", newline="\n") as f:
        # 9 weight bytes
        for w in weights_flat:
            f.write(f"{int(w):02X}\n")
            count += 1

        # bias (1 byte)
        f.write(f"{bias_byte:02X}\n")
        count += 1

        # threshold – 3 bytes little-endian
        f.write(f"{thr & 0xFF:02X}\n")
        f.write(f"{(thr >> 8) & 0xFF:02X}\n")
        f.write(f"{(thr >> 16) & 0xFF:02X}\n")
        count += 3

        # 65 536 image pixels
        for px in image.flatten():
            f.write(f"{int(px):02X}\n")
            count += 1

    return count


# ──────────────────────────────────────────────────────────────────────────────
# Scoreboard
# ──────────────────────────────────────────────────────────────────────────────

def export_full_vectors(
    image: np.ndarray,
    weights: np.ndarray,
    bias: int,
    threshold: int,
    filepath: str,
) -> int:
    """
    Write full convolution vector data for every valid output pixel (254×254).

    One line per pixel, row-major order (rows 2-255, cols 2-255 of the 256×256 input).
    Line format matches the PE test vector style:
      {9×Pixels(hex)} {9×Weights(hex)} {Bias(8b hex)} {TH(20b hex)} {Sum(20b hex)} {Bit}

    Example line:
      01A3FF0200B4C108 01020100FFFEFF 00 186A0 12345 1

    Returns total lines written (64,516).
    """
    from numpy.lib.stride_tricks import as_strided

    weights_flat = np.array(weights, dtype=np.uint8).flatten()
    assert weights_flat.size == 9, "Kernel must be 3×3"
    bias_b  = int(bias)      & 0xFF
    thr_int = int(threshold) & 0xFFFFF

    img = np.ascontiguousarray(image, dtype=np.int64)
    w   = np.array(weights, dtype=np.int64).reshape(3, 3)
    out_h, out_w = img.shape[0] - 2, img.shape[1] - 2

    # Extract all 3×3 sliding windows as a (out_h, out_w, 3, 3) view
    patch_strides = (img.strides[0], img.strides[1], img.strides[0], img.strides[1])
    patches = as_strided(img, shape=(out_h, out_w, 3, 3), strides=patch_strides)

    # MAC computation (vectorised, hardware-accurate 20-bit wrap)
    mac    = np.einsum("hwkl,kl->hw", patches, w).astype(np.int64) + bias_b
    mac_hw = (mac & 0xFFFFF).astype(np.uint32)
    result = (mac_hw > thr_int).astype(np.uint8)

    # Flatten windows to (N, 9) for writing
    patches_u8  = patches.reshape(out_h * out_w, 9).astype(np.uint8)

    def _grp(s: str) -> str:
        """Insert '_' every 4 hex characters for readability."""
        return "_".join(s[i:i + 4] for i in range(0, len(s), 4))

    weights_hex = _grp("".join(f"{int(v):02X}" for v in weights_flat))
    thr_hex     = _grp(f"{thr_int:05X}")

    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    lines = 0
    with open(filepath, "w", newline="\n") as f:
        f.write(
            "// Format: [9 Pixels(72b)] [9 Weights(72b)] [Bias(8b)]"
            " [TH(20b)] [Sum(20b)] [Bit]\n"
        )
        for r in range(out_h):
            for c in range(out_w):
                idx    = r * out_w + c
                px_hex = _grp("".join(f"{int(patches_u8[idx, k]):02X}" for k in range(9)))
                sum_hex = _grp(f"{int(mac_hw[r, c]):05X}")
                f.write(
                    f"{px_hex} {weights_hex} {bias_b:02X} {thr_hex}"
                    f" {sum_hex} {int(result[r, c])}\n"
                )
                lines += 1

    return lines


def export_scoreboard(
    golden_254: np.ndarray,
    filepath: str,
) -> int:
    """
    Write the expected-output scoreboard file.

    Format: one result per line (0 or 1), 254×254 = 64,516 lines total.
    No header or comment lines — raw pixel values only.
    Matches the chip's actual output format — the testbench captures only
    pixel_valid_out=1 pixels (the 254×254 valid region), in row-major order.

    Returns total lines written.
    """
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    lines = 0
    with open(filepath, "w", newline="\n") as f:
        for r in range(254):
            for c in range(254):
                f.write(f"{int(golden_254[r, c])}\n")
                lines += 1

    return lines


# ──────────────────────────────────────────────────────────────────────────────
# Run info summary
# ──────────────────────────────────────────────────────────────────────────────

def export_run_info(
    run_dir: str,
    weights: np.ndarray,
    bias: int,
    threshold: int,
    source_name: str = "",
    n_frames: int = 1,
    active_pixels: int | None = None,
) -> str:
    """
    Write run_info.txt in run_dir with a human-readable summary of the run.
    Returns the path to the written file.
    """
    w = np.array(weights, dtype=np.int32).flatten()
    filepath = os.path.join(run_dir, "run_info.txt")
    with open(filepath, "w", newline="\n", encoding="utf-8") as f:
        f.write("=" * 48 + "\n")
        f.write("  ASIC Verification Suite — Run Summary\n")
        f.write("=" * 48 + "\n\n")

        f.write(f"Date / Time  : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}\n")
        if source_name:
            f.write(f"Source       : {source_name}\n")
        mode = "Video" if n_frames > 1 else "Single image"
        f.write(f"Mode         : {mode}\n")
        if n_frames > 1:
            f.write(f"Frames       : {n_frames}\n")
        f.write(f"Output size  : 254 x 254 pixels per frame\n\n")

        f.write("Convolution kernel (3x3):\n")
        for row in range(3):
            vals = "  ".join(f"{w[row * 3 + col]:4d}" for col in range(3))
            f.write(f"  [ {vals} ]\n")
        f.write("\n")

        f.write(f"Bias         : {bias}  (0x{int(bias) & 0xFF:02X})\n")
        f.write(f"Threshold    : {threshold}  (0x{int(threshold) & 0xFFFFF:05X})\n")

        if active_pixels is not None:
            total_px = n_frames * 254 * 254
            pct = 100.0 * active_pixels / total_px if total_px > 0 else 0.0
            f.write(f"\nActive pixels: {active_pixels:,} / {total_px:,}  ({pct:.2f}%)\n")

        f.write("\nFolder layout:\n")
        f.write("  stimulus/             — input .hex files  ($readmemh)\n")
        f.write("  golden/               — scoreboard .txt  (0/1 per line)\n")
        f.write("  vectors/              — full_vectors .txt  (pixels|weights|bias|TH|sum|bit)\n")
        f.write("  run_params.json       — kernel config (auto-loaded by Analyst)\n")
        f.write("  visual_input/         — PNG images (source input frames)\n")
        f.write("  visual_golden/        — PNG images (golden output frames)\n")
        f.write("  actual/               — DUT output .txt files (filled by testbench)\n")
    return filepath


# ──────────────────────────────────────────────────────────────────────────────
# run_params.json — machine-readable sidecar for Analyst auto-load
# ──────────────────────────────────────────────────────────────────────────────

def export_run_params(
    directory: str,
    weights: np.ndarray,
    bias: int,
    threshold: int,
    preset_name: str = "CUSTOM",
) -> str:
    """
    Write run_params.json in *directory*.
    The Analyst widget auto-loads this file when the user imports a golden
    scoreboard from the same folder, so the kernel config is always consistent.
    Returns the path to the written file.
    """
    data = {
        "preset_name": preset_name,
        "weights": np.array(weights, dtype=int).reshape(3, 3).tolist(),
        "bias": int(bias),
        "threshold": int(threshold),
        "exported": datetime.now().isoformat(timespec="seconds"),
    }
    path = os.path.join(directory, "run_params.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Run-folder helper (mirrors the layout of existing manual_test.py)
# ──────────────────────────────────────────────────────────────────────────────

def create_run_folder(base: str = ".") -> tuple[str, str, str, str, str, str]:
    """
    Create a timestamped run folder with sub-directories.
    Returns (run_dir, stimulus_path, scoreboard_path, vectors_dir, visual_input_dir, visual_golden_dir).
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(base, f"gui_run_{ts}")
    stim_dir          = os.path.join(run_dir, "stimulus")
    score_dir         = os.path.join(run_dir, "golden")
    vectors_dir       = os.path.join(run_dir, "vectors")
    visual_input_dir  = os.path.join(run_dir, "visual_input")
    visual_golden_dir = os.path.join(run_dir, "visual_golden")

    for d in (stim_dir, score_dir, vectors_dir, visual_input_dir, visual_golden_dir):
        os.makedirs(d, exist_ok=True)

    stim_path  = os.path.join(stim_dir,  "input_0.hex")
    score_path = os.path.join(score_dir, "expected_0.txt")

    return run_dir, stim_path, score_path, vectors_dir, visual_input_dir, visual_golden_dir
