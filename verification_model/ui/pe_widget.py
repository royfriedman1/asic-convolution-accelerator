"""
PE Stimulus Generator Mode — Pre-Simulation Panel
Generates randomised PE (Processing Element) unit-test vectors.

Output format per line:
    {9×Pixels (hex)} {9×Weights (hex)} {Bias (hex)} {Threshold (hex)} {ExpectedSum (hex)} {ExpectedBit (1)}

Based on random_pe_test.py — now fully configurable from the GUI.
"""

from __future__ import annotations
import os
import numpy as np
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QLabel, QSpinBox,
    QFileDialog, QSizePolicy, QFrame, QTextEdit,
    QCheckBox, QApplication,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QFont

from ui.loading_overlay import LoadingOverlay


class PEWidget(QWidget):

    sig_status = pyqtSignal(str, str)

    _C_OK   = "#00e880"
    _C_ERR  = "#f04040"
    _C_INFO = "#d8a800"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_output_path: str = ""
        self._cancel_loading = False
        self._build_ui()
        self._overlay = LoadingOverlay(self)
        self._overlay.sig_cancel.connect(self._on_cancel)

    # ══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.setMinimumWidth(820)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 8, 14, 8)
        root.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("header_bar")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(0, 0, 0, 0)
        t1 = QLabel("PE STIMULUS")
        t1.setObjectName("mode_title")
        t2 = QLabel("PROCESSING ELEMENT UNIT-TEST VECTOR GENERATOR")
        t2.setObjectName("mode_subtitle")
        hdr_lay.addWidget(t1)
        hdr_lay.addSpacing(12)
        hdr_lay.addWidget(t2, alignment=Qt.AlignmentFlag.AlignBottom)
        hdr_lay.addStretch()
        root.addWidget(hdr)

        # ── Main content row ───────────────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(10)
        cols.addWidget(self._build_config_panel(), stretch=3)
        cols.addWidget(self._build_preview_panel(), stretch=4)
        root.addLayout(cols, stretch=1)

        # ── Generate bar ───────────────────────────────────────────────────
        root.addWidget(self._build_generate_bar())

    # ── Config panel ──────────────────────────────────────────────────────────

    def _build_config_panel(self) -> QGroupBox:
        grp = QGroupBox("VECTOR CONFIGURATION")
        grp.setMinimumWidth(300)
        lay = QVBoxLayout(grp)
        lay.setSpacing(8)
        lay.setContentsMargins(12, 16, 12, 10)

        def _row_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("lbl_section")
            return lbl

        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(1, 1)

        # NUM_VECTORS
        grid.addWidget(_row_label("NUM VECTORS"), 0, 0)
        self._num_vec_sb = QSpinBox()
        self._num_vec_sb.setRange(1, 1_000_000)
        self._num_vec_sb.setValue(1000)
        self._num_vec_sb.setSingleStep(100)
        self._num_vec_sb.setFixedHeight(32)
        self._num_vec_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(self._num_vec_sb, 0, 1)

        # ACC_WIDTH
        grid.addWidget(_row_label("ACC WIDTH (bits)"), 1, 0)
        self._acc_width_sb = QSpinBox()
        self._acc_width_sb.setRange(8, 32)
        self._acc_width_sb.setValue(20)
        self._acc_width_sb.setFixedHeight(32)
        self._acc_width_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        grid.addWidget(self._acc_width_sb, 1, 1)

        lay.addLayout(grid)

        sep1 = QFrame(); sep1.setObjectName("nav_separator"); sep1.setFixedHeight(1)
        lay.addWidget(sep1)

        # ── Bias config ───────────────────────────────────────────────────────
        bias_lbl = QLabel("BIAS")
        bias_lbl.setObjectName("lbl_section")
        lay.addWidget(bias_lbl)

        bias_row = QHBoxLayout()
        bias_row.setSpacing(8)
        self._bias_random_cb = QCheckBox("Random per vector")
        self._bias_random_cb.setChecked(False)
        self._bias_random_cb.toggled.connect(self._on_bias_mode)

        self._bias_val_sb = QSpinBox()
        self._bias_val_sb.setRange(0, 255)
        self._bias_val_sb.setValue(146)
        self._bias_val_sb.setFixedHeight(32)
        self._bias_val_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._bias_val_sb.setToolTip("Fixed bias value (0–255)")

        bias_row.addWidget(self._bias_random_cb)
        bias_row.addWidget(self._bias_val_sb)
        lay.addLayout(bias_row)

        # ── Threshold config ──────────────────────────────────────────────────
        thr_lbl = QLabel("THRESHOLD  (20-bit)")
        thr_lbl.setObjectName("lbl_section")
        lay.addWidget(thr_lbl)

        thr_row = QHBoxLayout()
        thr_row.setSpacing(8)
        self._thr_random_cb = QCheckBox("Random per vector")
        self._thr_random_cb.setChecked(False)
        self._thr_random_cb.toggled.connect(self._on_thr_mode)

        self._thr_val_sb = QSpinBox()
        self._thr_val_sb.setRange(0, 1_048_575)
        self._thr_val_sb.setValue(146431)
        self._thr_val_sb.setFixedHeight(32)
        self._thr_val_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._thr_val_sb.setToolTip("Fixed threshold value (0–1 048 575)")

        thr_row.addWidget(self._thr_random_cb)
        thr_row.addWidget(self._thr_val_sb)
        lay.addLayout(thr_row)

        sep2 = QFrame(); sep2.setObjectName("nav_separator"); sep2.setFixedHeight(1)
        lay.addWidget(sep2)

        # ── Pixel range ───────────────────────────────────────────────────────
        px_lbl = QLabel("PIXEL RANGE  (uint8)")
        px_lbl.setObjectName("lbl_section")
        lay.addWidget(px_lbl)

        px_row = QHBoxLayout()
        px_row.setSpacing(6)
        px_row.addWidget(QLabel("Min"))
        self._px_min_sb = QSpinBox()
        self._px_min_sb.setRange(0, 255)
        self._px_min_sb.setValue(0)
        self._px_min_sb.setFixedHeight(30)
        self._px_min_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        px_row.addWidget(self._px_min_sb)
        px_row.addWidget(QLabel("Max"))
        self._px_max_sb = QSpinBox()
        self._px_max_sb.setRange(0, 255)
        self._px_max_sb.setValue(255)
        self._px_max_sb.setFixedHeight(30)
        self._px_max_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        px_row.addWidget(self._px_max_sb)
        lay.addLayout(px_row)

        # ── Weight range ──────────────────────────────────────────────────────
        w_lbl = QLabel("WEIGHT RANGE  (uint8)")
        w_lbl.setObjectName("lbl_section")
        lay.addWidget(w_lbl)

        w_row = QHBoxLayout()
        w_row.setSpacing(6)
        w_row.addWidget(QLabel("Min"))
        self._w_min_sb = QSpinBox()
        self._w_min_sb.setRange(0, 255)
        self._w_min_sb.setValue(0)
        self._w_min_sb.setFixedHeight(30)
        self._w_min_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        w_row.addWidget(self._w_min_sb)
        w_row.addWidget(QLabel("Max"))
        self._w_max_sb = QSpinBox()
        self._w_max_sb.setRange(0, 255)
        self._w_max_sb.setValue(255)
        self._w_max_sb.setFixedHeight(30)
        self._w_max_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        w_row.addWidget(self._w_max_sb)
        lay.addLayout(w_row)

        lay.addStretch()
        return grp

    # ── Preview panel ─────────────────────────────────────────────────────────

    def _build_preview_panel(self) -> QGroupBox:
        grp = QGroupBox("PREVIEW  —  first 12 vectors (live)")
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(10, 14, 10, 8)
        lay.setSpacing(6)

        header_lbl = QLabel(
            "Format:  Pixels(9×8b) _ Weights(9×8b) _ Bias(8b) _ Threshold(20b)   "
            "→   ExpSum(20b) _ Bit(1b)"
        )
        header_lbl.setObjectName("img_info")
        lay.addWidget(header_lbl)

        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setFont(QFont("Consolas", 9))
        self._preview_text.setObjectName("weight_cell")
        self._preview_text.setMinimumHeight(180)
        lay.addWidget(self._preview_text, stretch=1)

        preview_btn = QPushButton("↺  Refresh Preview")
        preview_btn.setObjectName("btn_warn")
        preview_btn.setFixedHeight(32)
        preview_btn.clicked.connect(self._refresh_preview)
        lay.addWidget(preview_btn)

        # Stats
        self._stats_lbl = QLabel("—")
        self._stats_lbl.setObjectName("img_info")
        lay.addWidget(self._stats_lbl)

        return grp

    # ── Generate bar ──────────────────────────────────────────────────────────

    def _build_generate_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("img_frame")
        bar.setMinimumHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(14)

        lbl = QLabel("PE UNIT-TEST EXPORT")
        lbl.setObjectName("lbl_section")
        lay.addWidget(lbl)

        lay.addStretch()

        self._gen_btn = QPushButton("  Generate & Export  (.hex)")
        self._gen_btn.setObjectName("btn_export")
        self._gen_btn.setMinimumSize(QSize(280, 36))
        self._gen_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._gen_btn.setToolTip(
            "Generates PE test vectors and writes to a timestamped folder:\n"
            "  pe_unit_test_TIMESTAMP/pe_test_vectors.hex"
        )
        self._gen_btn.clicked.connect(self._generate_and_export)
        lay.addWidget(self._gen_btn)

        self._export_info = QLabel("")
        self._export_info.setObjectName("lbl_stat_value")
        self._export_info.setMinimumWidth(180)
        lay.addWidget(self._export_info)

        return bar

    # ══════════════════════════════════════════════════════════════════════════
    # Slots
    # ══════════════════════════════════════════════════════════════════════════

    def _on_bias_mode(self, random: bool):
        self._bias_val_sb.setEnabled(not random)

    def _on_thr_mode(self, random: bool):
        self._thr_val_sb.setEnabled(not random)

    def _on_cancel(self):
        self._cancel_loading = True
        self._overlay.hide_loading()
        self._gen_btn.setEnabled(True)
        self.sig_status.emit("Generation cancelled.", self._C_INFO)

    # ══════════════════════════════════════════════════════════════════════════
    # Core logic
    # ══════════════════════════════════════════════════════════════════════════

    def _build_vector(self, acc_mask: int, px_lo: int, px_hi: int,
                       w_lo: int, w_hi: int,
                       fixed_bias: int | None, fixed_thr: int | None,
                       rng: np.random.Generator) -> str:
        """Return one formatted line (no newline)."""
        lo_px = min(px_lo, px_hi); hi_px = max(px_lo, px_hi) + 1
        lo_w  = min(w_lo, w_hi);   hi_w  = max(w_lo, w_hi)  + 1

        pixels  = rng.integers(lo_px, hi_px, 9, dtype=np.uint8)
        weights = rng.integers(lo_w,  hi_w,  9, dtype=np.uint8)
        bias    = int(rng.integers(0, 256)) if fixed_bias is None else fixed_bias
        thr     = int(rng.integers(0, 1 << 20)) if fixed_thr is None else fixed_thr

        mac_sum   = int(np.sum(pixels.astype(np.int32) * weights.astype(np.int32))) + bias
        final_sum = mac_sum & acc_mask
        result    = 1 if final_sum > thr else 0

        px_hex = "".join(f"{p:02X}" for p in pixels)
        w_hex  = "".join(f"{w:02X}" for w in weights)
        return f"{px_hex} {w_hex} {bias:02X} {thr:05X} {final_sum:05X} {result:01X}"

    def _collect_params(self):
        """Return (n, acc_mask, px_lo, px_hi, w_lo, w_hi, fixed_bias, fixed_thr)."""
        n        = self._num_vec_sb.value()
        acc_mask = (1 << self._acc_width_sb.value()) - 1
        px_lo    = self._px_min_sb.value()
        px_hi    = self._px_max_sb.value()
        w_lo     = self._w_min_sb.value()
        w_hi     = self._w_max_sb.value()
        fixed_b  = None if self._bias_random_cb.isChecked() else self._bias_val_sb.value()
        fixed_t  = None if self._thr_random_cb.isChecked()  else self._thr_val_sb.value()
        return n, acc_mask, px_lo, px_hi, w_lo, w_hi, fixed_b, fixed_t

    def _refresh_preview(self):
        n, acc_mask, px_lo, px_hi, w_lo, w_hi, fixed_b, fixed_t = self._collect_params()
        rng = np.random.default_rng()
        lines = [
            "// Format: Pixels(9×8b)_Weights(9×8b)_Bias(8b)_Threshold(20b) → ExpSum_Bit",
        ]
        ones = 0
        preview_n = min(12, n)
        for _ in range(preview_n):
            line = self._build_vector(acc_mask, px_lo, px_hi, w_lo, w_hi,
                                       fixed_b, fixed_t, rng)
            lines.append(line)
            if line.endswith("_1"):
                ones += 1
        self._preview_text.setPlainText("\n".join(lines))
        self._stats_lbl.setText(
            f"Preview: {preview_n} vectors  |  "
            f"ones={ones}  zeros={preview_n - ones}  "
            f"(ratio: {ones / preview_n * 100:.1f}%)"
        )

    def _generate_and_export(self):
        base = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if not base:
            return

        n, acc_mask, px_lo, px_hi, w_lo, w_hi, fixed_b, fixed_t = self._collect_params()

        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder  = os.path.join(base, f"pe_unit_test_{ts}")
        os.makedirs(folder, exist_ok=True)
        out_path = os.path.join(folder, "pe_test_vectors.hex")

        self._cancel_loading = False
        self._gen_btn.setEnabled(False)
        self._overlay.show_loading(
            "Generating PE Vectors…",
            f"0 / {n} vectors",
            determinate=True,
            max_val=n,
            cancellable=True,
        )
        QApplication.processEvents()

        rng   = np.random.default_rng()
        ones  = 0
        chunk = max(1, n // 200)   # update ~200 times

        try:
            with open(out_path, "w") as f:
                f.write(
                    "// Format: [9 Pixels (72b)]_[9 Weights (72b)]_[Bias (8b)]_"
                    "[Threshold (20b)] | [Expected_Sum (20b)] [Expected_Bit (1b)]\n"
                )
                for i in range(n):
                    if self._cancel_loading:
                        return
                    line = self._build_vector(acc_mask, px_lo, px_hi, w_lo, w_hi,
                                              fixed_b, fixed_t, rng)
                    f.write(line + "\n")
                    if line.endswith("_1"):
                        ones += 1
                    if i % chunk == 0:
                        self._overlay.set_progress(i + 1, f"{i + 1} / {n} vectors")
                        if i % (chunk * 10) == 0:
                            QApplication.processEvents()

            self._overlay.hide_loading()
            self._gen_btn.setEnabled(True)
            zeros      = n - ones
            ones_pct   = ones  / n * 100
            zeros_pct  = zeros / n * 100
            self._export_info.setText(
                f"✔  {n:,} vectors  →  {os.path.basename(folder)}"
            )
            self._stats_lbl.setText(
                f"Generated: {n:,} vectors  |  "
                f"ones={ones:,} ({ones_pct:.1f}%)  "
                f"zeros={zeros:,} ({zeros_pct:.1f}%)"
            )
            self._last_output_path = out_path
            self.sig_status.emit(
                f"PE export complete — {n:,} vectors → {out_path}", self._C_OK
            )
            self._refresh_preview()
        except Exception as exc:
            self._overlay.hide_loading()
            self._gen_btn.setEnabled(True)
            self.sig_status.emit(f"PE export error: {exc}", self._C_ERR)

    # ── Public ────────────────────────────────────────────────────────────────

    def _clear_all(self):
        self._preview_text.clear()
        self._stats_lbl.setText("—")
        self._export_info.setText("")
        self._last_output_path = ""
        self.sig_status.emit("PE Stimulus cleared.", self._C_INFO)
