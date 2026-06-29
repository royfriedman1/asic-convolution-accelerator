"""
ReportExporter — generates a self-contained HTML verification report.

The report embeds all images as base64 data URIs so it can be
opened on any machine without extra files, and printed to PDF
directly from any browser (File → Print → Save as PDF).

Usage:
    from ui.report_exporter import build_html_report, save_report
    html = build_html_report(config)
    save_report(html, "/path/to/report.html")
"""
from __future__ import annotations

import base64
import datetime
import io
import os

import numpy as np


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _array_to_b64_png(arr: np.ndarray | None, scale: int = 1) -> str:
    """
    Convert a uint8 numpy array (H×W or H×W×3) to a base64-encoded PNG
    suitable for use as <img src="data:image/png;base64,...">
    Returns an empty string if arr is None.
    """
    if arr is None:
        return ""
    try:
        import cv2
        if arr.ndim == 2:
            img = arr
        else:
            img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
        if scale != 1:
            h, w = img.shape[:2]
            img = cv2.resize(img, (w * scale, h * scale),
                             interpolation=cv2.INTER_NEAREST)
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            return ""
        return base64.b64encode(buf.tobytes()).decode("ascii")
    except ImportError:
        pass
    try:
        from PIL import Image
        if arr.ndim == 2:
            img = Image.fromarray(arr, mode="L")
        else:
            img = Image.fromarray(arr, mode="RGB")
        if scale != 1:
            img = img.resize((img.width * scale, img.height * scale),
                              resample=Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except ImportError:
        return ""


def _img_tag(b64: str, alt: str = "", width: str = "256px") -> str:
    if not b64:
        return f'<div class="no-img">{alt or "No image"}</div>'
    return (
        f'<img src="data:image/png;base64,{b64}" '
        f'alt="{alt}" style="width:{width}; image-rendering:pixelated; '
        f'border:1px solid #3A3A3C; border-radius:4px;" />'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main builder
# ──────────────────────────────────────────────────────────────────────────────

def build_html_report(cfg: dict) -> str:
    """
    Build and return a self-contained HTML report string.

    Expected keys in cfg (all optional):
        golden        : np.ndarray  254×254 binary
        chip          : np.ndarray  254×254 binary
        mismatch_rgb  : np.ndarray  256×256×3 RGB
        original      : np.ndarray  256×256 grayscale
        weights       : list[list[int]]  3×3
        bias          : int
        threshold     : int
        preset_name   : str
        golden_source : str  "generator"|"external+params"|"external"|"none"
        match_rate    : float
        errors        : int
        total_valid   : int
        metrics       : dict  {gate_count, area, speed, power_total}
        log_lines     : list[str]
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    # Images
    golden_arr = cfg.get("golden")
    chip_arr   = cfg.get("chip")
    orig_arr   = cfg.get("original")
    mm_arr     = cfg.get("mismatch_rgb")

    # Convert binary 254×254 arrays to grayscale display images
    if golden_arr is not None and golden_arr.shape == (254, 254):
        g256 = golden_arr * 255
    else:
        g256 = golden_arr

    if chip_arr is not None and chip_arr.shape == (254, 254):
        c256 = chip_arr * 255
    else:
        c256 = chip_arr

    b64_orig   = _array_to_b64_png(orig_arr,   scale=2)
    b64_golden = _array_to_b64_png(g256,        scale=2)
    b64_chip   = _array_to_b64_png(c256,        scale=2)
    b64_mm     = _array_to_b64_png(mm_arr,      scale=2)

    # Kernel table
    weights = cfg.get("weights") or [[0]*3]*3
    bias      = cfg.get("bias",      0)
    threshold = cfg.get("threshold", 2000)
    preset    = cfg.get("preset_name", "CUSTOM")

    # Kernel source badge
    _src = cfg.get("golden_source", "none")
    if _src == "generator":
        _src_badge = (
            '<span style="color:#34C759;font-weight:bold;">&#10003; Generator</span>'
            '<span style="color:#6E6E73;font-size:10px;"> — params match golden output</span>'
        )
    elif _src == "external+params":
        _src_badge = (
            '<span style="color:#00ADEF;font-weight:bold;">&#10003; External + run_params.json</span>'
            '<span style="color:#6E6E73;font-size:10px;"> — params auto-loaded from sidecar</span>'
        )
    elif _src == "external":
        _src_badge = (
            '<span style="color:#FF9F0A;font-weight:bold;">&#9888; External (no params file)</span>'
            '<span style="color:#6E6E73;font-size:10px;"> — params reflect current Generator settings</span>'
        )
    else:
        _src_badge = '<span style="color:#8A8A8E;">—</span>'

    def _kernel_row(vals):
        cells = "".join(f'<td class="kw">{v}</td>' for v in vals)
        return f"<tr>{cells}</tr>"

    kernel_rows = "\n".join(_kernel_row(row) for row in weights)

    # Stats
    match_rate  = cfg.get("match_rate")
    errors      = cfg.get("errors")
    total_valid = cfg.get("total_valid")

    if match_rate is not None:
        stats_html = f"""
        <tr><td>Total Valid Pixels</td><td>{total_valid:,}</td></tr>
        <tr><td>Matching Pixels</td>
            <td style="color:#34C759">{(total_valid - errors):,}</td></tr>
        <tr><td>Mismatches</td>
            <td style="color:{'#34C759' if errors == 0 else '#FF453A'}">{errors:,}</td></tr>
        <tr><td>Match Rate</td>
            <td style="color:{'#34C759' if errors == 0 else '#FF9F0A'}">
                <strong>{match_rate:.4f}%</strong></td></tr>
        """
        verdict = (
            '<span style="color:#34C759;font-size:18px;">✓ PASS — No mismatches</span>'
            if errors == 0 else
            f'<span style="color:#FF453A;font-size:18px;">✗ FAIL — {errors:,} mismatch{"es" if errors != 1 else ""}</span>'
        )
    else:
        stats_html = "<tr><td colspan='2' style='color:#8A8A8E'>No comparison data</td></tr>"
        verdict    = '<span style="color:#8A8A8E">No comparison run</span>'

    # Synthesis metrics
    metrics = cfg.get("metrics") or {}
    def _mval(k, unit=""):
        v = metrics.get(k, "—")
        if v and v != "—" and unit:
            return f"{v} {unit}"
        return v if v else "—"

    def _mrows(pairs):
        return "\n".join(
            f"<tr><td>{label}</td><td>{_mval(key, unit)}</td></tr>"
            for label, key, unit in pairs
        )

    _um2 = "\u03bcm\u00b2"   # μm² — defined outside f-string to avoid backslash-in-fstring error
    _sec_style = (
        'color:#8A8A8E; font-size:10px; text-transform:uppercase; '
        'padding:8px 10px 2px; letter-spacing:1px;'
    )
    metrics_rows = (
        f'<tr><td colspan="2" style="{_sec_style}">Area &amp; Cells</td></tr>'
        + _mrows([
            ("Gate Count",      "gate_count",  "kGE"),
            ("Cell Count",      "cell_count",  "cells"),
            ("Seq Cells (FF)",  "ff_count",    "FFs"),
            ("Core Area",       "area",        _um2),
            ("Utilization",     "utilization", "%"),
        ])
        + f'<tr><td colspan="2" style="{_sec_style}">Timing</td></tr>'
        + _mrows([
            ("Max Frequency",   "speed",        "MHz"),
            ("Clock Period",    "clock_period", "ns"),
            ("WNS",             "wns",          "ns"),
            ("Critical Path",   "crit_path",    "ns"),
        ])
        + f'<tr><td colspan="2" style="{_sec_style}">Power</td></tr>'
        + _mrows([
            ("Total Power",     "power_total",  "mW"),
            ("Dynamic Power",   "dynamic_pwr",  "mW"),
            ("Leakage Power",   "leakage_pwr",  "mW"),
        ])
    )

    # Log entries
    log_lines = cfg.get("log_lines") or []
    if log_lines:
        log_html = "".join(
            f'<div class="log-line log-{_level_class(l)}">{l}</div>'
            for l in log_lines[-100:]   # last 100 entries
        )
    else:
        log_html = '<div class="log-line log-info">[No log entries]</div>'

    # Assemble HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>ASIC Verification Report — {now}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px;
         background: #0F0F12; color: #D0D0D5; line-height: 1.5; }}
  h1 {{ font-size: 22px; color: #00ADEF; margin-bottom: 4px; }}
  h2 {{ font-size: 14px; color: #00ADEF; letter-spacing: 2px;
        text-transform: uppercase; margin: 20px 0 8px; border-bottom: 1px solid #2A2A2E;
        padding-bottom: 4px; }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 32px 24px; }}
  .header {{ border-bottom: 2px solid #00ADEF; padding-bottom: 16px; margin-bottom: 24px; }}
  .subtitle {{ color: #6E6E73; font-size: 11px; margin-top: 4px; }}
  .meta {{ color: #5A5A60; font-size: 11px; margin-top: 8px; }}
  .verdict {{ margin: 16px 0; }}

  /* images */
  .img-grid {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; }}
  .img-cell {{ text-align: center; }}
  .img-cell .lbl {{ font-size: 10px; color: #6E6E73; letter-spacing: 1px;
                    text-transform: uppercase; margin-top: 4px; }}
  .no-img {{ width: 512px; height: 512px; background: #1A1A1E; display: flex;
             align-items: center; justify-content: center; color: #3A3A3C;
             font-size: 11px; border: 1px solid #2A2A2E; border-radius: 4px; }}

  /* tables */
  table {{ border-collapse: collapse; width: 100%; }}
  td {{ padding: 5px 10px; border-bottom: 1px solid #222226; font-size: 12px; }}
  tr:last-child td {{ border-bottom: none; }}
  .info-tbl td:first-child {{ color: #8A8A8E; width: 160px; }}
  .kw {{ text-align: center; background: #1C1C20; border: 1px solid #2A2A2E;
         width: 48px; height: 36px; font-size: 14px; font-weight: bold;
         color: #00ADEF; font-family: monospace; padding: 0; }}

  /* two-col layout */
  .cols {{ display: flex; gap: 24px; }}
  .col {{ flex: 1; }}

  /* log */
  .log-box {{ background: #0D0D10; border: 1px solid #2A2A2E; border-radius: 4px;
              padding: 10px; max-height: 280px; overflow-y: auto; }}
  .log-line {{ font-family: 'Consolas', monospace; font-size: 11px;
               padding: 1px 0; white-space: pre-wrap; }}
  .log-ok    {{ color: #34C759; }}
  .log-error {{ color: #FF453A; }}
  .log-warn  {{ color: #FF9F0A; }}
  .log-info  {{ color: #8A8A8E; }}

  /* section box */
  .section {{ background: #141418; border: 1px solid #222226; border-radius: 6px;
              padding: 16px; margin-bottom: 16px; }}

  @media print {{
    body {{ background: #fff; color: #111; }}
    h1, h2 {{ color: #0055AA; }}
    .log-box {{ max-height: none; }}
  }}
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <div class="header">
    <h1>ASIC Verification Report</h1>
    <div class="subtitle">
      Area &amp; Power Optimized Hardware Accelerator for Single Convolutional Kernel
    </div>
    <div class="meta">
      Tel Aviv University — Electrical Engineering &nbsp;|&nbsp;
      Generated: {now}
    </div>
  </div>

  <!-- Verdict -->
  <div class="section verdict">
    <h2>Verdict</h2>
    {verdict}
  </div>

  <!-- Visual Comparison -->
  <div class="section">
    <h2>Visual Comparison</h2>
    <div class="img-grid">
      <div class="img-cell">
        {_img_tag(b64_orig,   "Original Input")}
        <div class="lbl">Original Input</div>
      </div>
      <div class="img-cell">
        {_img_tag(b64_golden, "Golden Model")}
        <div class="lbl">Golden Model</div>
      </div>
      <div class="img-cell">
        {_img_tag(b64_chip,   "Chip DUT")}
        <div class="lbl">Chip DUT</div>
      </div>
      <div class="img-cell">
        {_img_tag(b64_mm,     "Mismatch Map")}
        <div class="lbl">Mismatch Map<br>
          <span style="color:#34C759">■</span> Match &nbsp;
          <span style="color:#FF3344">■</span> Mismatch &nbsp;
          <span style="color:#1C1C3A">■</span> Invalid</div>
      </div>
    </div>
  </div>

  <!-- Stats + Kernel side by side -->
  <div class="cols">
    <div class="col section">
      <h2>Comparison Results</h2>
      <table class="info-tbl">{stats_html}</table>
    </div>

    <div class="col section">
      <h2>Kernel Configuration</h2>
      <table style="width:auto; margin-bottom:10px;">
        {kernel_rows}
      </table>
      <table class="info-tbl">
        <tr><td>Source</td>    <td>{_src_badge}</td></tr>
        <tr><td>Preset</td>    <td>{preset}</td></tr>
        <tr><td>Bias</td>      <td>{bias}</td></tr>
        <tr><td>Threshold</td><td>{threshold}  (0x{threshold:05X})</td></tr>
      </table>
    </div>
  </div>

  <!-- Synthesis Metrics -->
  <div class="section">
    <h2>Synthesis Metrics</h2>
    <table class="info-tbl" style="max-width:420px;">{metrics_rows}</table>
  </div>

  <!-- Activity Log -->
  <div class="section">
    <h2>Activity Log</h2>
    <div class="log-box">
      {log_html}
    </div>
  </div>

  <!-- Footer -->
  <div style="text-align:center; color:#3A3A3C; font-size:10px; margin-top:24px;">
    ASIC Verification Suite v1.0  —  Tel Aviv University EE  —  {now}
  </div>

</div>
</body>
</html>
"""
    return html


def save_report(html: str, path: str) -> None:
    """Write the HTML report to a file."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def _level_class(line: str) -> str:
    """Map a log line to a CSS class based on its level tag."""
    u = line.upper()
    if "OK" in u[:20]:    return "ok"
    if "ERROR" in u[:20]: return "error"
    if "WARN" in u[:20]:  return "warn"
    return "info"
