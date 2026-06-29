"""
Generator Mode — Pre-Simulation Panel  |  TAU EE ASIC Verification Suite

Layout:
  ┌───────────────┬──────────────────────┬──────────────────────────────┐
  │  INPUT SOURCE  │  KERNEL CONFIG       │  LIVE PREVIEW                │
  │  ──────────── │  ─────────────────── │  ──────────────────────────  │
  │  [Load Image] │  3×3 weight grid     │  Input Image  │  Golden Out  │
  │  [Load Video] │  Bias / Threshold    │                              │
  │  [Rnd Preset] │  [Run Golden Model]  │                              │
  │  [Generate]   │                      │                              │
  ├───────────────┴──────────────────────┴──────────────────────────────┤
  │                  [Export Stimulus + Scoreboard  (.hex / .txt)]       │
  └─────────────────────────────────────────────────────────────────────┘

Signal contracts (consumed by MainWindow status bar):
  sig_status(msg: str, color: str)
  sig_kernel(kernel_str: str)          → "Kernel: X  |  Bias: Y  |  Thr: Z"
  sig_frame(current: int, total: int)
"""

from __future__ import annotations
import os
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QGroupBox, QPushButton, QLabel, QSpinBox,
    QComboBox, QFileDialog, QProgressBar, QSizePolicy,
    QFrame, QSlider, QMessageBox, QApplication, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QSize, QTimer, QSettings
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from core.app_logger import AppLogger

from ui.image_display import ImageDisplay
from ui.loading_overlay import LoadingOverlay
from core.golden_model import run_golden_model_fast
from core.hex_exporter import export_stimulus, export_scoreboard, create_run_folder

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

try:
    from PIL import Image as PilImage
    _HAS_PIL = True
    # Pillow 10+ moved resampling filters to Image.Resampling.*
    _PIL_BILINEAR = getattr(getattr(PilImage, "Resampling", PilImage), "BILINEAR", 2)
except ImportError:
    _HAS_PIL = False
    _PIL_BILINEAR = 2


IMG_SIZE = 256
_MAX_VIDEO_FRAMES = 2000    # absolute hard cap (safety ceiling)
_DEFAULT_MAX_FRAMES = 300   # default shown in the UI spinbox

# Kernel preset names list (used for status bar reporting)
_PRESET_NAMES = ["Edge H", "Edge V", "Blur", "Identity", "Sharpen"]


# ──────────────────────────────────────────────────────────────────────────────
# Background worker — runs golden model off the UI thread
# ──────────────────────────────────────────────────────────────────────────────

