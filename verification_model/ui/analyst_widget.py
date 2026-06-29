"""
Analyst Mode — Post-Simulation Panel

Layout:
  ┌──────────────────────────────────────────────────────────────────┐
  │  IMPORT BAR                                                       │
  ├──────────────────────────────────────┬───────────────────────────┤
  │  VISUAL COMPARISON (3 image views)   │  SYNTHESIS METRICS        │
  │  Golden | Chip DUT | Mismatch Map    │  Gates / Area / Speed     │
  │                                      │  Match Rate / Errors      │
  ├──────────────────────────────────────┴───────────────────────────┤
  │  POWER CONSUMPTION GRAPH                                          │
  └──────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
import os
import re
import numpy as np


def _natural_sort_key(filename: str):
    """Splits digit runs out so 'frame_2' sorts before 'frame_10'."""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", filename)]

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QTabWidget,
    QGroupBox, QPushButton, QLabel,
    QFileDialog, QTableWidget, QTableWidgetItem,
    QFrame, QHeaderView, QSizePolicy, QGridLayout,
    QSpinBox, QSlider, QApplication, QScrollArea,
    QToolButton, QMenu,
)
from PyQt6.QtCore import Qt, QSize, QTimer, QThread, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont, QKeySequence, QShortcut, QAction

from ui.image_display import ImageDisplay, build_mismatch_rgb
from ui.loading_overlay import LoadingOverlay
from core.golden_model import run_golden_model_fast
from core.app_logger import AppLogger


class _TxtVideoLoaderWorker(QObject):
    """Loads a list of .txt frame files off the UI thread."""
    progress = pyqtSignal(str)    # human-readable progress message
    finished = pyqtSignal(list)   # list of parsed arrays (empty = cancelled)
    error    = pyqtSignal(str)

    def __init__(self, files: list, folder: str, parse_fn):
        super().__init__()
        self._files     = files
        self._folder    = folder
        self._parse_fn  = parse_fn
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            results = []
            for i, fname in enumerate(self._files):
                if self._cancelled:
                    self.finished.emit([])
                    return
                bits = self._parse_fn(os.path.join(self._folder, fname))
                results.append(bits)
                if i % 5 == 0:
                    self.progress.emit(f"Reading frame {i + 1} / {len(self._files)}…")
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


class _ImgVideoLoaderWorker(QObject):
    """Loads image frame files off the UI thread."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)   # list of uint8 numpy arrays (empty = cancelled)
    error    = pyqtSignal(str)

    def __init__(self, files: list, folder: str):
        super().__init__()
        self._files     = files
        self._folder    = folder
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            import numpy as _np
            results = []
            for i, fname in enumerate(self._files):
                if self._cancelled:
                    self.finished.emit([])
                    return
                path = os.path.join(self._folder, fname)
                try:
                    import cv2 as _cv2
                    raw = _np.fromfile(path, dtype=_np.uint8)
                    img = _cv2.imdecode(raw, _cv2.IMREAD_GRAYSCALE)
                    img = _cv2.resize(img, (256, 256), interpolation=_cv2.INTER_AREA)
                    results.append(img.astype(_np.uint8))
                except Exception:
                    from PIL import Image as _Pil
                    img = _Pil.open(path).convert("L").resize((256, 256))
                    results.append(_np.array(img, dtype=_np.uint8))
                if i % 5 == 0:
                    self.progress.emit(f"Reading frame {i + 1} / {len(self._files)}…")
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


class _ComparisonGroupBox(QGroupBox):
    """
    GroupBox whose height always equals the width of one of its N children
    (i.e. each child is shown as a square).  The height is enforced via
    resizeEvent → setFixedHeight, which works reliably even inside a
    QScrollArea where hasHeightForWidth alone is ignored.
    """

    def _square_height(self, w: int) -> int:
        lay = self.layout()
        if lay is None:
            return w // 3
        m       = lay.contentsMargins()
        sp      = lay.spacing()
        n       = max(1, lay.count())
        inner_w = max(1, w - m.left() - m.right() - sp * (n - 1))
        square  = inner_w // n
        return square + m.top() + m.bottom()

    # Keep these so QVBoxLayout outside a QScrollArea also honours the ratio
    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, w: int) -> int:
        return self._square_height(w)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        target = self._square_height(event.size().width())
        if self.minimumHeight() != target or self.maximumHeight() != target:
            self.setFixedHeight(target)


