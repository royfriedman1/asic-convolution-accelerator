"""
Memory Bank Simulation Widget

Interactive step-by-step visualisation of the 9-bank parallel SRAM
architecture used by the 3×3 convolution accelerator.

Architecture
------------
  9 banks arranged as 3 rows × 3 columns.
  For pixel P[row][col]:
      Bank row  = row % 3
      Bank col  = col % 3
      Address   = col // 3
      Bank depth = ceil(N / 3)

  The 3×3 output window becomes valid once row ≥ 2 and col ≥ 2.
  Reading the window requires three consecutive bank columns (with
  a possible address boundary crossing, handled by rd_base / h_off).
"""
from __future__ import annotations

import math

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QPushButton, QSlider, QSpinBox, QFrame,
    QScrollArea, QGroupBox, QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor


# ---------------------------------------------------------------------------
# Design tokens — all colours use rgba() with semi-transparent fills so they
# read correctly on BOTH dark (#1A1A1B) and light (#F5F5F7) backgrounds.
# Only borders and text are fully opaque; backgrounds are subtle tints.
# ---------------------------------------------------------------------------

# Shared vivid accent colours (same in dark and light)
_CYAN   = "#00ADEF"
_CYAN_D = "#0090C8"
_GREEN  = "#22C55E"
_YELLOW = "#EAB308"
_RED    = "#EF4444"

# Semi-transparent fills  (works on any bg)
_FILL_DEF  = "rgba(128,128,128, 0.08)"   # unread pixel
_FILL_BUF  = "rgba(  0,173,239, 0.12)"   # in buffer
_FILL_WIN  = "rgba( 34,197, 94, 0.14)"   # 3×3 window
_FILL_WR   = "rgba(234,179,  8, 0.16)"   # write highlight
_FILL_RD   = "rgba( 34,197, 94, 0.18)"   # read highlight
_FILL_USED = "rgba(128,128,128, 0.07)"   # used bank cell

# Text colours for each state
_TXT_DEF  = "#9CA3AF"
_TXT_BUF  = "#0EA5E9"
_TXT_WIN  = "#16A34A"
_TXT_WR   = "#CA8A04"
_TXT_RD   = "#15803D"

# Border colours for each state
_BRD_DEF  = "rgba(156,163,175, 0.40)"
_BRD_BUF  = "rgba(  0,173,239, 0.65)"
_BRD_WIN  = "rgba( 34,197, 94, 0.80)"
_BRD_WR   = "rgba(234,179,  8, 0.90)"
_BRD_RD   = "rgba( 34,197, 94, 1.00)"

# Row accent colours (bank row 0/1/2)
_ROW = ["#0D9488", "#7C3AED", "#D97706"]   # teal / violet / amber

# Column accent colours (bank col 0/1/2)
_COL = ["#F43F5E", "#0EA5E9", "#84CC16"]   # rose / sky / lime

# Muted text — slightly lighter in dark, slightly darker in light
_MU = "#8A8A8E"