class GoldenWorker(QObject):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, image, weights, bias, threshold):
        super().__init__()
        self._image     = image
        self._weights   = weights
        self._bias      = bias
        self._threshold = threshold

    def run(self):
        try:
            result = run_golden_model_fast(
                self._image, self._weights, self._bias, self._threshold
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Background worker — runs golden model on ALL frames off the UI thread
# ──────────────────────────────────────────────────────────────────────────────

class BatchGoldenWorker(QObject):
    progress = pyqtSignal(int, int)   # (done, total)
    finished = pyqtSignal(list)        # list[np.ndarray 254×254]
    error    = pyqtSignal(str)

    def __init__(self, frames, weights, bias, threshold, per_frame_kernels=None):
        super().__init__()
        self._frames             = frames
        self._weights            = weights
        self._bias               = bias
        self._threshold          = threshold
        self._per_frame_kernels  = per_frame_kernels
        self._cancelled          = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        results = []
        total   = len(self._frames)
        try:
            for i, frame in enumerate(self._frames):
                if self._cancelled:
                    self.finished.emit([])   # empty = cancelled; lets thread quit
                    return
                if (self._per_frame_kernels is not None
                        and i < len(self._per_frame_kernels)):
                    k = self._per_frame_kernels[i]
                    w, b, t = k["weights"], k["bias"], k["threshold"]
                else:
                    w, b, t = self._weights, self._bias, self._threshold
                results.append(run_golden_model_fast(frame, w, b, t))
                self.progress.emit(i + 1, total)
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Background worker — exports stimulus + scoreboard files off the UI thread
# ──────────────────────────────────────────────────────────────────────────────

class ExportWorker(QObject):
    """Writes .hex + .txt + .png export files in a background thread."""
    progress = pyqtSignal(int, str)   # (frames_done, message)
    finished = pyqtSignal(str)        # run_dir path (empty string = cancelled)
    error    = pyqtSignal(str)

    def __init__(self, video_frames, golden_frames, weights,
                 bias, threshold, run_dir, stim_dir, score_dir,
                 vectors_dir, visual_input_dir, visual_golden_dir,
                 source_name="", preset_name="CUSTOM", per_frame_kernels=None):
        super().__init__()
        self._video_frames       = video_frames
        self._golden_frames      = golden_frames
        self._weights            = weights
        self._bias               = bias
        self._threshold          = threshold
        self._per_frame_kernels  = per_frame_kernels
        self._run_dir         = run_dir
        self._stim_dir        = stim_dir
        self._score_dir       = score_dir
        self._vectors_dir     = vectors_dir
        self._visual_input_dir  = visual_input_dir
        self._visual_golden_dir = visual_golden_dir
        self._preset_name     = preset_name
        self._source_name     = source_name
        self._cancelled       = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        from core.hex_exporter import (
            export_stimulus, export_scoreboard, export_full_vectors,
            export_run_info, export_run_params,
        )
        import os as _os
        from PIL import Image as _PilImage
        total = len(self._golden_frames)
        try:
            for i, (frame, golden) in enumerate(
                zip(self._video_frames, self._golden_frames)
            ):
                if self._cancelled:
                    self.finished.emit("")
                    return
                stim_path  = _os.path.join(self._stim_dir,   f"input_{i}.hex")
                score_path = _os.path.join(self._score_dir,  f"expected_{i}.txt")
                vec_path   = _os.path.join(self._vectors_dir, f"full_vectors_{i}.txt")
                if (self._per_frame_kernels is not None
                        and i < len(self._per_frame_kernels)):
                    _k = self._per_frame_kernels[i]
                    _w, _b, _t = _k["weights"], _k["bias"], _k["threshold"]
                else:
                    _w, _b, _t = self._weights, self._bias, self._threshold
                export_stimulus(frame, _w, _b, _t, stim_path)
                export_scoreboard(golden, score_path)
                export_full_vectors(frame, _w, _b, _t, vec_path)
                # Save visual PNGs (inputs and golden outputs in separate dirs)
                _PilImage.fromarray(frame).save(
                    _os.path.join(self._visual_input_dir, f"frame_{i + 1:03d}.png")
                )
                _PilImage.fromarray((golden * 255).astype(np.uint8)).save(
                    _os.path.join(self._visual_golden_dir, f"frame_{i + 1:03d}.png")
                )
                self.progress.emit(i + 1, f"Writing frame {i + 1} / {total}")
            # Write run summary + machine-readable params sidecar
            active = int(sum(g.sum() for g in self._golden_frames))
            export_run_info(
                self._run_dir, self._weights, self._bias, self._threshold,
                source_name=self._source_name,
                n_frames=total,
                active_pixels=active,
            )
            export_run_params(
                self._run_dir, self._weights, self._bias, self._threshold,
                preset_name=self._preset_name,
            )
            self.finished.emit(self._run_dir)
        except Exception as exc:
            self.error.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Background worker — decodes video frames off the UI thread
# ──────────────────────────────────────────────────────────────────────────────

class VideoLoaderWorker(QObject):
    """Decodes a video file into a list of 256×256 uint8 numpy arrays."""
    progress = pyqtSignal(int, str)        # (frames_done, hint_text)
    finished = pyqtSignal(list)            # list[np.ndarray] — empty = cancelled
    error    = pyqtSignal(str)

    def __init__(self, path: str, img_size: int, max_frames: int):
        super().__init__()
        self._path       = path
        self._img_size   = img_size
        self._max_frames = max_frames
        self._cancelled  = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        import cv2 as _cv2
        import numpy as _np
        try:
            cap = _cv2.VideoCapture(self._path)
            if not cap.isOpened():
                self.error.emit(f"Cannot open video: {self._path}")
                return
            raw_count    = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
            total_frames = raw_count if raw_count > 0 else 0
            frames: list = []
            truncated = False
            while True:
                if self._cancelled:
                    cap.release()
                    self.finished.emit([])
                    return
                ok, frame = cap.read()
                if not ok:
                    break
                gray = _cv2.cvtColor(frame, _cv2.COLOR_BGR2GRAY)
                gray = _cv2.resize(gray, (self._img_size, self._img_size),
                                   interpolation=_cv2.INTER_AREA)
                frames.append(gray.astype(_np.uint8))
                idx = len(frames)
                if idx >= self._max_frames:
                    truncated = True
                    break
                if idx % 30 == 0:
                    hint = (f"Frame {idx}" +
                            (f" / {total_frames}" if total_frames > 0 else ""))
                    self.progress.emit(idx, hint)
            cap.release()
            if truncated:
                self.progress.emit(len(frames),
                                   f"Truncated to {self._max_frames} frames (memory limit)")
            self.finished.emit(frames)
        except Exception as exc:
            self.error.emit(str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Main widget
# ──────────────────────────────────────────────────────────────────────────────

class GeneratorWidget(QWidget):

    # Status bar signals — consumed by MainWindow
    sig_status     = pyqtSignal(str, str)   # (message, css-color)
    sig_kernel     = pyqtSignal(str)        # full kernel-info string
    sig_kernel_cfg = pyqtSignal(dict)       # full kernel config dict → AnalystWidget
    sig_frame      = pyqtSignal(int, int)   # (current_frame_1based, total_frames)
    sig_video_step = pyqtSignal(int)        # 0-based frame index → AnalystWidget.go_to_frame

    # Internal colour codes
    _C_OK   = "#00e880"
    _C_ERR  = "#f04040"
    _C_INFO = "#d8a800"
    _C_WARN = "#ff9f0a"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image: np.ndarray | None = None        # current 256×256 uint8
        self._golden: np.ndarray | None = None       # 254×254 binary output
        self._video_frames: list[np.ndarray] = []
        self._video_idx: int = 0
        self._active_preset: str = "CUSTOM"
        self._worker_thread: QThread | None = None
        # Batch video processing state
        self._golden_frames: list[np.ndarray] = []
        self._is_playing:    bool = False
        self._play_timer:    QTimer | None = None
        self._batch_worker:       BatchGoldenWorker | None = None
        self._batch_thread:       QThread | None = None
        self._video_load_worker:  object | None = None
        self._video_load_thread:  QThread | None = None
        self._cancel_loading: bool = False
        self._last_output_dir: str = ""
        # Per-frame kernel randomisation (None = single fixed kernel for all frames)
        self._per_frame_kernels: list[dict] | None = None
        self._build_ui()
        # Full-cover loading overlay — created AFTER _build_ui
        self._overlay = LoadingOverlay(self)
        self._overlay.sig_cancel.connect(self._on_cancel_loading)
        # Restore last session settings
        self._load_settings()
        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self._load_image)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._run_golden)
        QShortcut(QKeySequence("Ctrl+E"), self).activated.connect(self._export)
        QShortcut(QKeySequence("Space"),  self).activated.connect(
            lambda: self._toggle_play() if self._video_frames else None
        )

    # ══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # Minimum width: Input(200) + Kernel(260) + Preview(440) + margins(28) + spacing(20) = 948
        # Keep below 960 so content fits at 1366px screen (1366-260 sidebar-40 scroll = ~1066px)
        self.setMinimumWidth(960)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 8, 14, 8)
        root.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QFrame()
        hdr.setObjectName("header_bar")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(0, 0, 0, 0)
        t1 = QLabel("GENERATOR")
        t1.setObjectName("mode_title")
        t2 = QLabel("PRE-SIMULATION / STIMULUS GENERATION")
        t2.setObjectName("mode_subtitle")
        hdr_lay.addWidget(t1)
        hdr_lay.addSpacing(12)
        hdr_lay.addWidget(t2, alignment=Qt.AlignmentFlag.AlignBottom)
        hdr_lay.addStretch()
        root.addWidget(hdr)

        # ── Three-column main area ─────────────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(10)
        cols.addWidget(self._build_input_panel(),   stretch=2)
        cols.addWidget(self._build_kernel_panel(),  stretch=3)
        cols.addWidget(self._build_preview_panel(), stretch=6)
        root.addLayout(cols, stretch=1)

        # Orphan widgets used only by _emit_status (not added to layout —
        # status goes to the main-window status bar via sig_status)
        self._status_lbl = QLabel()
        self._progress   = QProgressBar()
        self._progress.setRange(0, 0)

    # ── Input panel ───────────────────────────────────────────────────────────

    def _build_input_panel(self) -> QGroupBox:
        grp = QGroupBox("INPUT SOURCE")
        grp.setMinimumWidth(200)
        root_lay = QVBoxLayout(grp)
        root_lay.setSpacing(6)
        root_lay.setContentsMargins(10, 14, 10, 8)

        # ── File load buttons ─────────────────────────────────────────────────
        btn_img = QPushButton("Load Image")
        btn_img.setObjectName("btn_primary")
        btn_img.setFixedHeight(36)
        btn_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_img.setToolTip("Import JPG / PNG / BMP / TIF / WEBP / GIF — resized to 256×256 grayscale")
        btn_img.clicked.connect(self._load_image)

        btn_vid = QPushButton("Load Video")
        btn_vid.setObjectName("btn_primary")
        btn_vid.setFixedHeight(36)
        btn_vid.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_vid.setToolTip("Import MP4 / AVI — each frame is 256×256 grayscale")
        btn_vid.clicked.connect(self._load_video)
        if not _HAS_CV2:
            btn_vid.setEnabled(False)
            btn_vid.setToolTip("OpenCV not installed — pip install opencv-python")

        root_lay.addWidget(btn_img)
        root_lay.addWidget(btn_vid)

        # ── Max frames row ─────────────────────────────────────────────────────
        max_frames_row = QHBoxLayout()
        max_frames_row.setSpacing(6)
        max_frames_lbl = QLabel("Max frames")
        max_frames_lbl.setStyleSheet(
            "color: #00ADEF; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;"
        )
        self._max_frames_sb = QSpinBox()
        self._max_frames_sb.setRange(1, _MAX_VIDEO_FRAMES)
        self._max_frames_sb.setValue(_DEFAULT_MAX_FRAMES)
        self._max_frames_sb.setFixedHeight(30)
        self._max_frames_sb.setFixedWidth(80)
        self._max_frames_sb.setToolTip(
            f"Maximum number of frames to load from a video file.\n"
            f"Default: {_DEFAULT_MAX_FRAMES}  |  Hard cap: {_MAX_VIDEO_FRAMES}"
        )
        max_frames_row.addWidget(max_frames_lbl)
        max_frames_row.addStretch()
        max_frames_row.addWidget(self._max_frames_sb)
        root_lay.addLayout(max_frames_row)

        # ── Random generator section ───────────────────────────────────────────
        sep1 = QFrame(); sep1.setObjectName("nav_separator")
        sep1.setFixedHeight(1)
        root_lay.addWidget(sep1)

        lbl_rnd = QLabel("RANDOM STIMULUS")
        lbl_rnd.setObjectName("lbl_section")
        root_lay.addWidget(lbl_rnd)

        self._rnd_mode = QComboBox()
        self._rnd_mode.setFixedHeight(32)
        self._rnd_mode.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._rnd_mode.addItems([
            "Pure Noise",
            "Checkerboard",
            "Horizontal Gradient",
            "Vertical Gradient",
            "Salt & Pepper",
            "Concentric Rings",
            "Random Blobs",
        ])
        root_lay.addWidget(self._rnd_mode)

        # Count row: [Count  frames label in cyan] [stretch] [spinbox right-aligned]
        count_row = QHBoxLayout()
        count_row.setSpacing(6)
        count_lbl = QLabel("Count  frames")
        # Use inline style: cyan + bold but without the 2.5 px letter-spacing
        # that lbl_section applies — that spacing clips the text in narrow panels.
        count_lbl.setStyleSheet(
            "color: #00ADEF; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;"
        )
        self._rnd_count = QSpinBox()
        self._rnd_count.setRange(1, 500)
        self._rnd_count.setValue(1)
        self._rnd_count.setFixedHeight(30)
        self._rnd_count.setFixedWidth(80)
        self._rnd_count.setToolTip(
            "1 = generate a single image.\n"
            "> 1 = generate N random frames and treat them as a video sequence."
        )
        count_row.addWidget(count_lbl)
        count_row.addStretch()
        count_row.addWidget(self._rnd_count)
        root_lay.addLayout(count_row)

        # ── Randomize kernel options ────────────────────────────────────────
        _CB_STYLE = (
            "QCheckBox {{ color: {fg}; font-size: 11px; }}"
            "QCheckBox:checked {{ color: #00ADEF; }}"
            "QCheckBox::indicator {{ width: 13px; height: 13px; }}"
            "QCheckBox::indicator:checked {{ background: #00ADEF; border-radius: 3px; }}"
            "QCheckBox::indicator:unchecked {{ border: 1px solid #3A3A3C; border-radius: 3px; }}"
        )

        # Master toggle
        self._rnd_rand_kernel = QCheckBox("Randomize kernel per frame")
        self._rnd_rand_kernel.setStyleSheet(_CB_STYLE.format(fg="#8A8A8E"))
        self._rnd_rand_kernel.setToolTip(
            "Enable per-frame kernel randomisation.\n"
            "Use the sub-options below to choose what gets randomised."
        )
        root_lay.addWidget(self._rnd_rand_kernel)

        # Sub-option row (indented)
        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(16, 0, 0, 0)
        sub_row.setSpacing(10)

        self._rnd_rw = QCheckBox("Weights")
        self._rnd_rb = QCheckBox("Bias")
        self._rnd_rt = QCheckBox("Threshold")
        for cb in (self._rnd_rw, self._rnd_rb, self._rnd_rt):
            cb.setChecked(True)
            cb.setStyleSheet(_CB_STYLE.format(fg="#6E6E73"))
            sub_row.addWidget(cb)
        sub_row.addStretch()
        root_lay.addLayout(sub_row)

        # Enable/disable sub-options with master toggle
        def _sync_sub(state):
            on = bool(state)
            for cb in (self._rnd_rw, self._rnd_rb, self._rnd_rt):
                cb.setEnabled(on)
        self._rnd_rand_kernel.stateChanged.connect(_sync_sub)
        _sync_sub(self._rnd_rand_kernel.isChecked())

        btn_rnd = QPushButton("Generate Random")
        btn_rnd.setObjectName("btn_success")
        btn_rnd.setFixedHeight(34)
        btn_rnd.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_rnd.clicked.connect(self._generate_random)
        root_lay.addWidget(btn_rnd)

        # ── Video frame navigation ─────────────────────────────────────────────
        sep2 = QFrame(); sep2.setObjectName("nav_separator")
        sep2.setFixedHeight(1)
        root_lay.addWidget(sep2)

        self._nav_group = QFrame()
        self._nav_group.setObjectName("img_frame")
        nav_lay = QVBoxLayout(self._nav_group)
        nav_lay.setSpacing(6)
        nav_lay.setContentsMargins(10, 8, 10, 8)
        nav_lay.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)

        nav_title = QLabel("FRAME NAVIGATION")
        nav_title.setObjectName("lbl_section")
        nav_lay.addWidget(nav_title)

        self._frame_lbl = QLabel("Frame  —  /  —")
        self._frame_lbl.setObjectName("lbl_stat_value")
        self._frame_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_lay.addWidget(self._frame_lbl)

        self._frame_slider = QSlider(Qt.Orientation.Horizontal)
        self._frame_slider.setMinimum(0)
        self._frame_slider.setMaximum(0)
        self._frame_slider.valueChanged.connect(self._slider_changed)
        nav_lay.addWidget(self._frame_slider)

        nav_btns = QHBoxLayout()
        nav_btns.setSpacing(5)
        self._btn_prev = QPushButton("Prev")
        self._btn_prev.setFixedHeight(30)
        self._btn_prev.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_prev.clicked.connect(self._prev_frame)
        self._btn_next = QPushButton("Next")
        self._btn_next.setFixedHeight(30)
        self._btn_next.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_next.clicked.connect(self._next_frame)
        nav_btns.addWidget(self._btn_prev)
        nav_btns.addWidget(self._btn_next)
        nav_lay.addLayout(nav_btns)

        # Play / Pause + FPS — single row, no floating label (suffix used instead)
        play_fps_row = QHBoxLayout()
        play_fps_row.setSpacing(5)
        self._btn_play = QPushButton("Play")
        self._btn_play.setFixedHeight(30)
        self._btn_play.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_play.setToolTip(
            "Plays all frames with golden output.\n"
            "Each frame is processed independently — line buffer resets between frames."
        )
        self._btn_play.clicked.connect(self._toggle_playback)
        self._btn_play.setEnabled(False)

        self._fps_sb = QSpinBox()
        self._fps_sb.setRange(1, 60)
        self._fps_sb.setValue(10)
        self._fps_sb.setSuffix("  fps")   # unit inside the box — no floating label
        self._fps_sb.setFixedWidth(78)
        self._fps_sb.setFixedHeight(30)
        self._fps_sb.setEnabled(False)
        self._fps_sb.setToolTip("Playback frame rate")

        play_fps_row.addWidget(self._btn_play, stretch=1)
        play_fps_row.addWidget(self._fps_sb)
        nav_lay.addLayout(play_fps_row)

        self._nav_group.setVisible(False)   # hidden until a video is loaded
        root_lay.addWidget(self._nav_group)
        root_lay.addStretch()

        return grp

    # ── Kernel panel ──────────────────────────────────────────────────────────

    def _build_kernel_panel(self) -> QGroupBox:
        grp = QGroupBox("KERNEL CONFIGURATION")
        grp.setMinimumWidth(260)
        lay = QVBoxLayout(grp)
        lay.setSpacing(7)
        lay.setContentsMargins(10, 14, 10, 8)

        # ── Weight label ──────────────────────────────────────────────────────
        lbl_w = QLabel("WEIGHTS  (uint8 : 0 – 255)")
        lbl_w.setObjectName("lbl_section")
        lay.addWidget(lbl_w)

        # ── 3×3 grid ──────────────────────────────────────────────────────────
        grid_frame = QFrame()
        grid_lay = QGridLayout(grid_frame)
        grid_lay.setSpacing(4)
        grid_lay.setContentsMargins(0, 0, 0, 0)
        grid_lay.setColumnStretch(0, 1)
        grid_lay.setColumnStretch(1, 1)
        grid_lay.setColumnStretch(2, 1)

        self._weight_boxes: list[list[QSpinBox]] = []
        for r in range(3):
            row_boxes: list[QSpinBox] = []
            for c in range(3):
                sb = QSpinBox()
                sb.setObjectName("weight_cell")
                sb.setRange(0, 255)
                sb.setValue(0)
                sb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                sb.setFixedHeight(34)
                sb.setMinimumWidth(50)
                sb.valueChanged.connect(self._on_weight_changed)
                grid_lay.addWidget(sb, r, c)
                row_boxes.append(sb)
            self._weight_boxes.append(row_boxes)

        lay.addWidget(grid_frame)

        # ── Preset buttons — two QHBoxLayout rows; each button expands equally ──
        # Row A: [Edge H] [Edge V] [Blur]
        # Row B: [Identity] [Sharpen]  ← wider so text is never clipped
        def _make_preset_btn(name: str) -> QPushButton:
            b = QPushButton(name)
            b.setObjectName("btn_warn")
            b.setFixedHeight(30)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _, n=name: self._apply_preset(n))
            return b

        row_a = QHBoxLayout()
        row_a.setSpacing(4)
        for name in ("Edge H", "Edge V", "Blur"):
            row_a.addWidget(_make_preset_btn(name))

        row_b = QHBoxLayout()
        row_b.setSpacing(4)
        for name in ("Identity", "Sharpen"):
            row_b.addWidget(_make_preset_btn(name))

        lay.addLayout(row_a)
        lay.addLayout(row_b)

        # ── Custom preset row ─────────────────────────────────────────────────
        custom_row = QHBoxLayout()
        custom_row.setSpacing(4)
        self._custom_preset_combo = QComboBox()
        self._custom_preset_combo.setFixedHeight(28)
        self._custom_preset_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._custom_preset_combo.setToolTip("Saved custom presets")
        self._custom_preset_combo.activated.connect(self._load_custom_preset)
        save_preset_btn = QPushButton("Save")
        save_preset_btn.setObjectName("btn_success")
        save_preset_btn.setFixedHeight(28)
        save_preset_btn.setFixedWidth(64)
        save_preset_btn.setToolTip("Save current kernel as a named preset")
        save_preset_btn.clicked.connect(self._save_custom_preset)
        del_preset_btn = QPushButton("Del")
        del_preset_btn.setObjectName("btn_warn")
        del_preset_btn.setFixedSize(36, 28)
        del_preset_btn.setToolTip("Delete selected custom preset")
        del_preset_btn.clicked.connect(self._delete_custom_preset)
        custom_row.addWidget(self._custom_preset_combo, stretch=1)
        custom_row.addWidget(save_preset_btn)
        custom_row.addWidget(del_preset_btn)
        lay.addLayout(custom_row)
        self._refresh_custom_preset_combo()

        sep1 = QFrame(); sep1.setObjectName("nav_separator")
        sep1.setFixedHeight(1)
        lay.addWidget(sep1)

        # ── Bias ──────────────────────────────────────────────────────────────
        bias_row = QHBoxLayout()
        bias_row.setSpacing(6)
        bias_row.setContentsMargins(0, 0, 0, 0)

        bias_lbl = QLabel("BIAS")
        bias_lbl.setObjectName("lbl_section")
        self._bias_sb = QSpinBox()
        self._bias_sb.setRange(0, 255)
        self._bias_sb.setValue(0)
        self._bias_sb.setFixedHeight(32)
        self._bias_sb.setMinimumWidth(70)
        self._bias_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._bias_sb.valueChanged.connect(self._emit_kernel_info)
        bias_row.addWidget(bias_lbl)
        bias_row.addWidget(self._bias_sb)
        lay.addLayout(bias_row)

        # ── Threshold — label and spinbox on one row, hex on same line ────────
        thr_lbl = QLabel("THRESHOLD  (20-bit)")
        thr_lbl.setObjectName("lbl_section")
        lay.addWidget(thr_lbl)

        thr_row = QHBoxLayout()
        thr_row.setSpacing(6)
        self._thr_sb = QSpinBox()
        self._thr_sb.setRange(0, 1_048_575)
        self._thr_sb.setValue(2000)
        self._thr_sb.setFixedHeight(32)
        self._thr_sb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._thr_sb.valueChanged.connect(self._emit_kernel_info)

        self._thr_hex_lbl = QLabel("0x000007D0")
        self._thr_hex_lbl.setObjectName("img_info")
        self._thr_hex_lbl.setMinimumWidth(74)

        self._thr_sb.valueChanged.connect(
            lambda v: self._thr_hex_lbl.setText(f"0x{v:08X}")
        )
        thr_row.addWidget(self._thr_sb)
        thr_row.addWidget(self._thr_hex_lbl)
        lay.addLayout(thr_row)

        sep2 = QFrame(); sep2.setObjectName("nav_separator")
        sep2.setFixedHeight(1)
        lay.addWidget(sep2)

        # ── Run button ────────────────────────────────────────────────────────
        self._run_btn = QPushButton("  Run Golden Model")
        self._run_btn.setObjectName("btn_primary")
        self._run_btn.setFixedHeight(36)
        self._run_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._run_btn.clicked.connect(self._run_golden)
        lay.addWidget(self._run_btn)

        # ── Process All Frames button (video only) ────────────────────────────
        self._batch_btn = QPushButton("⚙  Process All Frames")
        self._batch_btn.setObjectName("btn_success")
        self._batch_btn.setFixedHeight(36)
        self._batch_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._batch_btn.setEnabled(False)
        self._batch_btn.setToolTip("Run golden model on every video frame and store results")
        self._batch_btn.clicked.connect(self._process_all_frames)
        lay.addWidget(self._batch_btn)

        sep3 = QFrame()
        sep3.setObjectName("nav_separator")
        sep3.setFixedHeight(1)
        lay.addWidget(sep3)

        self._export_btn = QPushButton(
            "  Export Stimulus + Scoreboard   (.hex / .txt)"
        )
        self._export_btn.setObjectName("btn_export")
        self._export_btn.setMinimumHeight(36)
        self._export_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._export_btn.setToolTip(
            "Writes to a timestamped run folder:\n"
            "  stimulus/input_0.hex    ← $readmemh format\n"
            "  golden/expected_0.txt"
        )
        self._export_btn.clicked.connect(self._export)
        lay.addWidget(self._export_btn)

        self._export_info = QLabel("")
        self._export_info.setObjectName("lbl_stat_value")
        lay.addWidget(self._export_info)

        lay.addStretch()

        # Seed the Identity preset on startup
        self._apply_preset("Identity")

        return grp

    # ── Preview panel ─────────────────────────────────────────────────────────

    def _build_preview_panel(self) -> QGroupBox:
        grp = QGroupBox("LIVE PREVIEW  —  Valid region: 254×254 (rows 2-255, cols 2-255)")
        grp.setMinimumWidth(440)
        lay = QHBoxLayout(grp)
        lay.setSpacing(10)
        lay.setContentsMargins(10, 14, 10, 8)

        self._disp_input  = ImageDisplay("INPUT IMAGE",   "LOAD IMAGE  or  DRAG & DROP")
        self._disp_output = ImageDisplay("GOLDEN OUTPUT", "RUN MODEL")

        # Drag & drop: image files on input panel → load as image
        self._disp_input.sig_file_dropped.connect(self._load_image_from_path)

        lay.addWidget(self._disp_input,  stretch=1)
        lay.addWidget(self._disp_output, stretch=1)

        return grp

    # ══════════════════════════════════════════════════════════════════════════
    # Image loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_image_from_path(self, path: str):
        """Load an image directly from a file path (used by drag & drop)."""
        try:
            arr = self._imread_gray(path)
            self._set_image(arr)
            self._clear_video_state()
            msg = f"Loaded: {os.path.basename(path)}  (256×256 grayscale)"
            self._emit_status(msg, self._C_OK)
            AppLogger.instance().ok(f"Image loaded: {os.path.basename(path)}")
        except Exception as exc:
            self._emit_status(f"Error loading image: {exc}", self._C_ERR)
            AppLogger.instance().error(f"Image load failed: {exc}")

    def _load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif *.ppm *.pgm);;All Files (*)"
        )
        if not path:
            return
        try:
            arr = self._imread_gray(path)
            self._last_image_path = path
            self._set_image(arr)          # clears golden output + stops playback
            self._clear_video_state()     # resets ALL video controls to idle state
            name = os.path.basename(path)
            self._emit_status(f"Loaded: {name}  (256×256 grayscale)", self._C_OK)
        except Exception as exc:
            QMessageBox.critical(self, "Image Load Error", str(exc))
            self._emit_status(f"Error loading image: {exc}", self._C_ERR)

    def _load_video(self):
        if not _HAS_CV2:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video", "",
            "Videos (*.mp4 *.avi *.mov *.mkv);;All Files (*)"
        )
        if not path:
            return

        # Cancel any in-progress load before starting a new one
        if self._video_load_worker is not None and hasattr(self._video_load_worker, "cancel"):
            self._video_load_worker.cancel()
        try:
            self._overlay.sig_cancel.disconnect()
        except Exception:
            pass
        # Always keep the generic cancel handler connected
        self._overlay.sig_cancel.connect(self._on_cancel_loading)

        self._overlay.show_loading(
            "Loading Video…",
            f"Decoding {os.path.basename(path)}",
            cancellable=True,
        )

        self._video_path = path   # store for status message in callback
        max_frames = min(self._max_frames_sb.value(), _MAX_VIDEO_FRAMES)
        worker = VideoLoaderWorker(path, IMG_SIZE, max_frames)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(lambda _n, hint: self._overlay.set_message(hint))
        worker.finished.connect(lambda frames, t=thread: self._on_video_loaded(frames, t))
        worker.error.connect(lambda msg, t=thread: self._on_video_error(msg, t))
        self._overlay.sig_cancel.connect(worker.cancel)
        # keep references alive while thread runs
        self._video_load_thread = thread
        self._video_load_worker = worker
        thread.start()

    def _on_video_loaded(self, frames: list, thread: QThread) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(self._video_load_worker.cancel)
        except Exception:
            pass
        self._overlay.hide_loading()

        if not frames:
            # cancelled or empty
            self._emit_status("Video load cancelled.", self._C_INFO)
            return

        user_limit = self._max_frames_sb.value()
        truncated = len(frames) >= user_limit
        self._video_frames  = frames
        self._golden_frames = []
        self._nav_group.setVisible(True)
        self._frame_slider.setMaximum(len(frames) - 1)
        self._frame_slider.setValue(0)
        self._set_video_frame(0)
        self._batch_btn.setEnabled(True)
        self._btn_play.setEnabled(False)
        self._fps_sb.setEnabled(False)

        name = os.path.basename(getattr(self, "_video_path", ""))
        if truncated:
            msg = (f"Video loaded: {name}  —  {len(frames)} frames "
                   f"(truncated to {user_limit} — change 'Max frames' to load more)")
            self._emit_status(msg, self._C_WARN)
            AppLogger.instance().warn(
                f"Video truncated: only first {user_limit} frames loaded."
            )
        else:
            self._emit_status(
                f"Video loaded: {name}  —  {len(frames)} frames", self._C_OK
            )

    def _on_video_error(self, msg: str, thread: QThread) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(self._video_load_worker.cancel)
        except Exception:
            pass
        self._overlay.hide_loading()
        self._emit_status(f"Video error: {msg}", self._C_ERR)
        AppLogger.instance().error(f"Video load error: {msg}")

    # ══════════════════════════════════════════════════════════════════════════
    # Random generation
    # ══════════════════════════════════════════════════════════════════════════

    def _generate_random(self):
        mode      = self._rnd_mode.currentText()
        count     = self._rnd_count.value()
        rand_kern = self._rnd_rand_kernel.isChecked()

        if count == 1:
            # ── Single-frame path ─────────────────────────────────
            arr = self._make_random_pattern(mode)
            self._set_image(arr)
            self._clear_video_state()
            if rand_kern:
                self._apply_random_kernel_to_ui()
                self._emit_status(
                    f"Random stimulus + kernel: {mode}  (256×256)", self._C_OK)
            else:
                self._emit_status(
                    f"Random stimulus: {mode}  (256×256)", self._C_OK)
        else:
            # ── Multi-frame path ────────────────────────────────
            self._clear_video_state()
            frames = [self._make_random_pattern(mode) for _ in range(count)]
            self._video_frames  = frames
            self._golden_frames = []

            # Build per-frame kernels if requested
            if rand_kern:
                rand_w = self._rnd_rw.isChecked()
                rand_b = self._rnd_rb.isChecked()
                rand_t = self._rnd_rt.isChecked()
                base_w = self._get_weights()
                base_b = self._bias_sb.value()
                base_t = self._thr_sb.value()
                self._per_frame_kernels = [
                    self._make_random_kernel(
                        rand_w=rand_w, rand_b=rand_b, rand_t=rand_t,
                        base_weights=base_w, base_bias=base_b, base_threshold=base_t,
                    )
                    for _ in range(count)
                ]
                # Show the first frame's kernel in the UI immediately
                self._apply_kernel_to_ui(self._per_frame_kernels[0])
            else:
                self._per_frame_kernels = None

            # Show the first frame immediately
            self._set_image(frames[0])
            # Enable navigation
            self._nav_group.setVisible(True)
            self._frame_slider.setMaximum(count - 1)
            self._frame_slider.setValue(0)
            self._set_video_frame(0)
            self._batch_btn.setEnabled(True)
            self._btn_play.setEnabled(False)
            self._fps_sb.setEnabled(False)
            kern_note = "  [random kernel/frame]" if rand_kern else ""
            AppLogger.instance().ok(
                f"Generated {count} random frames ({mode}){kern_note}."
            )
            self._emit_status(
                f"Generated {count} random frames ({mode}){kern_note}  —  "
                f"run 'Process All Frames' to compute golden outputs.",
                self._C_OK,
            )

    @staticmethod
    def _make_random_kernel(rand_w=True, rand_b=True, rand_t=True,
                            base_weights=None, base_bias=0, base_threshold=0) -> dict:
        """
        Generate a random kernel dict.
        Only the fields with rand_* = True are randomised; others keep the base value.
        """
        w = (np.random.randint(0, 256, 9, dtype=np.uint8).reshape(3, 3)
             if rand_w else (base_weights if base_weights is not None
                             else np.zeros((3, 3), dtype=np.uint8)))
        b = int(np.random.randint(0, 256))        if rand_b else base_bias
        t = int(np.random.randint(0, 0x100000))   if rand_t else base_threshold
        return {"weights": w, "bias": b, "threshold": t}

    def _apply_random_kernel_to_ui(self):
        """Randomise selected fields and push the values into the UI."""
        rand_w = self._rnd_rw.isChecked()
        rand_b = self._rnd_rb.isChecked()
        rand_t = self._rnd_rt.isChecked()
        k = self._make_random_kernel(
            rand_w=rand_w, rand_b=rand_b, rand_t=rand_t,
            base_weights=self._get_weights(),
            base_bias=self._bias_sb.value(),
            base_threshold=self._thr_sb.value(),
        )
        self._apply_kernel_to_ui(k)

    def _apply_kernel_to_ui(self, k: dict):
        """Push a kernel dict into the weight/bias/threshold UI controls."""
        w = k["weights"]
        for r in range(3):
            for c in range(3):
                self._weight_boxes[r][c].blockSignals(True)
                self._weight_boxes[r][c].setValue(int(w[r, c]))
                self._weight_boxes[r][c].blockSignals(False)
        self._bias_sb.blockSignals(True)
        self._bias_sb.setValue(k["bias"])
        self._bias_sb.blockSignals(False)
        self._thr_sb.blockSignals(True)
        self._thr_sb.setValue(k["threshold"])
        self._thr_sb.blockSignals(False)
        self._emit_kernel_info()

    @staticmethod
    def _make_random_pattern(mode: str) -> np.ndarray:
        N = IMG_SIZE
        x = np.linspace(0, 2 * np.pi, N)
        y = np.linspace(0, 2 * np.pi, N)
        X, Y = np.meshgrid(x, y)

        if mode == "Pure Noise":
            arr = np.random.randint(0, 256, (N, N), dtype=np.uint8)

        elif mode == "Checkerboard":
            block = 16
            arr = (np.indices((N, N)).sum(axis=0) // block % 2)
            arr = (arr * 220 + 10).astype(np.uint8)

        elif mode == "Horizontal Gradient":
            arr = np.tile(np.linspace(0, 255, N, dtype=np.uint8), (N, 1))

        elif mode == "Vertical Gradient":
            arr = np.tile(np.linspace(0, 255, N, dtype=np.uint8), (N, 1)).T.copy()

        elif mode == "Salt & Pepper":
            arr = np.full((N, N), 128, dtype=np.uint8)
            arr[np.random.rand(N, N) < 0.05] = 255
            arr[np.random.rand(N, N) < 0.05] = 0

        elif mode == "Concentric Rings":
            R = np.sqrt((X - np.pi) ** 2 + (Y - np.pi) ** 2)
            arr = ((np.sin(R * 3) + 1) * 127.5).astype(np.uint8)

        else:  # Random Blobs
            arr = np.zeros((N, N), dtype=np.uint8)
            for _ in range(np.random.randint(5, 20)):
                cx  = np.random.randint(20, N - 20)
                cy  = np.random.randint(20, N - 20)
                r   = np.random.randint(10, 60)
                val = np.random.randint(50, 255)
                yy, xx = np.ogrid[:N, :N]
                arr[(xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2] = val

        # Mild noise to stress-test boundary conditions
        noise = np.random.randint(-8, 9, (N, N), dtype=np.int16)
        return np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # ══════════════════════════════════════════════════════════════════════════
    # Golden model
    # ══════════════════════════════════════════════════════════════════════════

    def _run_golden(self):
        if self._image is None:
            self._emit_status("No image loaded — load or generate an image first.", self._C_ERR)
            return

        weights   = self._get_weights()
        bias      = self._bias_sb.value()
        threshold = self._thr_sb.value()

        self._run_btn.setEnabled(False)
        self._overlay.show_loading("Running Golden Model…", "Computing 256×256 MAC array")
        self._emit_status("Running golden model…", self._C_INFO)

        self._worker = GoldenWorker(self._image, weights, bias, threshold)
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_golden_done)
        self._worker.error.connect(self._on_golden_error)
        self._worker.finished.connect(self._worker_thread.quit)
        self._worker_thread.finished.connect(lambda: self._overlay.hide_loading())
        self._worker_thread.finished.connect(lambda: self._run_btn.setEnabled(True))
        self._worker_thread.start()

    def _on_golden_done(self, result: np.ndarray):
        self._golden = result
        ones_pct = 100.0 * result.mean()
        self._disp_output.set_image(
            result * 255,
            info=(
                f"254\u00d7254 valid region  |  "
                f"{result.sum():,} active px  ({ones_pct:.1f}%)"
            )
        )
        self._emit_status(
            f"Golden model complete — {result.sum():,} active pixels  ({ones_pct:.2f}%)",
            self._C_OK
        )

    def _on_golden_error(self, msg: str):
        self._overlay.hide_loading()
        self._emit_status(f"Golden model error: {msg}", self._C_ERR)

    # ══════════════════════════════════════════════════════════════════════════
    # Batch video processing
    # ══════════════════════════════════════════════════════════════════════════

    def _process_all_frames(self):
        """Launch BatchGoldenWorker to process every video frame in the background."""
        if not self._video_frames:
            self._emit_status("No video loaded.", self._C_ERR)
            return
        n_total = len(self._video_frames)
        self._cancel_loading = False
        self._batch_btn.setEnabled(False)
        self._run_btn.setEnabled(False)
        self._overlay.show_loading(
            "Processing Video…",
            f"0 / {n_total} frames done",
            determinate=True,
            max_val=n_total,
            cancellable=True,
        )
        self._emit_status("Processing all frames…", self._C_INFO)

        weights   = self._get_weights()
        bias      = self._bias_sb.value()
        threshold = self._thr_sb.value()

        self._batch_worker = BatchGoldenWorker(
            self._video_frames, weights, bias, threshold,
            per_frame_kernels=self._per_frame_kernels)
        self._batch_thread = QThread()
        self._batch_worker.moveToThread(self._batch_thread)
        self._batch_thread.started.connect(self._batch_worker.run)
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.finished.connect(self._on_batch_done)
        self._batch_worker.error.connect(self._on_batch_error)
        self._batch_worker.finished.connect(self._batch_thread.quit)
        self._batch_thread.finished.connect(lambda: self._run_btn.setEnabled(True))
        self._batch_thread.finished.connect(lambda: self._batch_btn.setEnabled(True))
        self._batch_thread.start()

    def _on_batch_progress(self, done: int, total: int):
        self._overlay.set_progress(done, f"{done} / {total} frames done")
        self._emit_status(f"Processing frame {done}/{total}…", self._C_INFO)

    def _on_batch_done(self, results: list):
        # NOTE: do NOT call thread.wait() here — it deadlocks.
        # The thread quits via finished.connect(batch_thread.quit) which is
        # also queued to the main thread; wait() would block before quit() runs.
        self._overlay.hide_loading()
        self._golden_frames = results
        self._btn_play.setEnabled(True)
        self._fps_sb.setEnabled(True)
        # Immediately show the result for the currently-visible frame
        self._golden = self._golden_frames[self._video_idx]
        self._update_output_display(self._video_idx)
        n = len(results)
        self._emit_status(f"Batch complete — {n} frames processed.", self._C_OK)

    def _on_batch_error(self, msg: str):
        self._overlay.hide_loading()
        self._emit_status(f"Batch processing error: {msg}", self._C_ERR)

    def _update_output_display(self, idx: int):
        """Render _golden_frames[idx] into the output display widget."""
        result = self._golden_frames[idx]
        ones_pct = 100.0 * result.mean()
        self._disp_output.set_image(
            result * 255,
            info=f"254×254  |  {result.sum():,} active px  ({ones_pct:.1f}%)"
        )

    # ── Playback ──────────────────────────────────────────────────────────────

    def _toggle_playback(self):
        if self._is_playing:
            # Pause
            if self._play_timer:
                self._play_timer.stop()
            self._is_playing = False
            self._btn_play.setText("Play")
        else:
            # Play
            if not self._golden_frames:
                return
            self._is_playing = True
            self._btn_play.setText("Pause")
            self._play_timer = QTimer(self)
            self._play_timer.timeout.connect(self._play_step)
            interval = max(1, int(1000 / self._fps_sb.value()))
            self._play_timer.start(interval)

    def _play_step(self):
        """Advance one frame; loop back to start when the last frame is reached."""
        next_idx = self._video_idx + 1
        if next_idx >= len(self._video_frames):
            next_idx = 0   # loop back to first frame
        self._set_video_frame(next_idx)

    # ══════════════════════════════════════════════════════════════════════════
    # Export
    # ══════════════════════════════════════════════════════════════════════════

    def _export(self):
        if self._image is None:
            self._emit_status("Nothing to export — load an image first.", self._C_ERR)
            return

        # ── Video batch path ─────────────────────────────────────────────────
        # Structure:  gui_run_TIMESTAMP/
        #               stimulus/            input_0.hex  input_1.hex  …
        #               golden/              expected_0.txt  expected_1.txt  …
        if self._golden_frames:
            base = QFileDialog.getExistingDirectory(
                self, "Select Output Folder", self._last_output_dir or ""
            )
            if not base:
                return
            self._last_output_dir = base
            self._save_settings()
            try:
                from datetime import datetime as _dt
                ts          = _dt.now().strftime("%Y%m%d_%H%M%S")
                run_dir           = os.path.join(base, f"gui_run_{ts}")
                stim_dir          = os.path.join(run_dir, "stimulus")
                score_dir         = os.path.join(run_dir, "golden")
                vectors_dir       = os.path.join(run_dir, "vectors")
                visual_input_dir  = os.path.join(run_dir, "visual_input")
                visual_golden_dir = os.path.join(run_dir, "visual_golden")
                os.makedirs(stim_dir,          exist_ok=True)
                os.makedirs(score_dir,         exist_ok=True)
                os.makedirs(vectors_dir,       exist_ok=True)
                os.makedirs(visual_input_dir,  exist_ok=True)
                os.makedirs(visual_golden_dir, exist_ok=True)

                weights   = self._get_weights()
                bias      = self._bias_sb.value()
                threshold = self._thr_sb.value()
                n_total   = len(self._golden_frames)

                self._cancel_loading = False
                self._overlay.show_loading(
                    "Exporting Files…",
                    f"Writing 0 / {n_total} frames",
                    determinate=True,
                    max_val=n_total,
                    cancellable=True,
                )

                # Disconnect any stale cancel handler from a previous operation
                try:
                    self._overlay.sig_cancel.disconnect()
                except Exception:
                    pass
                # Always keep the generic cancel handler connected
                self._overlay.sig_cancel.connect(self._on_cancel_loading)

                src_name = os.path.basename(getattr(self, "_video_path", ""))
                worker = ExportWorker(
                    self._video_frames, self._golden_frames, weights,
                    bias, threshold, run_dir, stim_dir, score_dir,
                    vectors_dir, visual_input_dir, visual_golden_dir,
                    source_name=src_name,
                    preset_name=self._active_preset,
                    per_frame_kernels=self._per_frame_kernels,
                )
                thread = QThread()
                worker.moveToThread(thread)
                thread.started.connect(worker.run)
                worker.progress.connect(
                    lambda done, msg: self._overlay.set_progress(done, msg)
                )
                worker.finished.connect(
                    lambda rd, t=thread, w=worker: self._on_export_done(rd, t, w)
                )
                worker.error.connect(
                    lambda msg, t=thread: self._on_export_error(msg, t)
                )
                self._overlay.sig_cancel.connect(worker.cancel)
                self._batch_thread  = thread
                self._batch_worker  = worker
                thread.start()
            except Exception as exc:
                self._overlay.hide_loading()
                self._emit_status(f"Export error: {exc}", self._C_ERR)
            return

        # ── Single-frame path (unchanged) ────────────────────────────────────
        if self._golden is None:
            reply = QMessageBox.question(
                self, "Run Golden Model?",
                "The golden model has not been run yet.\nRun it now before exporting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_golden()
            else:
                self._emit_status("Export cancelled — run golden model first.", self._C_INFO)
            return

        base = QFileDialog.getExistingDirectory(
            self, "Select Output Folder", self._last_output_dir or ""
        )
        if not base:
            return
        self._last_output_dir = base
        self._save_settings()

        try:
            from PIL import Image as _PilImage
            from core.hex_exporter import (
                export_run_info as _export_run_info,
                export_run_params as _export_run_params,
                export_full_vectors as _export_full_vectors,
            )
            run_dir, stim_path, score_path, vectors_dir, visual_input_dir, visual_golden_dir = create_run_folder(base)
            weights   = self._get_weights()
            bias      = self._bias_sb.value()
            threshold = self._thr_sb.value()

            n = export_stimulus(self._image, weights, bias, threshold, stim_path)
            export_scoreboard(self._golden, score_path)
            _export_full_vectors(
                self._image, weights, bias, threshold,
                os.path.join(vectors_dir, "full_vectors_0.txt"),
            )
            # Save visual PNGs (input and golden output in separate dirs)
            _PilImage.fromarray(self._image).save(
                os.path.join(visual_input_dir, "frame_001.png")
            )
            _PilImage.fromarray((self._golden * 255).astype(np.uint8)).save(
                os.path.join(visual_golden_dir, "frame_001.png")
            )
            # Write run summary + machine-readable params sidecar
            src = os.path.basename(getattr(self, "_last_image_path", ""))
            _export_run_info(
                run_dir, weights, bias, threshold,
                source_name=src,
                n_frames=1,
                active_pixels=int(self._golden.sum()),
            )
            _export_run_params(run_dir, weights, bias, threshold,
                               preset_name=self._active_preset)

            self._export_info.setText(f"\u2714  {n} bytes  \u2192  {os.path.basename(run_dir)}")
            self._emit_status(f"Exported to: {run_dir}", self._C_OK)
        except Exception as exc:
            self._emit_status(f"Export error: {exc}", self._C_ERR)

    # ══════════════════════════════════════════════════════════════════════════
    # Video navigation
    # ══════════════════════════════════════════════════════════════════════════

    def _prev_frame(self):
        if self._video_frames:
            self._set_video_frame(max(0, self._video_idx - 1))

    def _next_frame(self):
        if self._video_frames:
            self._set_video_frame(min(len(self._video_frames) - 1, self._video_idx + 1))

    def _slider_changed(self, val: int):
        if self._video_frames:
            self._set_video_frame(val)

    def _set_video_frame(self, idx: int):
        """
        Load frame `idx` from the video buffer.

        If batch golden results are available, restores the corresponding
        output display without clearing the results.  Otherwise clears the
        output to signal that the model needs to be (re-)run for this frame.
        """
        self._video_idx = idx
        frame = self._video_frames[idx]

        # Update kernel UI when per-frame randomisation is active
        if (self._per_frame_kernels is not None
                and idx < len(self._per_frame_kernels)):
            self._apply_kernel_to_ui(self._per_frame_kernels[idx])

        # Update input directly (without going through _set_image which
        # would wipe out the entire batch-golden results list)
        self._image = frame
        self._disp_input.set_image(frame)

        # Restore batch golden output for this frame (if available)
        if idx < len(self._golden_frames):
            self._golden = self._golden_frames[idx]
            self._update_output_display(idx)
        else:
            self._golden = None
            self._disp_output.clear()

        self._frame_lbl.setText(
            f"Frame  {idx + 1}  /  {len(self._video_frames)}"
        )
        self._frame_slider.blockSignals(True)
        self._frame_slider.setValue(idx)
        self._frame_slider.blockSignals(False)

        # Update status bar and notify Analyst for live sync
        total = len(self._video_frames)
        self.sig_frame.emit(idx + 1, total)
        self.sig_video_step.emit(idx)
        if self._golden_frames:
            self._emit_status(
                f"Frame {idx + 1}/{total}  —  golden result restored.",
                self._C_OK
            )
        else:
            self._emit_status(
                f"Frame {idx + 1}/{total}  —  run 'Process All Frames' to compute golden output.",
                self._C_INFO
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _set_image(self, arr: np.ndarray):
        """Set current image, clear stale golden output and batch results."""
        self._image         = arr
        self._golden        = None
        self._golden_frames = []
        self._disp_input.set_image(arr)
        self._disp_output.clear()
        # Disable playback — batch results no longer valid
        if hasattr(self, '_btn_play'):
            self._btn_play.setEnabled(False)
        if hasattr(self, '_fps_sb'):
            self._fps_sb.setEnabled(False)
        # Stop any running playback
        if self._is_playing and self._play_timer:
            self._play_timer.stop()
            self._is_playing = False
            if hasattr(self, '_btn_play'):
                self._btn_play.setText("Play")

    def _clear_video_state(self):
        """
        Enter single-frame mode: wipe all video data and reset every
        navigation control to its idle / disabled state.
        Always call AFTER _set_image() — which handles playback stop
        and golden-frames cleanup — so this method is purely about UI reset.
        """
        # Wipe video buffer and metadata
        self._video_frames.clear()
        self._golden_frames    = []
        self._per_frame_kernels = None
        self._video_idx        = 0

        # Reset slider range & value without triggering _slider_changed
        self._frame_slider.blockSignals(True)
        self._frame_slider.setMaximum(0)
        self._frame_slider.setValue(0)
        self._frame_slider.blockSignals(False)

        # Reset the frame counter label to the idle placeholder
        self._frame_lbl.setText("Frame  —  /  —")

        # Hide/disable all video-mode controls
        self._nav_group.setVisible(False)   # hidden — only shown when a video is active
        self._batch_btn.setEnabled(False)   # "Process All Frames" is video-only
        self._btn_play.setEnabled(False)
        self._fps_sb.setEnabled(False)

    def _get_weights(self) -> np.ndarray:
        return np.array(
            [[self._weight_boxes[r][c].value() for c in range(3)] for r in range(3)],
            dtype=np.uint8,
        )

    def _apply_preset(self, name: str):
        presets = {
            "Edge H":   [[1, 2, 1], [0, 0, 0], [255, 254, 255]],
            "Edge V":   [[1, 0, 255], [2, 0, 254], [1, 0, 255]],
            "Blur":     [[1, 2, 1], [2, 4, 2], [1, 2, 1]],
            "Identity": [[0, 0, 0], [0, 1, 0], [0, 0, 0]],
            "Sharpen":  [[0, 252, 0], [252, 17, 252], [0, 252, 0]],
        }
        vals = presets.get(name)
        if vals:
            for r in range(3):
                for c in range(3):
                    self._weight_boxes[r][c].blockSignals(True)
                    self._weight_boxes[r][c].setValue(vals[r][c])
                    self._weight_boxes[r][c].blockSignals(False)
            self._active_preset = name
            self._emit_kernel_info()

    def _on_weight_changed(self):
        """Mark kernel as CUSTOM when user edits any weight cell manually."""
        self._active_preset = "CUSTOM"
        self._emit_kernel_info()

    def _emit_kernel_info(self):
        bias      = self._bias_sb.value()
        threshold = self._thr_sb.value()
        weights   = [[self._weight_boxes[r][c].value() for c in range(3)]
                     for r in range(3)]
        info = (
            f"Kernel: {self._active_preset}"
            f"  |  Bias: {bias}"
            f"  |  Thr: {threshold}  (0x{threshold:05X})"
        )
        self.sig_kernel.emit(info)
        self.sig_kernel_cfg.emit({
            "weights":     weights,
            "bias":        bias,
            "threshold":   threshold,
            "preset_name": self._active_preset,
        })
        self._save_settings()

    # ── Session persistence ───────────────────────────────────────────────────

    def _save_settings(self):
        """Persist kernel, bias, threshold to QSettings (registry / ini file)."""
        s = QSettings("TAU-EE", "ASIC-Suite")
        weights = self._get_weights()
        for r in range(3):
            for c in range(3):
                s.setValue(f"kernel/w{r}{c}", weights[r][c])
        s.setValue("kernel/bias",      self._bias_sb.value())
        s.setValue("kernel/threshold", self._thr_sb.value())
        s.setValue("kernel/preset",    self._active_preset)
        if self._last_output_dir:
            s.setValue("export/last_dir", self._last_output_dir)

    def _load_settings(self):
        """Restore kernel, bias, threshold from last session."""
        s = QSettings("TAU-EE", "ASIC-Suite")
        # Restore weights (block signals so _on_weight_changed doesn't fire 9 times)
        for r in range(3):
            for c in range(3):
                v = s.value(f"kernel/w{r}{c}", None)
                if v is not None:
                    self._weight_boxes[r][c].blockSignals(True)
                    self._weight_boxes[r][c].setValue(int(v))
                    self._weight_boxes[r][c].blockSignals(False)
        bias = s.value("kernel/bias", None)
        if bias is not None:
            self._bias_sb.blockSignals(True)
            self._bias_sb.setValue(int(bias))
            self._bias_sb.blockSignals(False)
        thr = s.value("kernel/threshold", None)
        if thr is not None:
            self._thr_sb.blockSignals(True)
            self._thr_sb.setValue(int(thr))
            self._thr_sb.blockSignals(False)
        preset = s.value("kernel/preset", None)
        if preset:
            self._active_preset = preset
        self._last_output_dir = s.value("export/last_dir", "") or ""
        # Refresh status bar with loaded values
        self._emit_kernel_info()

    # ── Custom kernel presets ─────────────────────────────────────────────────

    def _get_custom_presets(self) -> list[dict]:
        """Load user-saved custom presets from QSettings."""
        s = QSettings("TAU-EE", "ASIC-Suite")
        import json
        raw = s.value("custom_presets", "[]")
        try:
            return json.loads(raw)
        except Exception:
            return []

    def _set_custom_presets(self, presets: list[dict]) -> None:
        import json
        QSettings("TAU-EE", "ASIC-Suite").setValue("custom_presets", json.dumps(presets))

    def _refresh_custom_preset_combo(self) -> None:
        self._custom_preset_combo.blockSignals(True)
        self._custom_preset_combo.clear()
        self._custom_preset_combo.addItem("— Custom Presets —")
        for p in self._get_custom_presets():
            self._custom_preset_combo.addItem(p["name"])
        self._custom_preset_combo.blockSignals(False)

    def _save_custom_preset(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Save Preset", "Preset name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        presets = self._get_custom_presets()
        # Warn if a preset with this name already exists
        existing = [p for p in presets if p["name"] == name]
        if existing:
            reply = QMessageBox.question(
                self, "Overwrite Preset",
                f"A preset named '{name}' already exists.\nOverwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        presets = [p for p in presets if p["name"] != name]
        weights = [[int(self._weight_boxes[r][c].value()) for c in range(3)]
                   for r in range(3)]
        presets.append({
            "name":      name,
            "weights":   weights,
            "bias":      self._bias_sb.value(),
            "threshold": self._thr_sb.value(),
        })
        self._set_custom_presets(presets)
        self._refresh_custom_preset_combo()
        AppLogger.instance().ok(f"Preset saved: {name}")
        self._emit_status(f"Preset '{name}' saved.", self._C_OK)

    def _load_custom_preset(self, index: int) -> None:
        if index <= 0:
            return   # placeholder item
        presets = self._get_custom_presets()
        if index - 1 >= len(presets):
            return
        p = presets[index - 1]
        for r in range(3):
            for c in range(3):
                self._weight_boxes[r][c].blockSignals(True)
                self._weight_boxes[r][c].setValue(p["weights"][r][c])
                self._weight_boxes[r][c].blockSignals(False)
        self._bias_sb.blockSignals(True)
        self._bias_sb.setValue(p.get("bias", 0))
        self._bias_sb.blockSignals(False)
        self._thr_sb.blockSignals(True)
        self._thr_sb.setValue(p.get("threshold", 2000))
        self._thr_sb.blockSignals(False)
        self._active_preset = p["name"]
        # Keep the selected item visible so the user can delete it without re-selecting
        self._custom_preset_combo.setCurrentIndex(index)
        self._emit_kernel_info()
        self._emit_status(f"Preset '{p['name']}' loaded.", self._C_OK)

    def _delete_custom_preset(self) -> None:
        idx = self._custom_preset_combo.currentIndex()
        if idx <= 0:
            # Nothing selected — inform user
            self._emit_status("Select a custom preset to delete.", self._C_INFO)
            return
        presets = self._get_custom_presets()
        if idx - 1 >= len(presets):
            return
        name = presets[idx - 1]["name"]
        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        presets.pop(idx - 1)
        self._set_custom_presets(presets)
        self._refresh_custom_preset_combo()
        AppLogger.instance().info(f"Preset deleted: {name}")
        self._emit_status(f"Preset '{name}' deleted.", self._C_INFO)

    def _emit_status(self, msg: str, color: str):
        # Status goes to the MainWindow status bar via the signal;
        # the local _status_lbl is an orphan (not in layout) and intentionally unused.
        self.sig_status.emit(msg, color)

    @staticmethod
    def _imread_gray(path: str) -> np.ndarray:
        """Load any image as 256×256 grayscale uint8."""
        if _HAS_CV2:
            # Use np.fromfile + imdecode to support non-ASCII/Unicode paths on Windows
            raw = np.fromfile(path, dtype=np.uint8)
            img = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError(f"cv2 could not decode image: {path}")
            return cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
        elif _HAS_PIL:
            img = PilImage.open(path).convert("L").resize(
                (IMG_SIZE, IMG_SIZE), _PIL_BILINEAR
            )
            return np.array(img, dtype=np.uint8)
        else:
            try:
                import matplotlib.pyplot as mpl_plt
                img = mpl_plt.imread(path)
                if img.max() <= 1.0:
                    img = (img * 255).astype(np.uint8)
                if img.ndim == 3:
                    img = np.dot(img[..., :3], [0.2989, 0.5870, 0.1140]).astype(np.uint8)
                pil = PilImage.fromarray(img).resize((IMG_SIZE, IMG_SIZE))
                return np.array(pil, dtype=np.uint8)
            except Exception as e:
                raise RuntimeError(
                    f"Cannot load image — install Pillow or OpenCV: {e}"
                )

    def _on_export_done(self, run_dir: str, thread: QThread, worker) -> None:
        thread.quit()
        thread.wait()
        try:
            self._overlay.sig_cancel.disconnect(worker.cancel)
        except Exception:
            pass
        self._overlay.hide_loading()
        self._run_btn.setEnabled(True)
        if hasattr(self, "_batch_btn"):
            self._batch_btn.setEnabled(bool(self._video_frames))
        if not run_dir:
            self._emit_status("Export cancelled.", self._C_INFO)
            return
        n = len(self._golden_frames)
        self._export_info.setText(
            f"\u2714  {n} frames  \u2192  {os.path.basename(run_dir)}"
        )
        msg = f"Exported {n} frames → {run_dir}"
        self._emit_status(msg, self._C_OK)
        AppLogger.instance().ok(msg)

    def _on_export_error(self, msg: str, thread: QThread) -> None:
        thread.quit()
        thread.wait()
        self._overlay.hide_loading()
        self._run_btn.setEnabled(True)
        if hasattr(self, "_batch_btn"):
            self._batch_btn.setEnabled(bool(self._video_frames))
        self._emit_status(f"Export error: {msg}", self._C_ERR)
        AppLogger.instance().error(f"Export error: {msg}")

    def _on_cancel_loading(self):
        """Called when the Cancel button is clicked on the loading overlay."""
        self._cancel_loading = True
        # Cancel whichever worker is active
        for worker in (self._batch_worker, self._video_load_worker):
            if worker is not None and hasattr(worker, "cancel"):
                worker.cancel()
        # Disconnect all cancel slots so the next operation starts clean
        try:
            self._overlay.sig_cancel.disconnect()
        except Exception:
            pass
        # Reconnect the generic cancel handler
        self._overlay.sig_cancel.connect(self._on_cancel_loading)
        self._overlay.hide_loading()
        self._run_btn.setEnabled(True)
        if hasattr(self, '_batch_btn'):
            self._batch_btn.setEnabled(bool(self._video_frames))
        self._emit_status("Operation cancelled.", self._C_INFO)

    def _clear_all(self):
        """
        Full reset: stops playback, wipes all loaded data, clears both
        displays, hides the video nav bar, and resets the export info label.
        Triggered by the Clear button in the sidebar.
        """
        # Stop playback first (before we wipe the frame lists it references)
        if self._is_playing and self._play_timer:
            self._play_timer.stop()
            self._is_playing = False
            self._btn_play.setText("Play")

        # Wipe loaded data
        self._image  = None
        self._golden = None

        # Clear both preview displays
        self._disp_input.clear()
        self._disp_output.clear()

        # Reset export info badge
        self._export_info.setText("")

        # Reset all video controls (clears video_frames, hides nav group, etc.)
        self._clear_video_state()

        self._emit_status(
            "Generator cleared — load an image or video to begin.", self._C_INFO
        )

    # ── Public API (called by MainWindow + AnalystWidget) ─────────────────────

    def get_current_config(self) -> dict:
        return {
            "weights":       self._get_weights(),
            "bias":          self._bias_sb.value(),
            "threshold":     self._thr_sb.value(),
            "image":         self._image,
            "golden":        self._golden,
            "video_frames":  self._video_frames,    # list of 256×256 input frames
            "golden_frames": self._golden_frames,   # list of 254×254 results
        }
