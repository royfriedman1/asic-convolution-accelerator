"""
Icon generator for ASIC Verification Suite.
Creates a multi-size ICO file with a stylized chip design.
Writes ICO binary manually (PIL's ICO encoder is limited to 1 size).
Run once:  python create_icon.py
"""

import io
import struct
import math
from PIL import Image, ImageDraw, ImageFont

# ── colour palette ─────────────────────────────────────────────────────────────
BG       = (26,  26,  27)
CARD     = (35,  35,  37)
CYAN     = (0,  173, 239)
CYAN_DIM = (0,  100, 140)
WHITE    = (255, 255, 255)
GREY     = (120, 120, 125)


def _draw_rounded_rect(draw, xy, radius, fill, outline=None, outline_width=1):
    draw.rounded_rectangle(list(xy), radius=radius, fill=fill,
                           outline=outline, width=outline_width)


def make_icon(size: int) -> Image.Image:
    """Draw a single-size icon frame and return an RGBA Image."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s    = size
    pad  = max(2, s // 16)

    # ── rounded background ────────────────────────────────────────────────────
    r_bg = max(4, s // 8)
    _draw_rounded_rect(draw, [pad, pad, s - pad, s - pad],
                       radius=r_bg, fill=BG,
                       outline=CYAN, outline_width=max(1, s // 64))

    # ── inner chip body ───────────────────────────────────────────────────────
    margin = s * 0.22
    chip_l, chip_t = margin, margin
    chip_r, chip_b = s - margin, s - margin
    r_chip = max(3, s // 12)
    _draw_rounded_rect(draw, [chip_l, chip_t, chip_r, chip_b],
                       radius=r_chip, fill=CARD,
                       outline=CYAN, outline_width=max(1, s // 48))

    # ── pin stubs ─────────────────────────────────────────────────────────────
    n_pins  = 4
    pin_len = s * 0.10
    pin_w   = max(1, s * 0.025)
    pin_gap = (chip_b - chip_t) / (n_pins + 1)

    for i in range(1, n_pins + 1):
        cy = chip_t + i * pin_gap
        draw.rectangle([pad + 1, cy - pin_w / 2, chip_l, cy + pin_w / 2], fill=CYAN)
        draw.rectangle([chip_r, cy - pin_w / 2, s - pad - 1, cy + pin_w / 2], fill=CYAN)

    pin_gap_h = (chip_r - chip_l) / (n_pins + 1)
    for i in range(1, n_pins + 1):
        cx = chip_l + i * pin_gap_h
        draw.rectangle([cx - pin_w / 2, pad + 1, cx + pin_w / 2, chip_t], fill=CYAN)
        draw.rectangle([cx - pin_w / 2, chip_b, cx + pin_w / 2, s - pad - 1], fill=CYAN)

    # ── 3×3 convolution kernel grid ──────────────────────────────────────────
    cx_c  = s / 2
    cy_c  = s / 2
    span  = (chip_r - chip_l) * 0.55
    step  = span / 2
    dot_r = max(2, s * 0.042)
    lw    = max(1, int(s * 0.016))

    x0_ln = cx_c - step - dot_r * 0.4
    x1_ln = cx_c + step + dot_r * 0.4
    y0_ln = cy_c - step - dot_r * 0.4
    y1_ln = cy_c + step + dot_r * 0.4

    for row in range(3):
        gy = cy_c + (row - 1) * step
        draw.rectangle([x0_ln, gy - lw / 2, x1_ln, gy + lw / 2], fill=CYAN_DIM)
    for col in range(3):
        gx = cx_c + (col - 1) * step
        draw.rectangle([gx - lw / 2, y0_ln, gx + lw / 2, y1_ln], fill=CYAN_DIM)

    for row in range(3):
        for col in range(3):
            gx = cx_c + (col - 1) * step
            gy = cy_c + (row - 1) * step
            colour = CYAN if (row == 1 and col == 1) else CYAN_DIM
            draw.ellipse([gx - dot_r, gy - dot_r, gx + dot_r, gy + dot_r], fill=colour)

    # ── "ASIC" text (only at larger sizes) ────────────────────────────────────
    if size >= 48:
        font_size = max(8, int(s * 0.13))
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

        text = "ASIC"
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = (s - tw) / 2
        ty = chip_b + (s - pad - chip_b - th) / 2 - bbox[1]
        draw.text((tx, ty), text, font=font, fill=CYAN)

    return img


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def write_ico(frames_with_sizes: list, out_path: str):
    """
    Write a proper multi-size ICO file.
    frames_with_sizes: list of (size_int, Image)  — all RGBA
    ICO stores sizes ≥ 256 as PNG; smaller ones also as PNG (Vista+ compatible).
    """
    n = len(frames_with_sizes)

    # Build PNG payloads
    payloads = []
    for sz, img in frames_with_sizes:
        payloads.append((sz, _png_bytes(img)))

    # Header: WORD reserved=0, WORD type=1, WORD count=n
    header = struct.pack("<HHH", 0, 1, n)

    # Each ICONDIRENTRY: 16 bytes
    # BYTE width (0 means 256), BYTE height, BYTE colourCount=0, BYTE reserved=0
    # WORD planes=1, WORD bitCount=32, DWORD sizeInBytes, DWORD fileOffset
    entry_size  = 16
    header_size = 6 + n * entry_size
    offset      = header_size

    entries = b""
    for sz, data in payloads:
        w = sz if sz < 256 else 0
        h = sz if sz < 256 else 0
        entries += struct.pack("<BBBBHHII",
                               w, h,    # width, height (0 = 256)
                               0, 0,    # colourCount, reserved
                               1, 32,   # planes, bitCount
                               len(data), offset)
        offset += len(data)

    with open(out_path, "wb") as f:
        f.write(header)
        f.write(entries)
        for _, data in payloads:
            f.write(data)


def main():
    sizes  = [16, 32, 48, 64, 128, 256]
    frames = [(sz, make_icon(sz)) for sz in sizes]

    out_path = "app_icon.ico"
    write_ico(frames, out_path)

    import os
    sz_kb = os.path.getsize(out_path) / 1024
    print(f"Icon saved: {out_path}  ({sz_kb:.1f} KB, {len(sizes)} sizes)")


if __name__ == "__main__":
    main()