class AnalystWidget(QWidget):

    sig_status = pyqtSignal(str, str)   # (message, colour  e.g. "#00ff88")

    STATUS_OK   = "#00ff88"
    STATUS_ERR  = "#ff4444"
    STATUS_INFO = "#ffd700"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._golden: np.ndarray | None = None      # 254×254
        self._chip: np.ndarray | None = None         # 254×254
        self._image: np.ndarray | None = None        # 256×256 source
        self._mismatch_coords: list[tuple[int,int]] = []
        self._last_match_rate:  float | None = None
        self._last_errors:      int   | None = None
        self._last_total_valid: int   | None = None
        self._kernel_cfg:       dict  = {}         # updated live from GeneratorWidget
        self._golden_source:    str   = "none"    # "none"|"generator"|"external"|"external+params"
        # Video / multi-frame state
        self._golden_frames: list[np.ndarray] = []
        self._chip_frames:   list[np.ndarray] = []
        self._video_frames:  list[np.ndarray] = []
        self._video_idx:     int = 0
        self._is_playing:    bool = False
        self._play_timer:    QTimer | None = None
        self._cancel_loading: bool = False
        self._load_thread: QThread | None = None
        self._load_worker = None
        self._pending_run_folder: str = ""
        self._pending_input_dir:  str = ""
        self._pending_img_files:  list = []
        # Per-frame kernel configs parsed from stimulus/ hex files
        self._per_frame_kernel_cfgs: list[dict] = []
        self._build_ui()
        # Loading overlay — created AFTER _build_ui so it covers the full widget
        self._overlay = LoadingOverlay(self)
        self._overlay.sig_cancel.connect(self._on_cancel_loading)
        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._load_chip_output)
        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self._load_golden_ref)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._run_comparison)
        QShortcut(QKeySequence("Space"), self).activated.connect(
            lambda: self._toggle_analyst_play()
            if (self._golden_frames or self._chip_frames) else None
        )

    # ══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ══ FIXED TOP SECTION — never scrolls ════════════════════════════════
        top = QWidget()
        top.setObjectName("analyst_top_bar")
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(4, 10, 4, 0)
        top_lay.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("header_bar")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(0, 0, 0, 0)
        t1 = QLabel("ANALYST")
        t1.setObjectName("mode_title")
        t2 = QLabel("POST-SIMULATION / CHIP VERIFICATION")
        t2.setObjectName("mode_subtitle")
        hdr_lay.addWidget(t1)
        hdr_lay.addSpacing(14)
        hdr_lay.addWidget(t2, alignment=Qt.AlignmentFlag.AlignBottom)
        hdr_lay.addStretch()
        top_lay.addWidget(hdr)

        # ── Import bar ────────────────────────────────────────────────────────
        top_lay.addWidget(self._build_import_bar())

        # ── Kernel config bar ─────────────────────────────────────────────────
        self._kernel_bar = self._build_kernel_bar()
        top_lay.addWidget(self._kernel_bar)

        # ── Video navigation bar (hidden until multi-frame data is loaded) ────
        self._video_nav = self._build_video_nav()
        top_lay.addWidget(self._video_nav)
        self._video_nav.setVisible(False)

        root.addWidget(top)

        # ── Thin separator ────────────────────────────────────────────────────
        sep = QFrame()
        sep.setObjectName("nav_separator")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ══ SCROLLABLE CONTENT ════════════════════════════════════════════════
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(4, 8, 4, 12)
        content_lay.setSpacing(10)

        content_lay.addWidget(self._build_comparison_panel(), stretch=8)
        content_lay.addWidget(self._build_right_panel(),      stretch=3)

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    # ── Import bar ────────────────────────────────────────────────────────────

    def _build_import_bar(self) -> QFrame:
        """
        Compact single-row toolbar with labelled sections spanning full width.
        Each section: tiny header label + button(s). Compare has match rate inside.
        """
        bar = QFrame()
        bar.setObjectName("img_frame")
        bar.setFixedHeight(70)                          # snug around labels + buttons
        row = QHBoxLayout(bar)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(0)

        # ── helpers ───────────────────────────────────────────────────────────
        def _vsep():
            s = QFrame()
            s.setObjectName("nav_vseparator")
            s.setFixedWidth(1)
            s.setMinimumHeight(36)
            return s

        def _hdr(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("import_section_hdr")
            return lbl

        def _btn(label, obj_name, tip, slot):
            b = QPushButton(label)
            b.setObjectName(obj_name)
            b.setToolTip(tip)
            b.setFixedHeight(30)
            b.setMinimumWidth(50)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(slot)
            return b

        def _section(title: str, buttons: list, stretch: int = 5):
            """Section widget: tiny label on top, buttons packed immediately below."""
            w = QWidget()
            w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            lay = QVBoxLayout(w)
            lay.setContentsMargins(4, 0, 4, 0)
            lay.setSpacing(3)
            lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            lay.addWidget(_hdr(title))
            btn_row = QHBoxLayout()
            btn_row.setContentsMargins(0, 0, 0, 0)
            btn_row.setSpacing(3)
            for b in buttons:
                btn_row.addWidget(b)
            lay.addLayout(btn_row)
            row.addWidget(w, stretch=stretch)

        # ── RUN FOLDER (golden + original input) ─────────────────────────────
        folder_w = QWidget()
        folder_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        folder_lay = QVBoxLayout(folder_w)
        folder_lay.setContentsMargins(4, 0, 4, 0)
        folder_lay.setSpacing(3)
        folder_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        folder_lay.addWidget(_hdr("RUN FOLDER"))

        folder_btn_row = QHBoxLayout()
        folder_btn_row.setContentsMargins(0, 0, 0, 0)
        folder_btn_row.setSpacing(3)

        load_folder_btn = _btn(
            "Load Folder", "btn_success",
            "Import a gui_run_* folder: loads golden scoreboard, "
            "original input frames, and kernel params automatically",
            self._load_run_folder,
        )
        folder_btn_row.addWidget(load_folder_btn)

        # Manual ▾ dropdown for individual file imports
        manual_btn = QToolButton()
        manual_btn.setText("Manual ▾")
        manual_btn.setObjectName("btn_primary")
        manual_btn.setFixedHeight(30)
        manual_btn.setMinimumWidth(70)
        manual_btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        manual_btn.setToolTip("Manual import: select individual files")
        manual_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        manual_menu = QMenu(manual_btn)
        manual_menu.addAction(QAction("Load Golden File",  self, triggered=self._load_golden_ref))
        manual_menu.addAction(QAction("Load Golden Video", self, triggered=self._load_golden_video))
        manual_menu.addSeparator()
        manual_menu.addAction(QAction("Load Input Image",  self, triggered=self._load_original_image))
        manual_menu.addAction(QAction("Load Input Video",  self, triggered=self._load_original_video))
        manual_btn.setMenu(manual_menu)

        folder_btn_row.addWidget(manual_btn)
        folder_lay.addLayout(folder_btn_row)
        row.addWidget(folder_w, stretch=6)
        row.addWidget(_vsep())

        # ── CHIP DATA ─────────────────────────────────────────────────────────
        _section("CHIP DATA", [
            _btn("Load Output", "btn_primary",
                 "Single-frame chip output (.txt)", self._load_chip_output),
            _btn("Load Video",  "btn_primary",
                 "Multi-frame: folder of .txt files", self._load_chip_video),
        ], stretch=5)
        row.addWidget(_vsep())

        # ── COMPARE — aligns with left visual panel (4th of 4 left sections) ─
        cmp_w = QWidget()
        cmp_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cmp_lay = QVBoxLayout(cmp_w)
        cmp_lay.setContentsMargins(4, 6, 4, 6)
        cmp_lay.setSpacing(3)
        cmp_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # invisible placeholder header — same height as _hdr() labels in other sections
        _cmp_hdr_placeholder = _hdr("")
        _cmp_hdr_placeholder.setVisible(False)
        cmp_lay.addWidget(_cmp_hdr_placeholder)

        cmp_btn_row = QHBoxLayout()
        cmp_btn_row.setContentsMargins(0, 0, 0, 0)
        cmp_btn_row.setSpacing(4)

        self._compare_btn = QPushButton("Compare  \u25b6")
        self._compare_btn.setObjectName("btn_export")
        self._compare_btn.setFixedHeight(30)
        self._compare_btn.setMinimumWidth(50)
        self._compare_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._compare_btn.clicked.connect(self._run_comparison)
        cmp_btn_row.addWidget(self._compare_btn)

        self._match_badge = QLabel("")
        self._match_badge.setObjectName("lbl_match_rate")
        self._match_badge.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._match_badge.setWordWrap(False)
        self._match_badge.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        cmp_btn_row.addWidget(self._match_badge)

        cmp_lay.addLayout(cmp_btn_row)
        row.addWidget(cmp_w, stretch=6)

        return bar

    # ── Video navigation bar ──────────────────────────────────────────────────

    def _build_video_nav(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("img_frame")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(10)

        self._an_frame_lbl = QLabel("Frame  1  /  —")
        self._an_frame_lbl.setObjectName("lbl_stat_value")
        self._an_frame_lbl.setMinimumWidth(110)
        lay.addWidget(self._an_frame_lbl)

        self._an_slider = QSlider(Qt.Orientation.Horizontal)
        self._an_slider.setMinimum(0)
        self._an_slider.setMaximum(0)
        self._an_slider.valueChanged.connect(self._an_slider_changed)
        lay.addWidget(self._an_slider, stretch=1)

        btn_prev = QPushButton("◀ Prev")
        btn_prev.setObjectName("nav_btn")
        btn_prev.setMinimumSize(QSize(80, 32))
        btn_prev.clicked.connect(lambda: self._set_analyst_frame(
            max(0, self._video_idx - 1)
        ))
        lay.addWidget(btn_prev)

        self._an_btn_play = QPushButton("▶  Play")
        self._an_btn_play.setObjectName("nav_btn")
        self._an_btn_play.setMinimumSize(QSize(100, 32))
        self._an_btn_play.clicked.connect(self._toggle_analyst_play)
        lay.addWidget(self._an_btn_play)

        btn_next = QPushButton("Next ▶")
        btn_next.setObjectName("nav_btn")
        btn_next.setMinimumSize(QSize(80, 32))
        btn_next.clicked.connect(lambda: self._set_analyst_frame(
            min(max(len(self._golden_frames), len(self._chip_frames)) - 1,
                self._video_idx + 1)
        ))
        lay.addWidget(btn_next)

        lay.addSpacing(8)
        self._an_fps_sb = QSpinBox()
        self._an_fps_sb.setRange(1, 60)
        self._an_fps_sb.setValue(10)
        self._an_fps_sb.setSuffix("  fps")   # unit inside spinbox — no floating label
        self._an_fps_sb.setFixedWidth(78)
        self._an_fps_sb.setFixedHeight(30)
        lay.addWidget(self._an_fps_sb)

        return bar

    # ── Kernel config bar ─────────────────────────────────────────────────────

    def _build_kernel_bar(self) -> QFrame:
        """Compact horizontal strip showing the current kernel configuration."""
        bar = QFrame()
        bar.setObjectName("kernel_bar")
        bar.setFixedHeight(24)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(0)

        def _cap(text):
            lbl = QLabel(text)
            lbl.setObjectName("kb_caption")
            return lbl

        def _val(attr):
            lbl = QLabel("—")
            lbl.setObjectName("kb_value")
            setattr(self, attr, lbl)
            return lbl

        def _sep():
            s = QFrame()
            s.setObjectName("nav_vseparator")
            s.setFixedWidth(1)
            s.setFixedHeight(14)
            return s

        lay.addWidget(_cap("KERNEL:"))
        lay.addSpacing(4)
        lay.addWidget(_val("_kb_preset"))
        lay.addSpacing(12)
        lay.addWidget(_sep())
        lay.addSpacing(12)
        lay.addWidget(_cap("WEIGHTS:"))
        lay.addSpacing(4)
        lay.addWidget(_val("_kb_weights"))
        lay.addSpacing(12)
        lay.addWidget(_sep())
        lay.addSpacing(12)
        lay.addWidget(_cap("BIAS:"))
        lay.addSpacing(4)
        lay.addWidget(_val("_kb_bias"))
        lay.addSpacing(12)
        lay.addWidget(_sep())
        lay.addSpacing(12)
        lay.addWidget(_cap("THRESHOLD:"))
        lay.addSpacing(4)
        lay.addWidget(_val("_kb_threshold"))
        lay.addSpacing(12)
        lay.addWidget(_sep())
        lay.addSpacing(12)
        lay.addWidget(_cap("SOURCE:"))
        lay.addSpacing(4)
        lay.addWidget(_val("_kb_source"))
        lay.addStretch()
        return bar

    def _update_kernel_bar(self) -> None:
        """Refresh all kernel bar labels from current _kernel_cfg / _golden_source."""
        cfg = self._kernel_cfg
        if not cfg:
            for attr in ("_kb_preset", "_kb_weights", "_kb_bias", "_kb_threshold"):
                getattr(self, attr).setText("—")
                getattr(self, attr).setToolTip("")
            self._kb_source.setText("—")
            return

        self._kb_preset.setText(cfg.get("preset_name", "CUSTOM"))

        w = cfg.get("weights")
        if w:
            # Inline display: [ r0 | r1 | r2 ]
            rows_inline = "  |  ".join(
                " ".join(str(v) for v in row) for row in w
            )
            self._kb_weights.setText(f"[ {rows_inline} ]")
            # Tooltip shows aligned grid
            tip_rows = "\n".join(
                "  [ " + "  ".join(f"{v:4d}" for v in row) + " ]"
                for row in w
            )
            self._kb_weights.setToolTip(f"Kernel weights:\n{tip_rows}")
        else:
            self._kb_weights.setText("—")
            self._kb_weights.setToolTip("")

        self._kb_bias.setText(str(cfg.get("bias", 0)))
        self._kb_threshold.setText(str(cfg.get("threshold", 0)))

        src_map = {
            "none":           "—",
            "generator":      "✓ Generator",
            "external":       "⚠ External",
            "external+params": "✓ External + params",
        }
        self._kb_source.setText(src_map.get(self._golden_source, "—"))

    @staticmethod
    def _parse_stimulus_kernel(path: str) -> dict | None:
        """
        Read the first 13 lines of a stimulus .hex file and extract the
        kernel configuration: 9 weight bytes, 1 bias byte, 3 threshold bytes
        (little-endian 20-bit).  Returns a dict suitable for _kernel_cfg,
        or None if the file cannot be parsed.
        """
        try:
            with open(path, "r") as fh:
                lines = [fh.readline().strip() for _ in range(13)]
            weights = [
                [int(lines[r * 3 + c], 16) for c in range(3)]
                for r in range(3)
            ]
            bias      = int(lines[9], 16)
            threshold = (
                int(lines[10], 16)
                | (int(lines[11], 16) << 8)
                | (int(lines[12], 16) << 16)
            )
            return {
                "preset_name": "—",
                "weights":     weights,
                "bias":        bias,
                "threshold":   threshold,
            }
        except Exception:
            return None

    # ── Right tab panel ───────────────────────────────────────────────────────

    def _build_right_panel(self) -> QTabWidget:
        """
        Three-tab panel on the right side of the Analyst layout.
          Tab 0 — RESULTS  : Comparison results (match rate, errors)
          Tab 1 — MISMATCH : Full mismatch table + CSV export
          Tab 2 — LOG      : Activity log
        Synthesis metrics and power graph are in the Synthesis Reports tab.
        """
        tabs = QTabWidget()
        tabs.setObjectName("right_tabs")
        tabs.tabBar().setExpanding(True)

        tabs.addTab(self._build_results_panel(),  "RESULTS")
        tabs.addTab(self._build_mismatch_panel(), "MISMATCH")
        tabs.addTab(self._build_log_panel(),      "LOG")

        self._metric_fields: dict = {}   # kept as empty dict for session compat

        AppLogger.instance().sig_entry.connect(self._on_log_entry)

        return tabs

    # ── Comparison panel ──────────────────────────────────────────────────────

    def _build_comparison_panel(self) -> _ComparisonGroupBox:
        grp = _ComparisonGroupBox("VISUAL COMPARISON")
        grp.setMinimumWidth(480)
        lay = QHBoxLayout(grp)   # ← horizontal: Original Input | Golden Model | Chip DUT
        lay.setSpacing(6)
        lay.setContentsMargins(4, 10, 4, 4)

        self._disp_original = ImageDisplay("ORIGINAL INPUT", "LOAD IMAGE / VIDEO  or  DRAG & DROP")
        self._disp_golden   = ImageDisplay("GOLDEN MODEL",   "LOAD REFERENCE  or  DRAG & DROP")
        self._disp_chip     = ImageDisplay("CHIP DUT",       "LOAD CHIP OUTPUT  or  DRAG & DROP")

        # Drag & drop: image files → original, .txt/.hex → golden or chip
        self._disp_original.sig_file_dropped.connect(self._drop_original)
        self._disp_golden.sig_file_dropped.connect(self._drop_golden)
        self._disp_chip.sig_file_dropped.connect(self._drop_chip)

        lay.addWidget(self._disp_original, stretch=1)
        lay.addWidget(self._disp_golden,   stretch=1)
        lay.addWidget(self._disp_chip,     stretch=1)

        return grp

    # ── Results panel (comparison stats only) ────────────────────────────────

    def _build_results_panel(self) -> QWidget:
        frame = QWidget()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(10)

        title = QLabel("COMPARISON RESULTS")
        title.setObjectName("lbl_section")
        lay.addWidget(title)

        stats_grid = QGridLayout()
        stats_grid.setSpacing(6)

        self._lbl_total_px    = self._stat_row(stats_grid, 0, "TOTAL VALID PX", "—",    "lbl_stat_value")
        self._lbl_match_px    = self._stat_row(stats_grid, 1, "MATCHING",        "—",    "lbl_match_rate")
        self._lbl_mismatch_px = self._stat_row(stats_grid, 2, "MISMATCHES",      "—",    "lbl_error_count")
        self._lbl_match_pct   = self._stat_row(stats_grid, 3, "MATCH RATE",      "—  %", "lbl_match_rate")
        lay.addLayout(stats_grid)

        sep = QFrame()
        sep.setObjectName("nav_separator")
        lay.addWidget(sep)


        return frame

    # ── Mismatch panel ────────────────────────────────────────────────────────

    def _build_mismatch_panel(self) -> QWidget:
        """Dedicated tab: full mismatch table (top 1000 shown) + CSV export."""
        frame = QWidget()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)

        # Header row: title + count label + export button
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)

        tbl_title = QLabel("MISMATCH DETAILS")
        tbl_title.setObjectName("lbl_section")
        hdr_row.addWidget(tbl_title)

        self._mismatch_count_lbl = QLabel("")
        self._mismatch_count_lbl.setObjectName("img_info")
        hdr_row.addWidget(self._mismatch_count_lbl)

        hdr_row.addStretch()

        export_btn = QPushButton("Export CSV")
        export_btn.setObjectName("btn_success")
        export_btn.setFixedHeight(26)
        export_btn.setToolTip("Export all mismatches to a CSV file")
        export_btn.clicked.connect(self._export_mismatch_csv)
        hdr_row.addWidget(export_btn)

        lay.addLayout(hdr_row)

        # Full mismatch table — no row limit
        self._mismatch_tbl = QTableWidget(0, 3)
        self._mismatch_tbl.setHorizontalHeaderLabels(["Row", "Col", "Expected / Got"])
        self._mismatch_tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._mismatch_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._mismatch_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._mismatch_tbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        lay.addWidget(self._mismatch_tbl, stretch=1)

        return frame

    # ── Log panel ─────────────────────────────────────────────────────────────

    def _build_log_panel(self) -> QWidget:
        """Activity log tab — shows all AppLogger entries with colour coding."""
        from PyQt6.QtWidgets import QTextEdit, QScrollBar
        frame = QWidget()
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        log_title = QLabel("ACTIVITY LOG")
        log_title.setObjectName("lbl_section")
        hdr_row.addWidget(log_title)
        hdr_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("btn_warn")
        clear_btn.setFixedHeight(24)
        clear_btn.setFixedWidth(58)
        clear_btn.clicked.connect(self._log_clear)
        hdr_row.addWidget(clear_btn)

        export_log_btn = QPushButton("Export")
        export_log_btn.setObjectName("btn_success")
        export_log_btn.setFixedHeight(24)
        export_log_btn.setMinimumWidth(64)
        export_log_btn.clicked.connect(self._log_export)
        hdr_row.addWidget(export_log_btn)

        lay.addLayout(hdr_row)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setObjectName("log_view")
        self._log_view.setStyleSheet(
            "QTextEdit#log_view { background:#0D0D10; color:#8A8A8E; "
            "font-family:'Consolas','Courier New',monospace; font-size:10px; "
            "border:1px solid #2A2A2E; border-radius:4px; }"
        )
        lay.addWidget(self._log_view, stretch=1)

        # Populate with any existing entries
        for line in AppLogger.instance().all_lines():
            self._append_log_line(line)

        return frame

    def _on_log_entry(self, level: str, line: str) -> None:
        """Slot: called whenever AppLogger emits a new entry."""
        if hasattr(self, "_log_view"):
            self._append_log_line(line)

    def _append_log_line(self, line: str) -> None:
        """Append a colour-coded line to the log view."""
        colours = {
            "OK":    "#34C759",
            "ERROR": "#FF453A",
            "WARN":  "#FF9F0A",
            "INFO":  "#8A8A8E",
        }
        level_key = next((k for k in colours if k in line.upper()[:20]), "INFO")
        colour = colours[level_key]
        self._log_view.append(
            f'<span style="color:{colour}; font-family:Consolas,monospace; font-size:10px;">'
            f'{line}</span>'
        )
        # Auto-scroll to bottom
        sb = self._log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _log_clear(self) -> None:
        AppLogger.instance().clear()
        if hasattr(self, "_log_view"):
            self._log_view.clear()

    def _log_export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Activity Log", "activity_log.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            AppLogger.instance().export_to_file(path)
            self._set_status(f"Log exported → {os.path.basename(path)}", self.STATUS_OK)
        except Exception as exc:
            self._set_status(f"Log export error: {exc}", self.STATUS_ERR)

    @staticmethod
    def _stat_row(grid: QGridLayout, row: int, name: str, default: str, val_obj: str) -> QLabel:
        n = QLabel(name)
        n.setObjectName("lbl_metric_name")
        v = QLabel(default)
        v.setObjectName(val_obj)
        grid.addWidget(n, row, 0)
        grid.addWidget(v, row, 1)
        return v

    # ══════════════════════════════════════════════════════════════════════════
    # Logic — Import
    # ══════════════════════════════════════════════════════════════════════════

    def _load_chip_output(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Chip Output", "",
            "Text / Hex (*.txt *.hex);;All Files (*)"
        )
        if not path:
            return
        try:
            bits = self._parse_output_file(path)
            self._chip = bits
            self._clear_video_state()          # single-frame → clear any video
            self._disp_chip.set_image(bits * 255, info=f"ones={bits.sum()}")
            self._set_status(f"Chip output loaded: {os.path.basename(path)}", self.STATUS_OK)
            AppLogger.instance().ok(f"Chip output loaded: {os.path.basename(path)}")
        except Exception as exc:
            self._set_status(f"Load error: {exc}", self.STATUS_ERR)
            AppLogger.instance().error(f"Load chip error: {exc}")

    def _load_golden_ref(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Golden Scoreboard / Reference", "",
            "Text Files (*.txt);;Hex Files (*.hex);;All Files (*)"
        )
        if not path:
            return
        try:
            bits = self._parse_output_file(path)
            self._golden = bits
            self._clear_video_state()          # single-frame → clear any video
            # Try to auto-load run_params.json from the same directory
            self._golden_source = "external"
            self._kernel_cfg = {}
            params_path = os.path.join(os.path.dirname(path), "run_params.json")
            if os.path.isfile(params_path):
                self._load_run_params(params_path)
                self._golden_source = "external+params"
                info_extra = "  [params loaded]"
            else:
                info_extra = ""
            self._disp_golden.set_image(bits * 255, info=f"ones={bits.sum()}{info_extra}")
            self._set_status(f"Golden reference loaded: {os.path.basename(path)}", self.STATUS_OK)
            AppLogger.instance().ok(f"Golden reference loaded: {os.path.basename(path)}")
        except Exception as exc:
            self._set_status(f"Load error: {exc}", self.STATUS_ERR)
            AppLogger.instance().error(f"Load golden error: {exc}")

    def _load_run_params(self, path: str) -> None:
        """Parse run_params.json and update self._kernel_cfg."""
        import json
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._kernel_cfg = {
            "weights":     data.get("weights"),
            "bias":        data.get("bias", 0),
            "threshold":   data.get("threshold", 2000),
            "preset_name": data.get("preset_name", "CUSTOM"),
        }
        AppLogger.instance().ok(
            f"Kernel params auto-loaded from {os.path.basename(path)}"
        )
        self._update_kernel_bar()

    def _load_run_folder(self):
        """
        Import a complete gui_run_* folder.
        Loads golden scoreboard from golden/, original input frames from
        visual_input/, kernel params from run_params.json, and — if an
        actual/ subfolder exists — automatically loads it as chip output
        and runs the comparison.  All in one step.
        """
        folder = QFileDialog.getExistingDirectory(
            self, "Select Run Folder (gui_run_…)"
        )
        if not folder:
            return

        score_dir   = os.path.join(folder, "golden")
        # Support both new (visual_input) and old (3_visual_input) naming
        input_dir   = os.path.join(folder, "visual_input")
        if not os.path.isdir(input_dir):
            input_dir = os.path.join(folder, "3_visual_input")
        actual_dir  = os.path.join(folder, "actual")
        params_path = os.path.join(folder, "run_params.json")

        if not os.path.isdir(score_dir):
            self._set_status(
                "No golden/ subfolder found — is this a valid run folder?",
                self.STATUS_ERR,
            )
            return

        # Kernel params
        self._golden_source = "external"
        self._kernel_cfg = {}
        if os.path.isfile(params_path):
            self._load_run_params(params_path)
            self._golden_source = "external+params"
        self._update_kernel_bar()

        # Parse per-frame kernel configs from stimulus/ hex files
        self._per_frame_kernel_cfgs = []
        stim_dir = os.path.join(folder, "stimulus")
        if os.path.isdir(stim_dir):
            hex_files = sorted(
                (fn for fn in os.listdir(stim_dir) if fn.lower().endswith(".hex")),
                key=_natural_sort_key,
            )
            for hf in hex_files:
                cfg = self._parse_stimulus_kernel(os.path.join(stim_dir, hf))
                if cfg is not None:
                    self._per_frame_kernel_cfgs.append(cfg)

        # Discover golden scoreboard files
        txt_files = sorted(
            (fn for fn in os.listdir(score_dir) if fn.lower().endswith(".txt")),
            key=_natural_sort_key,
        )
        if not txt_files:
            self._set_status(
                "No .txt scoreboard files found in golden/",
                self.STATUS_ERR,
            )
            return

        # Discover original input images
        img_files: list[str] = []
        if os.path.isdir(input_dir):
            img_files = sorted(
                (fn for fn in os.listdir(input_dir)
                 if fn.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"))),
                key=_natural_sort_key,
            )

        # Discover DUT actual output files
        actual_files: list[str] = []
        if os.path.isdir(actual_dir):
            actual_files = sorted(
                (fn for fn in os.listdir(actual_dir) if fn.lower().endswith(".txt")),
                key=_natural_sort_key,
            )

        n = len(txt_files)
        if n == 1:
            # ── Single-frame ─────────────────────────────────────────────────
            try:
                bits = self._parse_output_file(os.path.join(score_dir, txt_files[0]))
            except Exception as exc:
                self._set_status(f"Golden load error: {exc}", self.STATUS_ERR)
                return
            self._golden = bits
            self._clear_video_state()
            info_extra = "  [params]" if self._golden_source == "external+params" else ""
            self._disp_golden.set_image(bits * 255, info=f"ones={bits.sum()}{info_extra}")

            # Load original input image if present
            if img_files:
                img_path = os.path.join(input_dir, img_files[0])
                _loaded = False
                try:
                    import cv2 as _cv2
                    raw = np.fromfile(img_path, dtype=np.uint8)
                    img = _cv2.imdecode(raw, _cv2.IMREAD_GRAYSCALE)
                    if img is None:
                        raise ValueError("cv2 decode returned None")
                    img = _cv2.resize(img, (256, 256), interpolation=_cv2.INTER_AREA)
                    self._image = img.astype(np.uint8)
                    self._video_frames = []
                    self._disp_original.set_image(self._image, info=img_files[0])
                    _loaded = True
                except Exception as _e1:
                    AppLogger.instance().warn(f"cv2 load failed ({_e1}), trying PIL…")
                if not _loaded:
                    try:
                        from PIL import Image as _Pil
                        pil = _Pil.open(img_path).convert("L").resize((256, 256))
                        self._image = np.array(pil, dtype=np.uint8)
                        self._video_frames = []
                        self._disp_original.set_image(self._image, info=img_files[0])
                        _loaded = True
                    except Exception as _e2:
                        AppLogger.instance().warn(
                            f"PIL load also failed ({_e2}) — original input skipped")

            # ── Auto-load DUT actual output and compare ───────────────────────
            if actual_files:
                try:
                    chip_bits = self._parse_output_file(
                        os.path.join(actual_dir, actual_files[0]))
                    self._chip = chip_bits
                    self._disp_chip.set_image(
                        chip_bits * 255, info=f"ones={chip_bits.sum()}  [actual/]")
                    AppLogger.instance().ok(
                        f"DUT actual auto-loaded: {actual_files[0]}")
                    self._run_comparison()
                except Exception as exc:
                    AppLogger.instance().warn(f"actual/ auto-load failed: {exc}")

            _has_actual = bool(actual_files)
            self._set_status(
                f"Run folder loaded: {os.path.basename(folder)}  (1 frame)"
                + ("  — comparison auto-run ✓" if _has_actual else ""),
                self.STATUS_OK,
            )
            AppLogger.instance().ok(f"Run folder loaded: {os.path.basename(folder)}")
        else:
            # ── Multi-frame: load golden then original then actual ────────────
            self._pending_input_dir   = input_dir
            self._pending_img_files   = img_files
            self._pending_actual_dir  = actual_dir
            self._pending_actual_files = actual_files
            self._pending_run_folder  = folder
            self._cancel_loading = False
            self._overlay.show_loading(
                "Loading Run Folder…",
                f"Reading {n} golden scoreboard frames…",
                cancellable=True,
            )
            worker = _TxtVideoLoaderWorker(txt_files, score_dir, self._parse_output_file)
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.progress.connect(self._overlay.set_message)
            worker.finished.connect(
                lambda frames, t=thread, w=worker: self._on_run_folder_golden_done(frames, t, w)
            )
            worker.error.connect(lambda msg: self._on_load_error(msg, thread))
            self._overlay.sig_cancel.connect(worker.cancel)
            self._load_thread = thread
            self._load_worker = worker
            thread.start()

    def _on_run_folder_golden_done(self, frames: list, thread: QThread, worker) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(worker.cancel)
        except Exception:
            pass
        if not frames:
            self._overlay.hide_loading()
            self._set_status("Run folder load cancelled.", self.STATUS_INFO)
            return
        self._golden_frames = frames
        n = len(frames)
        folder     = getattr(self, "_pending_run_folder", "")
        input_dir  = getattr(self, "_pending_input_dir", "")
        img_files  = getattr(self, "_pending_img_files", [])

        if img_files and os.path.isdir(input_dir):
            # Continue to load original input frames
            self._overlay.set_message(f"Reading {len(img_files)} input frames…")
            w2 = _ImgVideoLoaderWorker(img_files, input_dir)
            t2 = QThread()
            w2.moveToThread(t2)
            t2.started.connect(w2.run)
            w2.progress.connect(self._overlay.set_message)
            w2.finished.connect(
                lambda imgs, t=t2, w=w2: self._on_run_folder_input_done(imgs, n, folder, t, w)
            )
            w2.error.connect(lambda msg: self._on_load_error(msg, t2))
            self._overlay.sig_cancel.connect(w2.cancel)
            self._load_thread = t2
            self._load_worker = w2
            t2.start()
        else:
            # No input images — try actual/ then finish
            actual_dir   = getattr(self, "_pending_actual_dir",   "")
            actual_files = getattr(self, "_pending_actual_files", [])
            if actual_files and os.path.isdir(actual_dir):
                try:
                    chip_frames = [
                        self._parse_output_file(os.path.join(actual_dir, fn))
                        for fn in actual_files
                    ]
                    self._chip_frames = chip_frames
                    self._chip = chip_frames[0]
                    self._disp_chip.set_image(
                        chip_frames[0] * 255,
                        info=f"ones={chip_frames[0].sum()}  [actual/ frame 1/{len(chip_frames)}]")
                    AppLogger.instance().ok(
                        f"DUT actual auto-loaded: {len(chip_frames)} frames from actual/")
                except Exception as exc:
                    AppLogger.instance().warn(f"actual/ auto-load failed: {exc}")

            self._overlay.hide_loading()
            n_total = max(n, len(self._chip_frames))
            self._an_slider.setMaximum(n_total - 1)
            self._video_nav.setVisible(True)
            self._set_analyst_frame(0)
            has_actual = bool(actual_files)
            self._set_status(
                f"Run folder loaded: {os.path.basename(folder)}  ({n} frames)"
                + ("  — actual/ auto-loaded ✓" if has_actual else "  (no input images)"),
                self.STATUS_OK,
            )
            AppLogger.instance().ok(f"Run folder loaded: {os.path.basename(folder)}")

    def _on_run_folder_input_done(self, imgs: list, n_golden: int,
                                  folder: str, thread: QThread, worker) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(worker.cancel)
        except Exception:
            pass
        self._overlay.hide_loading()
        if imgs:
            self._video_frames = imgs
            if imgs:
                self._image = imgs[0]
                self._disp_original.set_image(imgs[0], info=f"{len(imgs)} frames")
        # ── Auto-load DUT actual/ frames if available ─────────────────────
        actual_dir   = getattr(self, "_pending_actual_dir",   "")
        actual_files = getattr(self, "_pending_actual_files", [])
        if actual_files and os.path.isdir(actual_dir):
            try:
                chip_frames = [
                    self._parse_output_file(os.path.join(actual_dir, fn))
                    for fn in actual_files
                ]
                self._chip_frames = chip_frames
                self._chip = chip_frames[0]
                self._disp_chip.set_image(
                    chip_frames[0] * 255,
                    info=f"ones={chip_frames[0].sum()}  [actual/ frame 1/{len(chip_frames)}]")
                AppLogger.instance().ok(
                    f"DUT actual auto-loaded: {len(chip_frames)} frames from actual/")
            except Exception as exc:
                AppLogger.instance().warn(f"actual/ auto-load failed: {exc}")

        n_total = max(n_golden, len(self._chip_frames))
        self._an_slider.setMaximum(n_total - 1)
        self._video_nav.setVisible(True)
        self._set_analyst_frame(0)
        has_actual = bool(actual_files)
        self._set_status(
            f"Run folder loaded: {os.path.basename(folder)}  ({n_golden} frames)"
            + ("  — actual/ auto-loaded ✓" if has_actual else ""),
            self.STATUS_OK,
        )
        AppLogger.instance().ok(f"Run folder loaded: {os.path.basename(folder)}")

    def _load_chip_video(self):
        """Load chip video frames from a folder of .txt files — runs in a worker thread."""
        folder = QFileDialog.getExistingDirectory(self, "Select Chip Video Folder")
        if not folder:
            return
        files = sorted(
            (fn for fn in os.listdir(folder) if fn.lower().endswith(".txt")),
            key=_natural_sort_key,
        )
        if not files:
            self._set_status("No .txt files found in the selected folder", self.STATUS_ERR)
            return
        self._cancel_loading = False
        self._overlay.show_loading(
            "Loading Chip Video…",
            f"Reading {len(files)} frame files…",
            cancellable=True,
        )
        worker = _TxtVideoLoaderWorker(files, folder, self._parse_output_file)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._overlay.set_message)
        worker.finished.connect(
            lambda frames: self._on_chip_video_done(frames, folder, thread, worker)
        )
        worker.error.connect(lambda msg: self._on_load_error(msg, thread))
        self._overlay.sig_cancel.connect(worker.cancel)
        self._load_thread = thread
        self._load_worker = worker
        thread.start()

    def _on_chip_video_done(self, frames: list, folder: str,
                            thread: QThread, worker) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(worker.cancel)
        except Exception:
            pass
        self._overlay.hide_loading()
        if not frames:
            self._set_status("Chip video load cancelled.", self.STATUS_INFO)
            return
        self._chip_frames = frames
        n_frames = len(frames)
        n_total  = max(n_frames, len(self._golden_frames))
        self._an_slider.setMaximum(n_total - 1)
        self._video_nav.setVisible(True)
        self._set_analyst_frame(0)
        self._set_status(
            f"Chip video loaded: {n_frames} frames from '{os.path.basename(folder)}'",
            self.STATUS_OK,
        )

    def _load_golden_video(self):
        """Load golden video frames from a folder of .txt files — runs in a worker thread."""
        folder = QFileDialog.getExistingDirectory(self, "Select Golden Video Folder")
        if not folder:
            return
        files = sorted(
            (fn for fn in os.listdir(folder) if fn.lower().endswith(".txt")),
            key=_natural_sort_key,
        )
        if not files:
            self._set_status("No .txt files found in the selected folder", self.STATUS_ERR)
            return
        self._cancel_loading = False
        self._overlay.show_loading(
            "Loading Golden Video…",
            f"Reading {len(files)} frame files…",
            cancellable=True,
        )
        worker = _TxtVideoLoaderWorker(files, folder, self._parse_output_file)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._overlay.set_message)
        worker.finished.connect(
            lambda frames: self._on_golden_video_done(frames, folder, thread, worker)
        )
        worker.error.connect(lambda msg: self._on_load_error(msg, thread))
        self._overlay.sig_cancel.connect(worker.cancel)
        self._load_thread = thread
        self._load_worker = worker
        thread.start()

    def _on_golden_video_done(self, frames: list, folder: str,
                              thread: QThread, worker) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(worker.cancel)
        except Exception:
            pass
        self._overlay.hide_loading()
        if not frames:
            self._set_status("Golden video load cancelled.", self.STATUS_INFO)
            return
        self._golden_frames = frames
        n_frames = len(frames)
        n_total  = max(n_frames, len(self._chip_frames))
        self._an_slider.setMaximum(n_total - 1)
        self._video_nav.setVisible(True)
        self._set_analyst_frame(0)
        self._set_status(
            f"Golden video loaded: {n_frames} frames from '{os.path.basename(folder)}'",
            self.STATUS_OK,
        )

    def _on_cancel_loading(self):
        self._cancel_loading = True
        # worker.cancel() is connected directly to sig_cancel when a worker is active;
        # fall back to hiding immediately only when no worker thread is running.
        if self._load_worker is None:
            self._overlay.hide_loading()

    def _load_original_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Original Input Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif);;All Files (*)"
        )
        if not path:
            return
        try:
            import cv2 as _cv2
            raw = __import__('numpy').fromfile(path, dtype=__import__('numpy').uint8)
            img = _cv2.imdecode(raw, _cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError("Could not decode image")
            img = _cv2.resize(img, (256, 256), interpolation=_cv2.INTER_AREA)
            self._image = img.astype(__import__('numpy').uint8)
            self._video_frames = []
            self._disp_original.set_image(self._image, info=os.path.basename(path))
            self._set_status(f"Original input loaded: {os.path.basename(path)}", self.STATUS_OK)
        except Exception:
            try:
                from PIL import Image as _Pil
                img = _Pil.open(path).convert("L").resize((256, 256))
                self._image = __import__('numpy').array(img, dtype=__import__('numpy').uint8)
                self._video_frames = []
                self._disp_original.set_image(self._image, info=os.path.basename(path))
                self._set_status(f"Original input loaded: {os.path.basename(path)}", self.STATUS_OK)
            except Exception as exc:
                self._set_status(f"Load error: {exc}", self.STATUS_ERR)

    def _load_original_video(self):
        """Load original input frames from an image folder — runs in a worker thread."""
        folder = QFileDialog.getExistingDirectory(self, "Select Original Input Video Folder")
        if not folder:
            return
        files = sorted(
            (fn for fn in os.listdir(folder)
             if fn.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'))),
            key=_natural_sort_key,
        )
        if not files:
            self._set_status("No image files found in the selected folder", self.STATUS_ERR)
            return
        self._cancel_loading = False
        self._overlay.show_loading(
            "Loading Original Video…",
            f"Reading {len(files)} frames…",
            cancellable=True,
        )
        worker = _ImgVideoLoaderWorker(files, folder)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._overlay.set_message)
        worker.finished.connect(
            lambda frames: self._on_original_video_done(frames, folder, thread, worker)
        )
        worker.error.connect(lambda msg: self._on_load_error(msg, thread))
        self._overlay.sig_cancel.connect(worker.cancel)
        self._load_thread = thread
        self._load_worker = worker
        thread.start()

    def _on_original_video_done(self, frames: list, folder: str,
                                thread: QThread, worker) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(worker.cancel)
        except Exception:
            pass
        self._overlay.hide_loading()
        if not frames:
            self._set_status("Original video load cancelled.", self.STATUS_INFO)
            return
        self._video_frames = frames
        if frames:
            self._image = frames[0]
            self._disp_original.set_image(frames[0], info=f"{len(frames)} frames")
        self._set_status(
            f"Original video loaded: {len(frames)} frames from '{os.path.basename(folder)}'",
            self.STATUS_OK,
        )

    def _on_load_error(self, msg: str, thread: QThread) -> None:
        thread.quit()
        thread.wait()
        self._overlay.hide_loading()
        self._set_status(f"Load error: {msg}", self.STATUS_ERR)

    # ── Output file parsing ───────────────────────────────────────────────────

    @staticmethod
    def _parse_output_file(path: str) -> np.ndarray:
        """
        Parse a chip-output or scoreboard file.
        Supported formats:
          A) Legacy scoreboard: '1 0' or '0 0' per line (valid result) → take result where valid=1
          B) Raw bits  : '0' or '1' per line (64,516 lines = 254×254)
          C) Hex bits  : '00' or '01' per line
        Returns 254×254 uint8 array (0 or 1).
        """
        bits = np.zeros(254 * 254, dtype=np.uint8)

        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.startswith("//")]

        if len(lines) == 0:
            raise ValueError("Empty file")

        # Detect format
        first = lines[0].split()
        if len(first) == 2:
            # Legacy scoreboard format: "valid result" — 65,536 lines (256×256)
            idx = 0
            done = False
            for r in range(256):
                if done:
                    break
                for c in range(256):
                    line_idx = r * 256 + c
                    if line_idx >= len(lines):
                        done = True
                        break
                    parts = lines[line_idx].split()
                    valid = int(parts[0]) if parts else 0
                    result = int(parts[1]) if len(parts) > 1 else 0
                    if valid and r >= 2 and c >= 2:
                        bits[idx] = result & 1
                        idx += 1
        else:
            # Raw single-value per line — require at least 254×254 values
            if len(lines) < 254 * 254:
                raise ValueError(
                    f"Output file is truncated: expected at least {254*254:,} lines "
                    f"(254×254 valid pixels), got {len(lines):,}. "
                    "The file may be incomplete or from an aborted simulation."
                )
            raw = []
            for l in lines:
                try:
                    raw.append(int(l, 16) & 1)
                except ValueError:
                    pass
            expected = 254 * 254
            if len(raw) >= expected:
                bits = np.array(raw[:expected], dtype=np.uint8)
            else:
                bits[:len(raw)] = raw

        return bits.reshape(254, 254)

    @staticmethod
    def _parse_output_lines(lines: list) -> np.ndarray:
        """
        Same logic as _parse_output_file but from a pre-read list of stripped lines.
        Used for splitting a merged multi-frame chip video file into per-frame arrays.
        """
        bits = np.zeros(254 * 254, dtype=np.uint8)
        if not lines:
            return bits.reshape(254, 254)

        first = lines[0].split()
        if len(first) == 2:
            # Legacy scoreboard format: "valid result" — 65,536 lines
            idx = 0
            done = False
            for r in range(256):
                if done:
                    break
                for c in range(256):
                    li = r * 256 + c
                    if li >= len(lines):
                        done = True
                        break
                    parts = lines[li].split()
                    valid  = int(parts[0]) if parts else 0
                    result = int(parts[1]) if len(parts) > 1 else 0
                    if valid and r >= 2 and c >= 2:
                        bits[idx] = result & 1
                        idx += 1
        else:
            # Raw single-value per line (254×254 = 64,516 lines)
            raw = []
            for ln in lines:
                try:
                    raw.append(int(ln, 16) & 1)
                except ValueError:
                    pass
            expected = 254 * 254
            if len(raw) >= expected:
                bits = np.array(raw[:expected], dtype=np.uint8)
            else:
                bits[:len(raw)] = raw

        return bits.reshape(254, 254)


    # ══════════════════════════════════════════════════════════════════════════
    # Logic — Comparison
    # ══════════════════════════════════════════════════════════════════════════

    def _run_comparison(self):
        if self._golden is None:
            self._set_status("Load golden reference first.", self.STATUS_ERR)
            return
        if self._chip is None:
            self._set_status("Load chip output first.", self.STATUS_ERR)
            return

        g = self._golden
        c = self._chip

        if g.shape != c.shape:
            self._set_status(
                f"Shape mismatch: golden={g.shape}, chip={c.shape}",
                self.STATUS_ERR
            )
            return

        # Compute stats
        total    = g.size
        matches  = int(np.sum(g == c))
        errors   = total - matches
        rate_pct = 100.0 * matches / total

        # Update stat labels
        self._lbl_total_px.setText(f"{total:,}")
        self._lbl_match_px.setText(f"{matches:,}")
        self._lbl_mismatch_px.setText(f"{errors:,}")
        self._lbl_match_pct.setText(f"{rate_pct:.4f}  %")
        self._match_badge.setText(f"{rate_pct:.2f}%")

        # Refresh golden/chip displays
        self._disp_golden.set_image(g * 255, info=f"ones={g.sum()}")
        self._disp_chip.set_image(c * 255, info=f"ones={c.sum()}")

        # Fill mismatch table
        self._fill_mismatch_table(g, c)




        # Store comparison result for report export
        self._last_match_rate  = rate_pct
        self._last_errors      = errors
        self._last_total_valid = total

        status_style = self.STATUS_OK if errors == 0 else self.STATUS_ERR
        msg = f"Comparison complete — {errors} errors / {total} pixels  ({rate_pct:.4f}% match)"
        self._set_status(msg, status_style)
        if errors == 0:
            AppLogger.instance().ok(msg)
        else:
            AppLogger.instance().warn(msg)

    def _fill_mismatch_table(self, golden: np.ndarray, chip: np.ndarray):
        self._mismatch_tbl.setRowCount(0)
        # Store ALL mismatches for CSV export
        all_mismatches = np.argwhere(golden != chip)   # (N, 2): row, col in 254×254 space
        self._mismatch_coords = [(int(r), int(c),
                                  int(golden[r, c]), int(chip[r, c]))
                                 for r, c in all_mismatches]

        total = len(self._mismatch_coords)
        _DISPLAY_LIMIT = 1000
        shown = min(total, _DISPLAY_LIMIT)

        for i, (r, c, exp, got) in enumerate(self._mismatch_coords[:_DISPLAY_LIMIT]):
            row_item = QTableWidgetItem(str(r + 2))    # +2 → 256×256 space
            col_item = QTableWidgetItem(str(c + 2))
            exp_got  = QTableWidgetItem(f"golden={exp}  chip={got}")
            row_item.setForeground(QBrush(QColor("#ffd700")))
            col_item.setForeground(QBrush(QColor("#ffd700")))
            exp_got.setForeground(QBrush(QColor("#ff4444")))
            self._mismatch_tbl.insertRow(i)
            self._mismatch_tbl.setItem(i, 0, row_item)
            self._mismatch_tbl.setItem(i, 1, col_item)
            self._mismatch_tbl.setItem(i, 2, exp_got)

        if total > _DISPLAY_LIMIT:
            self._mismatch_tbl.insertRow(shown)
            overflow = QTableWidgetItem(
                f"… and {total - _DISPLAY_LIMIT:,} more — use Export CSV for full list"
            )
            overflow.setForeground(QBrush(QColor("#5a7090")))
            self._mismatch_tbl.setItem(shown, 2, overflow)

        # Update count label
        count_text = f"{total:,} mismatch{'es' if total != 1 else ''}"
        if total > _DISPLAY_LIMIT:
            count_text += f"  (showing {_DISPLAY_LIMIT:,})"
        self._mismatch_count_lbl.setText(count_text)

    def _export_mismatch_csv(self):
        if not self._mismatch_coords:
            self._set_status("No mismatch data to export — run Compare first.", self.STATUS_ERR)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Mismatch Table", "mismatch_details.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Row (256-space)", "Col (256-space)", "Golden", "Chip"])
                for r, c, exp, got in self._mismatch_coords:
                    writer.writerow([r + 2, c + 2, exp, got])
            self._set_status(
                f"Exported {len(self._mismatch_coords):,} rows → {os.path.basename(path)}",
                self.STATUS_OK,
            )
        except Exception as exc:
            self._set_status(f"Export error: {exc}", self.STATUS_ERR)

    def _export_report(self):
        """Generate a self-contained HTML verification report."""
        from ui.report_exporter import build_html_report, save_report
        import datetime
        default_name = (
            f"verification_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Verification Report", default_name,
            "HTML Files (*.html);;All Files (*)"
        )
        if not path:
            return
        try:
            # Build mismatch RGB if we have both arrays
            mm_rgb = None
            if self._golden is not None and self._chip is not None:
                mm_rgb = build_mismatch_rgb(self._golden, self._chip)

            kc = self._kernel_cfg
            # For video, use the currently-displayed frame as the original image
            orig_img = (
                self._video_frames[self._video_idx]
                if self._video_frames and 0 <= self._video_idx < len(self._video_frames)
                else self._image
            )
            # If comparison was never explicitly run but both arrays exist,
            # compute the stats on-the-fly so the report is never empty.
            match_rate   = self._last_match_rate
            errors_val   = self._last_errors
            total_val    = self._last_total_valid
            if match_rate is None and self._golden is not None and self._chip is not None:
                total_val  = self._golden.size
                errors_val = int(np.sum(self._golden != self._chip))
                match_rate = 100.0 * (total_val - errors_val) / total_val

            cfg = {
                "golden":        self._golden,
                "chip":          self._chip,
                "mismatch_rgb":  mm_rgb,
                "original":      orig_img,
                "weights":       kc.get("weights"),
                "bias":          kc.get("bias", 0),
                "threshold":     kc.get("threshold", 2000),
                "preset_name":   kc.get("preset_name", "CUSTOM"),
                "golden_source": self._golden_source,
                "match_rate":    match_rate,
                "errors":        errors_val,
                "total_valid":   total_val,
                "metrics": {
                    k: v.text() for k, v in self._metric_fields.items()
                },
                "log_lines": AppLogger.instance().all_lines(),
            }
            html = build_html_report(cfg)
            save_report(html, path)
            AppLogger.instance().ok(f"Report exported → {os.path.basename(path)}")
            self._set_status(
                f"Report saved → {os.path.basename(path)}  (open in any browser)",
                self.STATUS_OK,
            )
            # Auto-open in default browser
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception as exc:
            self._set_status(f"Report error: {exc}", self.STATUS_ERR)

    # ══════════════════════════════════════════════════════════════════════════
    # Public API — called from MainWindow to pre-populate from Generator
    # ══════════════════════════════════════════════════════════════════════════

    def update_kernel_cfg(self, cfg: dict) -> None:
        """Receive live kernel configuration from GeneratorWidget via sig_kernel_cfg."""
        self._kernel_cfg = cfg
        # Only update source to "generator" if no external golden was loaded
        if self._golden_source in ("none", "generator"):
            self._golden_source = "generator"
        self._update_kernel_bar()

    def load_from_generator(self, config: dict):
        """Pre-fill golden reference and original input from Generator Mode output."""
        # Capture kernel config snapshot at transfer time
        self._golden_source = "generator"
        self._kernel_cfg = {
            "weights":     config.get("weights").tolist()
                           if hasattr(config.get("weights"), "tolist")
                           else config.get("weights"),
            "bias":        config.get("bias", 0),
            "threshold":   config.get("threshold", 2000),
            "preset_name": config.get("preset_name", "CUSTOM"),
        }
        self._update_kernel_bar()
        video_frames  = config.get("video_frames",  [])
        golden_frames = config.get("golden_frames", [])

        if golden_frames and video_frames:
            # ── Multi-frame video path ────────────────────────────────────────
            self._video_frames  = video_frames
            self._golden_frames = golden_frames
            n = len(golden_frames)
            self._an_slider.setMaximum(n - 1)
            self._video_nav.setVisible(True)
            self._set_analyst_frame(0)
            self._set_status(
                f"Golden video imported: {n} frames from Generator Mode.",
                self.STATUS_OK
            )
        else:
            # ── Single-frame path ─────────────────────────────────────────────
            self._clear_video_state()
            golden = config.get("golden")
            image  = config.get("image")
            if golden is not None:
                self._golden = golden
                self._disp_golden.set_image(golden * 255, info=f"from generator | ones={golden.sum()}")
                self._set_status(
                    "Golden reference imported from Generator Mode.", self.STATUS_OK
                )
            if image is not None:
                self._image = image
                self._disp_original.set_image(image, info="from generator")

    # ══════════════════════════════════════════════════════════════════════════
    # Video frame navigation (multi-frame mode)
    # ══════════════════════════════════════════════════════════════════════════

    def _set_analyst_frame(self, idx: int):
        """Update all three displays and stats for the given frame index."""
        self._video_idx = idx
        n_total = max(len(self._golden_frames), len(self._chip_frames))
        self._an_frame_lbl.setText(f"Frame  {idx + 1}  /  {n_total}")
        self._an_slider.blockSignals(True)
        self._an_slider.setValue(idx)
        self._an_slider.blockSignals(False)

        # ── Golden display ────────────────────────────────────────────────────
        if idx < len(self._golden_frames):
            g = self._golden_frames[idx]
            self._golden = g
            self._disp_golden.set_image(g * 255, info=f"ones={g.sum()}")
        else:
            self._disp_golden.clear()

        # ── Chip display ──────────────────────────────────────────────────────
        if idx < len(self._chip_frames):
            c = self._chip_frames[idx]
            self._chip = c
            self._disp_chip.set_image(c * 255, info=f"ones={c.sum()}")
        else:
            self._disp_chip.clear()

        # ── Original input display ────────────────────────────────────────────
        if idx < len(self._video_frames):
            self._disp_original.set_image(self._video_frames[idx])
        elif self._image is not None and not self._video_frames:
            self._disp_original.set_image(self._image)

        # ── Per-frame kernel bar update ───────────────────────────────────────
        if self._per_frame_kernel_cfgs and idx < len(self._per_frame_kernel_cfgs):
            self._kernel_cfg = self._per_frame_kernel_cfgs[idx]
            self._update_kernel_bar()

        # ── Per-frame comparison stats ────────────────────────────────────────
        if (idx < len(self._golden_frames) and idx < len(self._chip_frames)):
            g = self._golden_frames[idx]
            c = self._chip_frames[idx]
            total   = g.size
            matches = int(np.sum(g == c))
            errors  = total - matches
            rate    = 100.0 * matches / total
            self._lbl_total_px.setText(f"{total:,}")
            self._lbl_match_px.setText(f"{matches:,}")
            self._lbl_mismatch_px.setText(f"{errors:,}")
            self._lbl_match_pct.setText(f"{rate:.4f}  %")
            self._match_badge.setText(f"{rate:.2f}%")
            self._fill_mismatch_table(g, c)
            # Keep report-export fields in sync with the displayed frame
            self._last_match_rate  = rate
            self._last_errors      = errors
            self._last_total_valid = total

    def _an_slider_changed(self, val: int):
        if self._golden_frames or self._chip_frames:
            self._set_analyst_frame(val)

    def go_to_frame(self, idx: int) -> None:
        """
        Called by MainWindow when GeneratorWidget playback advances a frame.
        Syncs the analyst display to the same frame index if video data is loaded.
        """
        if not (self._golden_frames or self._chip_frames):
            return
        n = max(len(self._golden_frames), len(self._chip_frames))
        self._set_analyst_frame(min(idx, n - 1))

    def _toggle_analyst_play(self):
        if self._is_playing:
            if self._play_timer:
                self._play_timer.stop()
            self._is_playing = False
            self._an_btn_play.setText("▶  Play")
        else:
            self._is_playing = True
            self._an_btn_play.setText("⏸  Pause")
            self._play_timer = QTimer(self)
            self._play_timer.timeout.connect(self._analyst_play_step)
            interval = max(1, int(1000 / self._an_fps_sb.value()))
            self._play_timer.start(interval)

    def _analyst_play_step(self):
        n = max(len(self._golden_frames), len(self._chip_frames))
        next_idx = self._video_idx + 1
        if next_idx >= n:
            next_idx = 0          # loop back to first frame
        self._set_analyst_frame(next_idx)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clear_video_state(self):
        """
        Called when a *single-frame* file is loaded, or when transitioning away
        from video mode.  Clears all multi-frame lists and hides the video
        navigation bar so the stale video sequence does not persist.
        """
        # Stop any running playback first
        if self._is_playing and self._play_timer:
            self._play_timer.stop()
            self._is_playing = False
            self._an_btn_play.setText("▶  Play")
        self._golden_frames = []
        self._chip_frames   = []
        self._video_frames  = []
        self._video_idx     = 0
        self._per_frame_kernel_cfgs = []
        # Hide the nav bar FIRST — ensures the slider cannot be interacted
        # with during the reset and that nothing can re-trigger _an_slider_changed
        self._video_nav.setVisible(False)
        # Reset slider with blockSignals so valueChanged cannot fire
        self._an_slider.blockSignals(True)
        self._an_slider.setValue(0)
        self._an_slider.setMaximum(0)
        self._an_slider.blockSignals(False)
        self._an_frame_lbl.setText("Frame  1  /  —")

    def _clear_all(self):
        """
        Full reset — wipes every loaded dataset, clears all displays,
        resets metrics/comparison results, and hides the video nav bar.
        Triggered by the 'Clear All' button in the import bar.
        """
        # ── State ──────────────────────────────────────────────────────────────
        self._golden = None
        self._chip   = None
        self._image  = None
        self._mismatch_coords  = []
        self._last_match_rate  = None
        self._last_errors      = None
        self._last_total_valid = None
        self._clear_video_state()   # clears video lists + hides video nav

        # ── Displays ───────────────────────────────────────────────────────────
        self._disp_original.clear()
        self._disp_golden.clear()
        self._disp_chip.clear()





        # ── Comparison result labels ────────────────────────────────────────────
        self._lbl_total_px.setText("—")
        self._lbl_match_px.setText("—")
        self._lbl_mismatch_px.setText("—")
        self._lbl_match_pct.setText("—  %")
        self._match_badge.setText("")

        # ── Mismatch table ─────────────────────────────────────────────────────
        self._mismatch_tbl.setRowCount(0)
        self._mismatch_count_lbl.setText("")




        # ── Status bar ─────────────────────────────────────────────────────────
        self._set_status(
            "Cleared — load chip output and golden reference to begin.",
            self.STATUS_INFO,
        )

    # ── Drag & drop handlers ──────────────────────────────────────────────────

    def _drop_chip(self, path: str):
        """Dropped file on Chip DUT panel — load as chip output."""
        ext = path.lower().rsplit(".", 1)[-1]
        if ext in ("txt", "hex"):
            try:
                bits = self._parse_output_file(path)
                self._chip = bits
                self._clear_video_state()
                self._disp_chip.set_image(bits * 255, info=os.path.basename(path))
                self._set_status(f"Chip output loaded: {os.path.basename(path)}", self.STATUS_OK)
            except Exception as exc:
                self._set_status(f"Drop load error: {exc}", self.STATUS_ERR)
        else:
            self._set_status("Drop a .txt or .hex file on the Chip DUT panel.", self.STATUS_ERR)

    def _drop_golden(self, path: str):
        """Dropped file on Golden Model panel — load as golden reference."""
        ext = path.lower().rsplit(".", 1)[-1]
        if ext in ("txt", "hex"):
            try:
                bits = self._parse_output_file(path)
                self._golden = bits
                self._clear_video_state()
                self._disp_golden.set_image(bits * 255, info=os.path.basename(path))
                self._set_status(f"Golden reference loaded: {os.path.basename(path)}", self.STATUS_OK)
            except Exception as exc:
                self._set_status(f"Drop load error: {exc}", self.STATUS_ERR)
        else:
            self._set_status("Drop a .txt or .hex file on the Golden Model panel.", self.STATUS_ERR)

    def _drop_original(self, path: str):
        """Dropped file on Original Input panel — load as source image."""
        ext = path.lower().rsplit(".", 1)[-1]
        if ext in ("png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp"):
            try:
                import cv2 as _cv2
                raw = np.fromfile(path, dtype=np.uint8)
                img = _cv2.imdecode(raw, _cv2.IMREAD_GRAYSCALE)
                if img is None:
                    raise ValueError("Could not decode image")
                img = _cv2.resize(img, (256, 256), interpolation=_cv2.INTER_AREA)
                self._image = img.astype(np.uint8)
                self._video_frames = []
                self._disp_original.set_image(self._image, info=os.path.basename(path))
                self._set_status(f"Original input loaded: {os.path.basename(path)}", self.STATUS_OK)
            except Exception:
                try:
                    from PIL import Image as _Pil
                    img = _Pil.open(path).convert("L").resize((256, 256))
                    self._image = np.array(img, dtype=np.uint8)
                    self._video_frames = []
                    self._disp_original.set_image(self._image, info=os.path.basename(path))
                    self._set_status(f"Original input loaded: {os.path.basename(path)}", self.STATUS_OK)
                except Exception as exc:
                    self._set_status(f"Drop load error: {exc}", self.STATUS_ERR)
        else:
            self._set_status("Drop an image file (PNG/JPG/BMP) on the Original Input panel.", self.STATUS_ERR)

    def _set_status(self, msg: str, colour: str = "#8A8A8E"):
        self.sig_status.emit(msg, colour)
