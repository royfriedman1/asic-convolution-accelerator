"""
Reusable image-display widget.

Features:
  - Responsive: fills its parent's available space while keeping aspect ratio
  - Shows title, pixel dimensions, and an optional info line
  - build_mismatch_rgb() correctly handles the 254×254 valid region
"""

from __future__ import annotations
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QToolTip
)
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt, QSize, QPoint, QTimer, pyqtSignal, QUrl


# ──────────────────────────────────────────────────────────────────────────────
# Numpy → QPixmap
# ──────────────────────────────────────────────────────────────────────────────

def _ndarray_to_pixmap(arr: np.ndarray) -> QPixmap:
    """
    Convert a uint8 numpy array to QPixmap.
    Supports:  (H, W)     → Grayscale8
               (H, W, 3)  → RGB888
    """
    a = np.ascontiguousarray(arr, dtype=np.uint8)
    if a.ndim == 2:
        h, w = a.shape
        q = QImage(a.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
    elif a.ndim == 3 and a.shape[2] == 3:
        h, w, _ = a.shape
        q = QImage(a.tobytes(), w, h, w * 3, QImage.Format.Format_RGB888)
    else:
        raise ValueError(f"Unsupported array shape: {arr.shape}")
    return QPixmap.fromImage(q)


# ──────────────────────────────────────────────────────────────────────────────
# Mismatch visualisation
# ──────────────────────────────────────────────────────────────────────────────

def build_mismatch_rgb(golden: np.ndarray, chip: np.ndarray) -> np.ndarray:
    """
    Build a 254×254 RGB comparison image from two 254×254 binary arrays.

    Colour key:
      #00dd77  (green) — matching pixel
      #ff3344  (red)   — mismatching pixel
    """
    match = (golden == chip)
    rgb = np.empty((254, 254, 3), dtype=np.uint8)
    rgb[match]  = [0x00, 0xdd, 0x77]
    rgb[~match] = [0xff, 0x33, 0x44]
    return rgb


# ──────────────────────────────────────────────────────────────────────────────
# Widget
# ──────────────────────────────────────────────────────────────────────────────

class ImageDisplay(QWidget):
    """
    Card-style image display panel.

    Adaptive sizing: the image label expands to fill available space
    and the pixmap is rescaled on every resize event, preserving aspect ratio.

    Extra features:
    - ＋ / − buttons for zoom (50% – 800%)
    - Drag & drop: accepts image files and .txt / .hex files
      → emits sig_file_dropped(path) so the parent widget can load it
    """

    sig_file_dropped = pyqtSignal(str)   # absolute path of the dropped file

    _MIN_DISPLAY = 120     # minimum edge length (px) — prevents layout collapse
    _ZOOM_MIN    = 0.5
    _ZOOM_MAX    = 8.0

    def __init__(self, title: str = "", placeholder_text: str = "NO IMAGE", parent=None):
        super().__init__(parent)
        self._title       = title
        self._placeholder = placeholder_text
        self._pixmap: QPixmap | None = None
        self._array:  np.ndarray | None = None
        self._last_tip_pos: QPoint | None = None   # throttle tooltip updates
        self._zoom: float = 1.0                    # current zoom factor
        self._build_ui()
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        self.setObjectName("img_frame")

        # Widget-level expanding policy so it grows inside its parent layout.
        # Minimum size on the outer widget (not the inner label) prevents
        # total collapse without affecting layout width distribution.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(self._MIN_DISPLAY, self._MIN_DISPLAY)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(3)

        # Title
        self._title_lbl = QLabel(self._title.upper())
        self._title_lbl.setObjectName("img_title")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title_lbl)

        # Image area — expands and scales.
        # Policy.Ignored: the label's sizeHint (= current pixmap size) is
        # completely ignored by the parent layout.  Space is allocated purely
        # by stretch factors, so two ImageDisplay widgets with stretch=1 always
        # get identical dimensions regardless of their loaded image content.
        self._img_lbl = QLabel(self._placeholder)
        self._img_lbl.setObjectName("img_label_display")
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setMinimumSize(0, 0)
        self._img_lbl.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Ignored,
        )
        self._img_lbl.setMouseTracking(True)   # propagate hover without button press
        layout.addWidget(self._img_lbl, stretch=1)

        # Info row — full width, no buttons
        self._info_lbl = QLabel("")
        self._info_lbl.setObjectName("img_info")
        self._info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_lbl.setMinimumWidth(0)
        layout.addWidget(self._info_lbl)

        # Zoom row — [−] [+] right-aligned
        zoom_row = QHBoxLayout()
        zoom_row.setContentsMargins(0, 0, 0, 0)
        zoom_row.setSpacing(4)

        self._btn_zoom_out = QPushButton("−")
        self._btn_zoom_out.setObjectName("btn_zoom")
        self._btn_zoom_out.setFixedSize(22, 22)
        self._btn_zoom_out.setToolTip("Zoom out")
        self._btn_zoom_out.clicked.connect(self._zoom_out)

        self._btn_zoom_in = QPushButton("+")
        self._btn_zoom_in.setObjectName("btn_zoom")
        self._btn_zoom_in.setFixedSize(22, 22)
        self._btn_zoom_in.setToolTip("Zoom in")
        self._btn_zoom_in.clicked.connect(self._zoom_in)

        zoom_row.addStretch()
        zoom_row.addWidget(self._btn_zoom_out)
        zoom_row.addWidget(self._btn_zoom_in)
        layout.addLayout(zoom_row)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_image(self, array: np.ndarray, info: str = "") -> None:
        """
        Display a numpy uint8 array.

        For 256×256 images that embed a 254×254 valid region (rows/cols 2+),
        the caller should pass the full 256×256 canvas — the black border
        at the top-left acts as the visual invalid-region indicator.
        """
        pix = _ndarray_to_pixmap(array)
        self._pixmap = pix
        self._array  = array
        self._last_tip_pos = None
        self._zoom = 1.0   # reset zoom on new image
        self._rescale()

        if info:
            self._info_lbl.setText(info)
        else:
            h, w = array.shape[:2]
            self._info_lbl.setText(f"{w}\u00d7{h} px")

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title.upper())

    def set_info(self, text: str) -> None:
        self._info_lbl.setText(text)

    def clear(self) -> None:
        self._pixmap = None
        self._array  = None
        self._last_tip_pos = None
        self._img_lbl.setPixmap(QPixmap())
        self._img_lbl.setText(self._placeholder)
        self._info_lbl.setText("")

    # ── Pixel hover ───────────────────────────────────────────────────────────

    def _img_pixel_at(self, widget_pos):
        """Map a widget-local QPoint to (row, col) in the original array, or None."""
        if self._pixmap is None or self._array is None:
            return None
        # Use the actual rendered pixmap size — correct at any zoom level.
        lbl_pix = self._img_lbl.pixmap()
        if lbl_pix is None or lbl_pix.isNull():
            return None
        disp_w, disp_h = lbl_pix.width(), lbl_pix.height()
        orig_w, orig_h = self._pixmap.width(), self._pixmap.height()
        if disp_w == 0 or disp_h == 0 or orig_w == 0 or orig_h == 0:
            return None
        lw, lh = self._img_lbl.width(), self._img_lbl.height()
        ox = (lw - disp_w) // 2
        oy = (lh - disp_h) // 2
        p = self._img_lbl.mapFrom(self, widget_pos)
        x, y = p.x() - ox, p.y() - oy
        if x < 0 or y < 0 or x >= disp_w or y >= disp_h:
            return None
        col = min(int(x * orig_w / disp_w), self._array.shape[1] - 1)
        row = min(int(y * orig_h / disp_h), self._array.shape[0] - 1)
        return row, col

    def mouseMoveEvent(self, event):
        pos = event.pos()
        # Throttle: skip if cursor moved less than 4 px (avoids tooltip flood)
        if self._last_tip_pos is not None:
            d = pos - self._last_tip_pos
            if abs(d.x()) < 4 and abs(d.y()) < 4:
                super().mouseMoveEvent(event)
                return
        self._last_tip_pos = pos

        rc = self._img_pixel_at(pos)
        if rc is not None:
            row, col = rc
            val = self._array[row, col]
            if self._array.ndim == 2:
                tip = f"x={col}, y={row}  →  {int(val)}"
            else:
                tip = f"x={col}, y={row}  →  ({int(val[0])}, {int(val[1])}, {int(val[2])})"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._last_tip_pos = None
        QToolTip.hideText()
        super().leaveEvent(event)

    # ── Button zoom ───────────────────────────────────────────────────────────

    def _apply_zoom(self, factor: float) -> None:
        if self._pixmap is None:
            return
        self._zoom = max(self._ZOOM_MIN, min(self._ZOOM_MAX, self._zoom * factor))
        self._rescale()
        pct = int(self._zoom * 100)
        self._info_lbl.setText(
            (self._info_lbl.text().split("  [")[0]) + f"  [{pct}%]"
        )

    def _zoom_in(self)  -> None: self._apply_zoom(1.25)
    def _zoom_out(self) -> None: self._apply_zoom(1 / 1.25)

    def wheelEvent(self, event):
        # Do NOT zoom on scroll — pass event up so parent can scroll.
        event.ignore()

    # ── Drag & drop ───────────────────────────────────────────────────────────

    _ACCEPTED_EXTS = {
        ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp",
        ".txt", ".hex",
    }

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(
                QUrl(u).toLocalFile().lower().endswith(tuple(self._ACCEPTED_EXTS))
                for u in urls
            ):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext  = path.lower().rsplit(".", 1)[-1]
            if f".{ext}" in self._ACCEPTED_EXTS:
                self.sig_file_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()

    # ── Resize event ──────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._pixmap is None:
            return
        # Use the label's ACTUAL Qt-allocated size — this is always correct
        # regardless of margins, spacings, or how many rows are in the layout.
        # Computing it manually from widget dimensions is error-prone and causes
        # the image to occasionally overflow the frame on resize / first paint.
        lw = max(1, self._img_lbl.width())
        lh = max(1, self._img_lbl.height())
        avail_w = max(1, int(lw * self._zoom))
        avail_h = max(1, int(lh * self._zoom))
        self._img_lbl.setPixmap(
            self._pixmap.scaled(
                QSize(avail_w, avail_h),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