def _rgba(hex_color: str, alpha: float) -> str:
    """Convert '#RRGGBB' + alpha float → 'rgba(r,g,b,alpha)'.
    Qt CSS does NOT support 8-digit hex (#RRGGBBAA), so we always use rgba()."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


class MemorySimWidget(QWidget):
    """
    Step-by-step, interactive visualisation of the 9-bank SRAM
    architecture of the 3×3 convolution accelerator.
    """

    sig_status = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._N        = 6
        self._cycle    = 0
        self._playing  = False
        self._speed_ms = 600
        self._dark     = True     # updated by main-window theme toggle

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        # Cell widget caches rebuilt in _rebuild_grids()
        self._inp_cells:    list[QLabel]             = []
        self._bank_cells:   list[list[list[QLabel]]] = []
        self._out_cells:    list[QLabel]             = []
        self._out_col_hdrs: list[QLabel]             = []
        self._out_row_hdrs: list[QLabel]             = []
        self._cell_sz: int = 36   # current input-cell pixel size (updated by _rebuild_grids)

        # Debounce timer — rebuild grids after resize stops
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._on_resize_done)

        self._build_ui()
        self._apply_settings()

    # =========================================================================
    # Public API
    # =========================================================================

    def update_theme(self, is_dark: bool) -> None:
        """Called by MainWindow when the theme toggle is clicked."""
        self._dark = is_dark
        self._refresh_theme_elements()

    # =========================================================================
    # Responsive resize
    # =========================================================================

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Debounce: wait 120 ms after the last resize before rebuilding
        self._resize_timer.start(120)

    def _on_resize_done(self) -> None:
        """Called after resize settles — recalculates cell sizes and redraws."""
        self._rebuild_grids()
        self._update_sim()

    # =========================================================================
    # UI Construction
    # =========================================================================

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar (reuses app's existing #header_bar style)
        hdr = QFrame()
        hdr.setObjectName("header_bar")
        hdr_l = QVBoxLayout(hdr)
        hdr_l.setContentsMargins(16, 8, 16, 8)
        hdr_l.setSpacing(2)
        t = QLabel("MEMORY SIMULATION")
        t.setObjectName("mode_title")
        hdr_l.addWidget(t)
        sub = QLabel(
            "9-BANK PARALLEL SRAM  ·  PIXEL MAPPING  ·  3×3 WINDOW RE-ORDERING"
        )
        sub.setObjectName("mode_subtitle")
        hdr_l.addWidget(sub)
        root.addWidget(hdr)

        # Controls bar
        root.addWidget(self._build_controls())

        # Cycle card (slider + valid badge)
        root.addWidget(self._build_cycle_card())

        # Operation info card (updates every cycle)
        root.addWidget(self._build_op_card())

        # Main dashboard — fills all remaining space, no scroll
        dash = QWidget()
        dash.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dash_l = QHBoxLayout(dash)
        dash_l.setContentsMargins(10, 10, 10, 10)
        dash_l.setSpacing(10)

        # ── Panel 1: Input image ──────────────────────────────────────────────
        self._inp_panel = QGroupBox("INPUT IMAGE  (6×6)")
        self._inp_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        inp_l = QVBoxLayout(self._inp_panel)
        inp_l.setContentsMargins(8, 16, 8, 8)
        inp_l.setSpacing(6)
        self._inp_grid_w = QWidget()
        self._inp_grid_l = QGridLayout(self._inp_grid_w)
        self._inp_grid_l.setSpacing(3)
        self._inp_grid_l.setContentsMargins(0, 0, 0, 0)
        inp_l.addStretch()
        inp_l.addWidget(self._inp_grid_w, 0, Qt.AlignmentFlag.AlignCenter)
        inp_l.addWidget(self._build_legend())
        inp_l.addStretch()
        dash_l.addWidget(self._inp_panel, stretch=1)

        # ── Panel 2: Physical Memory banks (centre) ───────────────────────────
        banks_panel = QGroupBox("PHYSICAL MEMORY  —  9 BANKS")
        banks_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        banks_l = QVBoxLayout(banks_panel)
        banks_l.setContentsMargins(8, 16, 8, 8)
        banks_l.setSpacing(6)
        b_sub = QLabel("🟡 Write   🟢 Read   Bank colour = row identity")
        b_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b_sub.setStyleSheet(f"color:{_MU}; font-size:11px;")
        banks_l.addWidget(b_sub)
        self._banks_grid_w = QWidget()
        self._banks_grid_l = QGridLayout(self._banks_grid_w)
        self._banks_grid_l.setSpacing(6)
        self._banks_grid_l.setContentsMargins(0, 0, 0, 0)
        banks_l.addStretch()
        banks_l.addWidget(self._banks_grid_w, 0, Qt.AlignmentFlag.AlignCenter)
        banks_l.addStretch()
        dash_l.addWidget(banks_panel, stretch=2)

        # ── Panel 3: Output window → PE ───────────────────────────────────────
        out_panel = QGroupBox("OUTPUT WINDOW  →  PE")
        out_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        out_l = QVBoxLayout(out_panel)
        out_l.setContentsMargins(8, 16, 8, 8)
        out_l.setSpacing(6)
        out_sub = QLabel("Pixel source and physical bank for each 3×3 window slot.")
        out_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        out_sub.setWordWrap(True)
        out_sub.setStyleSheet(f"color:{_MU}; font-size:11px;")
        out_l.addWidget(out_sub)
        self._out_grid_w = QWidget()
        self._out_grid_l = QGridLayout(self._out_grid_w)
        self._out_grid_l.setSpacing(6)
        self._out_grid_l.setContentsMargins(0, 0, 0, 0)
        out_l.addStretch()
        out_l.addWidget(self._out_grid_w, 0, Qt.AlignmentFlag.AlignCenter)
        out_l.addStretch()
        dash_l.addWidget(out_panel, stretch=1)

        root.addWidget(dash, stretch=1)

    # ── Architecture quick-reference ──────────────────────────────────────────

    def _build_arch_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("sim_arch_card")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(32)

        def _formula(title: str, expr: str, colour: str) -> QWidget:
            w = QWidget()
            l = QVBoxLayout(w)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet(f"color:{_MU}; font-size:10px; font-weight:600; letter-spacing:1px;")
            l.addWidget(t)
            e = QLabel(expr)
            e.setStyleSheet(
                f"color:{colour}; font-size:13px; font-weight:700;"
                f"font-family:'Courier New',monospace;"
            )
            l.addWidget(e)
            return w

        lay.addWidget(_formula("BANK ROW",  "row % 3",   _ROW[0]))
        lay.addWidget(self._vline())
        lay.addWidget(_formula("BANK COL",  "col % 3",   _ROW[1]))
        lay.addWidget(self._vline())
        lay.addWidget(_formula("ADDRESS",   "col ÷ 3",   _ROW[2]))
        lay.addWidget(self._vline())
        lay.addWidget(_formula("DEPTH",     "⌈N ÷ 3⌉",   _MU))
        lay.addWidget(self._vline())
        lay.addWidget(_formula("VALID",     "row≥2 & col≥2", _GREEN))
        lay.addStretch()

        return card

    # ── Current operation info card ───────────────────────────────────────────

    def _build_op_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("sim_op_card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(4)

        # Main operation line
        self._op_main = QLabel("—")
        self._op_main.setObjectName("sim_op_main")
        self._op_main.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._op_main)

        # Detail / formula line
        self._op_detail = QLabel("—")
        self._op_detail.setObjectName("sim_op_detail")
        self._op_detail.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._op_detail)

        return card

    # ── Controls bar ──────────────────────────────────────────────────────────

    def _build_controls(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("sim_ctrl_bar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 10, 18, 10)
        lay.setSpacing(12)

        sz_lbl = QLabel("Image size (N×N):")
        sz_lbl.setStyleSheet(f"color:{_MU}; font-size:12px; font-weight:600;")
        lay.addWidget(sz_lbl)

        self._sz_spin = QSpinBox()
        self._sz_spin.setRange(3, 15)
        self._sz_spin.setValue(6)
        self._sz_spin.setFixedWidth(68)
        lay.addWidget(self._sz_spin)

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("btn_success")
        apply_btn.setFixedSize(72, 30)
        apply_btn.clicked.connect(self._on_apply)
        lay.addWidget(apply_btn)

        lay.addSpacing(10)

        self._play_btn = QPushButton("▶  Play")
        self._play_btn.setObjectName("btn_primary")
        self._play_btn.setFixedSize(106, 34)
        self._play_btn.clicked.connect(self._toggle_play)
        lay.addWidget(self._play_btn)

        lay.addSpacing(10)

        spd_lbl = QLabel("Speed:")
        spd_lbl.setStyleSheet(f"color:{_MU}; font-size:12px; font-weight:600;")
        lay.addWidget(spd_lbl)

        self._spd_slider = QSlider(Qt.Orientation.Horizontal)
        self._spd_slider.setRange(1, 10)
        self._spd_slider.setValue(5)
        self._spd_slider.setFixedWidth(120)
        self._spd_slider.valueChanged.connect(self._on_speed_change)
        lay.addWidget(self._spd_slider)

        self._spd_lbl = QLabel("Medium")
        self._spd_lbl.setStyleSheet(f"color:{_MU}; font-size:12px;")
        self._spd_lbl.setFixedWidth(72)
        lay.addWidget(self._spd_lbl)

        lay.addStretch()
        return bar

    # ── Cycle / slider card ───────────────────────────────────────────────────

    def _build_cycle_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("sim_cycle_card")
        lay = QHBoxLayout(card)          # single row — compact height
        lay.setContentsMargins(20, 6, 20, 6)
        lay.setSpacing(10)

        # Clock number
        clk_cap = QLabel("CYCLE")
        clk_cap.setStyleSheet(
            f"color:{_MU}; font-size:10px; font-weight:700; letter-spacing:2px;")
        lay.addWidget(clk_cap)

        self._clk_num = QLabel("1")
        self._clk_num.setStyleSheet(f"color:{_RED}; font-size:20px; font-weight:800;")
        self._clk_num.setFixedWidth(46)
        lay.addWidget(self._clk_num)

        self._clk_of = QLabel("/ 36")
        self._clk_of.setStyleSheet(f"color:{_MU}; font-size:12px;")
        self._clk_of.setFixedWidth(40)
        lay.addWidget(self._clk_of)

        # Slider with min/max labels
        lbl_1 = QLabel("1")
        lbl_1.setStyleSheet(f"color:{_MU}; font-size:10px;")
        lay.addWidget(lbl_1)

        self._cyc_slider = QSlider(Qt.Orientation.Horizontal)
        self._cyc_slider.setRange(0, 35)
        self._cyc_slider.setValue(0)
        self._cyc_slider.valueChanged.connect(self._on_cyc_slider)
        lay.addWidget(self._cyc_slider, stretch=1)

        self._max_lbl = QLabel("36")
        self._max_lbl.setStyleSheet(f"color:{_MU}; font-size:10px; min-width:26px;")
        lay.addWidget(self._max_lbl)

        # Valid badge
        self._valid_badge = QLabel("✖  window_valid = 0")
        self._valid_badge.setObjectName("sim_badge_invalid")
        self._valid_badge.setFixedHeight(26)
        self._valid_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._valid_badge)

        return card

    # ── Legend ────────────────────────────────────────────────────────────────

    def _build_legend(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(18)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        items = [
            ("rgba(128,128,128,0.08)", "rgba(128,128,128,0.40)", _TXT_DEF, "Not read yet"),
            (_FILL_BUF,               _BRD_BUF,                 _TXT_BUF, "In buffer"),
            (_CYAN,                   _CYAN_D,                  "#ffffff", "Current pixel"),
            (_FILL_WIN,               _BRD_WIN,                 _TXT_WIN,  "3×3 window"),
        ]
        for bg, brd, fg, text in items:
            c = QWidget()
            l = QHBoxLayout(c)
            l.setContentsMargins(0, 0, 0, 0)
            l.setSpacing(6)
            dot = QLabel()
            dot.setFixedSize(13, 13)
            dot.setStyleSheet(
                f"background:{bg}; border:1.5px solid {brd}; border-radius:3px;")
            l.addWidget(dot)
            txt = QLabel(text)
            txt.setStyleSheet(f"color:{_MU}; font-size:11px;")
            l.addWidget(txt)
            lay.addWidget(c)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _vline() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setFixedWidth(1)
        f.setStyleSheet("background:rgba(128,128,128,0.3); margin:2px 0;")
        return f

    # =========================================================================
    # Grid reconstruction
    # =========================================================================

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _rebuild_grids(self) -> None:
        N     = self._N
        depth = math.ceil(N / 3)

        # ── Derive cell sizes from current widget dimensions ───────────────────
        # Fixed vertical overhead: header~56 + controls~54 + cycle~44 + op_card~58
        #                          + dash margins 20 + panel title/legend ~80
        FIXED_V  = 340
        FIXED_H  = 56    # dash margins + inter-panel spacing

        w = max(500, self.width())
        h = max(300, self.height())

        avail_h = max(N * 18, h - FIXED_V)
        avail_w = max(400, w - FIXED_H)

        # Input panel ~25 % of width; height limited by avail_h
        inp_w   = avail_w // 4 - 16           # minus panel paddings
        inp_h   = avail_h - 34                # minus legend row
        cell    = max(16, min(60, min(inp_w // max(1, N),
                                      inp_h // max(1, N))))
        self._cell_sz = cell
        fs   = max(5, cell // 4)
        mono = QFont("Courier New", fs)
        mono.setBold(True)

        # Bank cells: banks panel ~50 % of width, 3×3 boxes each depth cells wide
        banks_w   = avail_w // 2 - 16
        banks_h   = avail_h - 30
        box_w     = (banks_w - 12) // 3       # 2 gaps × 6 px
        box_h     = (banks_h - 12) // 3
        b_cw      = max(1, (box_w - 20) // max(1, depth))
        b_ch      = max(1, box_h - 44)        # minus bank-title + padding
        b_cell_sz = max(20, min(52, min(b_cw, b_ch)))
        b_fs      = max(7, min(10, b_cell_sz // 4))
        b_font    = QFont("Courier New", b_fs)
        b_font.setBold(True)

        # Output cells: output panel ~25 % of width, always 3×3 + headers
        out_w   = avail_w // 4 - 16
        out_h   = avail_h - 50
        OUT     = max(24, min(80, min(out_w // 4, out_h // 4)))

        # ── Input grid ────────────────────────────────────────────────────────
        self._clear_layout(self._inp_grid_l)
        self._inp_cells.clear()
        for r in range(N):
            for c in range(N):
                lbl = QLabel("")          # no initial text — colour conveys state
                lbl.setFixedSize(cell, cell)
                lbl.setContentsMargins(0, 0, 0, 0)
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFont(mono)
                lbl.setStyleSheet(self._inp_css("default"))
                self._inp_grid_l.addWidget(lbl, r, c)
                self._inp_cells.append(lbl)
        self._inp_panel.setTitle(f"INPUT IMAGE  ({N}×{N})")

        # ── Output window (3×3 + header row/col) ──────────────────────────────
        self._clear_layout(self._out_grid_l)
        self._out_cells.clear()
        self._out_col_hdrs.clear()
        self._out_row_hdrs.clear()

        OUT = 72   # output cell size (fixed — always shows 3×3)

        corner = QLabel()
        corner.setFixedSize(60, 36)
        self._out_grid_l.addWidget(corner, 0, 0)

        for j in range(3):
            h = QLabel("Bank col\n—")
            h.setFixedSize(OUT, 38)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            h.setStyleSheet(self._out_hdr_default())
            self._out_grid_l.addWidget(h, 0, j + 1)
            self._out_col_hdrs.append(h)

        out_f = QFont("Courier New", 9)
        out_f.setBold(True)
        for i in range(3):
            rh = QLabel("Bank row\n—")
            rh.setFixedSize(60, OUT)
            rh.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rh.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            rh.setStyleSheet(self._out_hdr_default())
            self._out_grid_l.addWidget(rh, i + 1, 0)
            self._out_row_hdrs.append(rh)
            for j in range(3):
                cell_lbl = QLabel("—")
                cell_lbl.setFixedSize(OUT, OUT)
                cell_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_lbl.setFont(out_f)
                cell_lbl.setStyleSheet(self._out_css("invalid"))
                self._out_grid_l.addWidget(cell_lbl, i + 1, j + 1)
                self._out_cells.append(cell_lbl)

        # ── Banks (3×3 grid of bank boxes) ────────────────────────────────────
        self._clear_layout(self._banks_grid_l)
        self._bank_cells = [[[] for _ in range(3)] for _ in range(3)]
        # b_cell_sz, b_fs, b_font already computed above from widget dimensions

        for br in range(3):
            for bc in range(3):
                rc = _ROW[br]
                box = QFrame()
                box.setStyleSheet(
                    f"QFrame {{"
                    f"  border: 1.5px solid {rc};"
                    f"  border-radius: 10px;"
                    f"  background: {'rgba(255,255,255,0.03)' if self._dark else 'rgba(0,0,0,0.03)'};"
                    f"}}"
                )
                box_l = QVBoxLayout(box)
                box_l.setContentsMargins(8, 8, 8, 8)
                box_l.setSpacing(5)

                title = QLabel(f"Bank[{br}][{bc}]")
                title.setAlignment(Qt.AlignmentFlag.AlignCenter)
                title.setStyleSheet(
                    f"background: {'rgba(255,255,255,0.06)' if self._dark else f'{rc}18'};"
                    f"color:{rc}; border:1px solid {rc}; border-radius:4px;"
                    f"padding:2px 8px; font-size:10px; font-weight:700;"
                    f"font-family:'Courier New',monospace;"
                )
                box_l.addWidget(title, 0, Qt.AlignmentFlag.AlignCenter)

                row_w = QWidget()
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(0, 0, 0, 0)
                row_l.setSpacing(4)
                row_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

                addr_cells: list[QLabel] = []
                b_cell_sz = max(32, min(42, int(120 / max(depth, 1))))
                for addr in range(depth):
                    cl = QLabel(f"@{addr}")    # single-line — no clipping
                    cl.setFixedSize(b_cell_sz, b_cell_sz)
                    cl.setContentsMargins(0, 0, 0, 0)
                    cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    cl.setFont(b_font)
                    cl.setToolTip(f"Bank[{br}][{bc}]  addr {addr}")
                    cl.setStyleSheet(self._bank_css("empty", br))
                    row_l.addWidget(cl)
                    addr_cells.append(cl)

                self._bank_cells[br][bc] = addr_cells
                box_l.addWidget(row_w)
                self._banks_grid_l.addWidget(box, br, bc)

    def _refresh_theme_elements(self) -> None:
        """Re-apply theme-sensitive styles (bank box backgrounds) after rebuild."""
        for br in range(len(self._bank_cells)):
            for bc in range(len(self._bank_cells[br])):
                # Re-style the parent QFrame of each bank
                pass  # colours embedded in _rebuild_grids; call that if needed

    # =========================================================================
    # Simulation logic
    # =========================================================================

    def _update_sim(self) -> None:
        N     = self._N
        depth = math.ceil(N / 3)
        cyc   = self._cycle
        row   = cyc // N
        col   = cyc % N

        wr_row  = row % 3
        wr_col  = col % 3
        wr_addr = col // 3
        valid   = (row >= 2) and (col >= 2)

        # ── Clock label ───────────────────────────────────────────────────────
        self._clk_num.setText(str(cyc + 1))

        # ── window_valid badge ────────────────────────────────────────────────
        if valid:
            self._valid_badge.setObjectName("sim_badge_valid")
            self._valid_badge.setText("✔  window_valid = 1")
        else:
            self._valid_badge.setObjectName("sim_badge_invalid")
            self._valid_badge.setText("✖  window_valid = 0")
        self._valid_badge.style().unpolish(self._valid_badge)
        self._valid_badge.style().polish(self._valid_badge)

        # ── Operation info card ───────────────────────────────────────────────
        self._op_main.setText(
            f"Writing  P[{row}][{col}]  →  Bank[{wr_row}][{wr_col}]  @  address {wr_addr}"
        )
        detail = (
            f"wr_row = {row}%3 = {wr_row}   ·   "
            f"wr_bank = {col}%3 = {wr_col}   ·   "
            f"wr_addr = {col}÷3 = {wr_addr}   ·   "
            f"bank depth = ⌈{N}÷3⌉ = {depth}"
        )
        if not valid:
            remaining_r = max(0, 2 - row)
            remaining_c = max(0, 2 - col)
            if remaining_r > 0:
                detail += f"   ·   ⚠ window_valid in {remaining_r} more row(s)"
            elif remaining_c > 0:
                detail += f"   ·   ⚠ window_valid in {remaining_c} more col(s)"
        else:
            rd_base = (col - 2) // 3
            h_off   = ((col - 2) % 3 + 3) % 3
            detail += f"   ·   rd_base={rd_base}  h_off={h_off}  → reading 3×3 window"
        self._op_detail.setText(detail)

        # ── Rebuild bank state ────────────────────────────────────────────────
        banks: list[list[list]] = [
            [[None] * depth for _ in range(3)] for _ in range(3)
        ]
        in_mem: set[tuple[int, int]] = set()
        for i in range(cyc + 1):
            cr, cc = i // N, i % N
            pr, pb, pa = cr % 3, cc % 3, cc // 3
            prev = banks[pr][pb][pa]
            if prev is not None:
                in_mem.discard(prev)
            coord = (cr, cc)
            banks[pr][pb][pa] = coord
            in_mem.add(coord)

        # ── Read addresses ────────────────────────────────────────────────────
        rd_addrs: list[int | None] = [None, None, None]
        if valid:
            rd_base = (col - 2) // 3
            h_off   = ((col - 2) % 3 + 3) % 3
            for bc in range(3):
                rd_addrs[bc] = rd_base + 1 if bc < h_off else rd_base

        # ── Input grid ────────────────────────────────────────────────────────
        # Cells are colour-only — text only on the current pixel and the 3×3 window.
        # This avoids all clipping regardless of N.
        for r in range(N):
            for c in range(N):
                coord  = (r, c)
                in_win = (
                    valid
                    and (row - 2 <= r <= row)
                    and (col - 2 <= c <= col)
                )
                lbl = self._inp_cells[r * N + c]
                # Show coordinate text only when cell is large enough to fit it
                show_txt = self._cell_sz >= 28
                if r == row and c == col:
                    lbl.setStyleSheet(self._inp_css("current"))
                    lbl.setText(f"P{r}/{c}" if show_txt else "●")
                elif in_win:
                    lbl.setStyleSheet(self._inp_css("window"))
                    lbl.setText(f"{r}/{c}" if show_txt else "")
                elif coord in in_mem:
                    lbl.setStyleSheet(self._inp_css("buffer"))
                    lbl.setText(f"{r}/{c}" if show_txt else "")
                else:
                    lbl.setStyleSheet(self._inp_css("default"))
                    lbl.setText(f"{r}/{c}" if show_txt else "")

        # ── Banks ─────────────────────────────────────────────────────────────
        for br in range(3):
            for bc in range(3):
                for addr in range(depth):
                    val  = banks[br][bc][addr]
                    cell = self._bank_cells[br][bc][addr]
                    if val is None:
                        cell.setText(f"@{addr}")       # empty slot — single line
                        cell.setStyleSheet(self._bank_css("empty", br))
                    else:
                        r2, c2 = val
                        is_wr = (val == (row, col))
                        is_rd = (
                            valid
                            and br in {row % 3, (row - 1) % 3, (row - 2) % 3}
                            and rd_addrs[bc] is not None
                            and addr == rd_addrs[bc]
                        )
                        # Highlight cells show pixel coord; others just show address
                        if is_wr or is_rd:
                            cell.setText(f"P{r2}/{c2}")   # single line — always fits
                        else:
                            cell.setText(f"@{addr}")       # compact — no clipping
                        if is_wr:
                            cell.setStyleSheet(self._bank_css("write", br))
                        elif is_rd:
                            cell.setStyleSheet(self._bank_css("read", br))
                        else:
                            cell.setStyleSheet(self._bank_css("used", br))

        # ── Output window ─────────────────────────────────────────────────────
        # Colour rule: row headers = bank-row accent; col headers = bank-col accent;
        # data cells = one consistent green style — no more colour mixing per cell.
        _HDR_BASE = (
            "border-radius:5px; font-size:9px; font-weight:700;"
            "font-family:'Courier New',monospace;"
        )
        _CELL_ACTIVE = (
            "background:rgba(34,197,94,0.16); border:1.5px solid rgba(34,197,94,0.70);"
            "border-radius:8px; color:#22C55E;"
            "font-size:10px; font-weight:700; font-family:'Courier New',monospace;"
        )
        _CELL_MISS = (
            "background:rgba(239,68,68,0.10); border:1px solid rgba(239,68,68,0.40);"
            "border-radius:8px; color:#EF4444;"
            "font-size:10px; font-weight:700; font-family:'Courier New',monospace;"
        )
        if valid:
            p_rows = [(row - 2) % 3, (row - 1) % 3, row % 3]
            p_cols = [(col - 2) % 3, (col - 1) % 3, col % 3]

            for j, pc in enumerate(p_cols):
                cc = _COL[pc]
                self._out_col_hdrs[j].setText(f"col {pc}")
                self._out_col_hdrs[j].setStyleSheet(
                    f"background:{_rgba(cc,0.12)}; border:1.5px solid {cc};"
                    f"color:{cc}; {_HDR_BASE}"
                )

            for i, pr in enumerate(p_rows):
                rc = _ROW[pr]
                self._out_row_hdrs[i].setText(f"row\n{pr}")
                self._out_row_hdrs[i].setStyleSheet(
                    f"background:{_rgba(rc,0.12)}; border:1.5px solid {rc};"
                    f"color:{rc}; {_HDR_BASE}"
                )
                for j, pc in enumerate(p_cols):
                    taddr = rd_addrs[pc]
                    px    = (
                        banks[pr][pc][taddr]
                        if (taddr is not None and 0 <= taddr < depth)
                        else None
                    )
                    cell_lbl = self._out_cells[i * 3 + j]
                    if px:
                        r2, c2 = px
                        cell_lbl.setText(f"P{r2}/{c2}")
                        cell_lbl.setStyleSheet(_CELL_ACTIVE)
                    else:
                        cell_lbl.setText("?")
                        cell_lbl.setStyleSheet(_CELL_MISS)
        else:
            _HDR_DEF = self._out_hdr_default()
            for j in range(3):
                self._out_col_hdrs[j].setText("col —")
                self._out_col_hdrs[j].setStyleSheet(_HDR_DEF)
            for i in range(3):
                self._out_row_hdrs[i].setText("row\n—")
                self._out_row_hdrs[i].setStyleSheet(_HDR_DEF)
                for j in range(3):
                    self._out_cells[i * 3 + j].setText("—")
                    self._out_cells[i * 3 + j].setStyleSheet(self._out_css("invalid"))

    # =========================================================================
    # CSS helpers — all use rgba() so they work on any background
    # =========================================================================

    @staticmethod
    def _inp_css(state: str) -> str:
        base = (
            "border-radius:7px;"
            "font-family:'Courier New',monospace; font-weight:700;"
        )
        if state == "current":
            # Solid cyan fill — font-size not set here; QFont from setFont() controls size
            return (
                f"background:{_CYAN}; border:2px solid {_CYAN_D};"
                f"color:#ffffff; {base}"
            )
        if state == "window":
            return (
                f"background:{_FILL_WIN}; border:2px solid {_BRD_WIN};"
                f"color:{_TXT_WIN}; {base}"
            )
        if state == "buffer":
            return (
                f"background:{_FILL_BUF}; border:1.5px solid {_BRD_BUF};"
                f"color:{_TXT_BUF}; {base}"
            )
        return (
            f"background:{_FILL_DEF}; border:1.5px solid {_BRD_DEF};"
            f"color:{_TXT_DEF}; {base}"
        )

    @staticmethod
    def _bank_css(state: str, row: int) -> str:
        # font-size intentionally omitted — QFont set via setFont() takes effect
        base = (
            "border-radius:6px;"
            "font-family:'Courier New',monospace; font-weight:700;"
        )
        rc = _ROW[row]
        if state == "write":
            # Solid yellow — unmistakably "writing now"
            return (
                f"background:{_YELLOW}; border:2px solid {_YELLOW};"
                f"color:#111111; {base}"
            )
        if state == "read":
            # Solid green — unmistakably "reading now"
            return (
                f"background:{_GREEN}; border:2px solid {_GREEN};"
                f"color:#111111; {base}"
            )
        if state == "used":
            # Neutral fill — bank identity carried by the surrounding box border
            return (
                f"background:rgba(128,128,128,0.14); border:1px solid rgba(128,128,128,0.35);"
                f"color:#9CA3AF; {base}"
            )
        # empty
        return (
            f"background:rgba(128,128,128,0.05); border:1px dashed rgba(128,128,128,0.25);"
            f"color:rgba(128,128,128,0.40); {base}"
        )

    @staticmethod
    def _out_css(state: str) -> str:
        base = (
            "border-radius:8px;"
            "font-family:'Courier New',monospace; font-size:9px;"
        )
        if state == "valid":
            return (
                f"background:{_FILL_WIN}; border:1.5px solid {_BRD_WIN};"
                f"color:{_TXT_WIN}; {base}"
            )
        return (
            f"background:{_FILL_DEF}; border:1px solid {_BRD_DEF};"
            f"color:{_TXT_DEF}; {base}"
        )

    @staticmethod
    def _out_hdr_default() -> str:
        return (
            f"background:{_FILL_DEF}; border:1px solid {_BRD_DEF};"
            f"border-radius:5px; color:{_MU}; font-size:9px;"
        )

    # =========================================================================
    # Slot handlers
    # =========================================================================

    def _apply_settings(self) -> None:
        self._N   = self._sz_spin.value()
        max_cyc   = self._N * self._N
        self._cyc_slider.blockSignals(True)
        self._cyc_slider.setMaximum(max_cyc - 1)
        self._cyc_slider.setValue(0)
        self._cyc_slider.blockSignals(False)
        self._clk_of.setText(f"/ {max_cyc}")
        self._max_lbl.setText(str(max_cyc))
        self._cycle = 0
        self._rebuild_grids()
        self._update_sim()

    def _on_apply(self) -> None:
        if self._playing:
            self._stop_play()
        self._apply_settings()

    def _on_cyc_slider(self, val: int) -> None:
        if self._playing:
            self._stop_play()
        self._cycle = val
        self._update_sim()

    def _toggle_play(self) -> None:
        if self._playing:
            self._stop_play()
        else:
            self._start_play()

    def _start_play(self) -> None:
        if self._cycle >= self._N * self._N - 1:
            self._cycle = 0
            self._cyc_slider.blockSignals(True)
            self._cyc_slider.setValue(0)
            self._cyc_slider.blockSignals(False)
            self._update_sim()
        self._playing = True
        self._play_btn.setText("⏸  Pause")
        self._play_btn.setObjectName("btn_warn")
        self._play_btn.style().unpolish(self._play_btn)
        self._play_btn.style().polish(self._play_btn)
        self._timer.start(self._speed_ms)

    def _stop_play(self) -> None:
        self._playing = False
        self._timer.stop()
        self._play_btn.setText("▶  Play")
        self._play_btn.setObjectName("btn_primary")
        self._play_btn.style().unpolish(self._play_btn)
        self._play_btn.style().polish(self._play_btn)

    def _tick(self) -> None:
        if self._cycle < self._N * self._N - 1:
            self._cycle += 1
            self._cyc_slider.blockSignals(True)
            self._cyc_slider.setValue(self._cycle)
            self._cyc_slider.blockSignals(False)
            self._update_sim()
        else:
            self._stop_play()

    def _on_speed_change(self, val: int) -> None:
        self._speed_ms = max(50, 1600 - val * 150)
        labels = {
            1: "Very Slow", 2: "Slow",   3: "Slow",
            4: "Medium",   5: "Medium",  6: "Medium",
            7: "Fast",     8: "Fast",    9: "Very Fast", 10: "Max",
        }
        self._spd_lbl.setText(labels.get(val, "Medium"))
        if self._playing:
            self._timer.start(self._speed_ms)
