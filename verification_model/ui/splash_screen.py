"""
Splash screen for ASIC Verification & Analysis Suite.
Shows an animated loading screen while the main window initialises.
"""

import os
import sys

from PyQt6.QtWidgets import QSplashScreen, QApplication
from PyQt6.QtCore    import Qt, QTimer, QRect, QPoint
from PyQt6.QtGui     import (
    QPainter, QColor, QFont, QPixmap, QLinearGradient,
    QBrush, QPen, QFontDatabase, QPainterPath, QImage
)

# ── palette ────────────────────────────────────────────────────────────────────
_BG       = QColor(26,  26,  27)
_CARD     = QColor(35,  35,  37)
_CYAN     = QColor(0,  173, 239)
_CYAN20   = QColor(0,  173, 239, 50)
_CYAN50   = QColor(0,  173, 239, 128)
_WHITE    = QColor(255, 255, 255)
_GREY     = QColor(140, 140, 148)
_GREY_DIM = QColor(80,  80,  88)

_W, _H    = 640, 380          # splash dimensions


def _resource(rel_path: str) -> str:
    """Resolve path relative to the package root (works in dev & PyInstaller)."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS          # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


class SplashScreen(QSplashScreen):
    """
    Animated frameless splash screen.

    Usage
    -----
    splash = SplashScreen()
    splash.show()
    app.processEvents()
    # … heavy initialisation …
    splash.finish(main_window)
    """

    _MESSAGES = [
        "Initialising hardware model …",
        "Loading convolution engine …",
        "Preparing analysis tools …",
        "Building UI components …",
        "Ready.",
    ]

    def __init__(self):
        # Detect device pixel ratio for crisp HiDPI rendering
        screen = QApplication.primaryScreen()
        self._dpr: float = screen.devicePixelRatio() if screen else 1.0

        # Build the base pixmap at full physical resolution
        pix = QPixmap(int(_W * self._dpr), int(_H * self._dpr))
        pix.setDevicePixelRatio(self._dpr)
        pix.fill(Qt.GlobalColor.transparent)
        super().__init__(pix, Qt.WindowType.WindowStaysOnTopHint |
                              Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._progress   = 0          # 0..100
        self._msg_idx    = 0
        self._pulse_tick = 0
        self._dots       = 0

        # Dot-pulse animation
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)         # ~25 fps

        # Load TAU logo at full source resolution (no pre-scaling)
        logo_path  = _resource("tau_logo.png")
        self._logo = QPixmap(logo_path) if os.path.exists(logo_path) else QPixmap()

        # Load TAU banner ("EXPANDING the BOUNDARIES of POSSIBILITY")
        banner_path   = _resource("banner logo.png")
        self._banner  = QPixmap(banner_path) if os.path.exists(banner_path) else QPixmap()

        self._centre_on_screen()

    # ── helpers ────────────────────────────────────────────────────────────────
    def _centre_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            self.move(sg.center() - QPoint(_W // 2, _H // 2))

    def _tick(self):
        self._pulse_tick = (self._pulse_tick + 1) % 100
        self.repaint()

    # ── public API ─────────────────────────────────────────────────────────────
    def set_progress(self, value: int, message: str = ""):
        """Set progress 0-100 and optional status message."""
        self._progress = max(0, min(100, value))
        if message:
            self.showMessage(message)      # stored by base class
        self.repaint()
        QApplication.processEvents()

    def advance(self):
        """Step to the next preset message and advance progress proportionally."""
        n  = len(self._MESSAGES)
        idx = min(self._msg_idx, n - 1)
        self.set_progress(int((idx + 1) / n * 100), self._MESSAGES[idx])
        self._msg_idx = min(self._msg_idx + 1, n - 1)

    # ── painting ───────────────────────────────────────────────────────────────
    def drawContents(self, painter: QPainter):
        """Override so we control every pixel."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── background ────────────────────────────────────────────────────────
        path = QPainterPath()
        path.addRoundedRect(0, 0, _W, _H, 18, 18)
        painter.setClipPath(path)
        painter.fillRect(0, 0, _W, _H, _BG)

        # subtle vertical gradient overlay
        grad = QLinearGradient(0, 0, 0, _H)
        grad.setColorAt(0.0,  QColor(50, 50, 55, 60))
        grad.setColorAt(1.0,  QColor(0,   0,  0, 0))
        painter.fillRect(0, 0, _W, _H, QBrush(grad))

        # ── border ────────────────────────────────────────────────────────────
        pen = QPen(_CYAN, 2)
        painter.setPen(pen)
        border_path = QPainterPath()
        border_path.addRoundedRect(1, 1, _W - 2, _H - 2, 17, 17)
        painter.drawPath(border_path)

        # ── top cyan stripe ───────────────────────────────────────────────────
        stripe_h = 5
        stripe_grad = QLinearGradient(0, 0, _W, 0)
        stripe_grad.setColorAt(0.0, QColor(0, 173, 239, 0))
        stripe_grad.setColorAt(0.3, _CYAN)
        stripe_grad.setColorAt(0.7, _CYAN)
        stripe_grad.setColorAt(1.0, QColor(0, 173, 239, 0))
        painter.fillRect(2, 2, _W - 4, stripe_h, QBrush(stripe_grad))

        # ── decorative circuit lines (background) ─────────────────────────────
        self._draw_circuit_deco(painter)

        # ── TAU logo ──────────────────────────────────────────────────────────
        logo_y = 38
        if not self._logo.isNull():
            max_logo_w = 180   # logical pixels
            # Scale in physical pixels for full sharpness on HiDPI screens
            phys_w = int(max_logo_w * self._dpr)
            scaled = self._logo.scaledToWidth(
                phys_w, Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(self._dpr)
            # Logical size after DPR is applied
            logo_logical_w = scaled.width()  / self._dpr   # == max_logo_w
            logo_logical_h = scaled.height() / self._dpr
            lx = int((_W - logo_logical_w) // 2)
            painter.drawPixmap(lx, logo_y, scaled)
            logo_bottom = logo_y + int(logo_logical_h) + 10
        else:
            # fallback text
            f = QFont("Heebo", 18, QFont.Weight.Bold)
            painter.setFont(f)
            painter.setPen(_CYAN)
            painter.drawText(QRect(0, logo_y, _W, 40),
                             Qt.AlignmentFlag.AlignHCenter, "TAU")
            logo_bottom = logo_y + 50

        # ── title ─────────────────────────────────────────────────────────────
        title_y = logo_bottom + 4
        f_title = QFont("Heebo", 15, QFont.Weight.Bold)
        painter.setFont(f_title)
        painter.setPen(_WHITE)
        painter.drawText(QRect(20, title_y, _W - 40, 30),
                         Qt.AlignmentFlag.AlignHCenter,
                         "ASIC Verification & Analysis Suite")

        # ── banner logo ("EXPANDING the BOUNDARIES of POSSIBILITY") ──────────
        sub_y = title_y + 34   # title QRect height is 30px + 4px gap
        banner_h = 0
        if not self._banner.isNull():
            target_h  = 55  # logical pixels — capped so nothing overflows
            phys_h    = int(target_h * self._dpr)
            s_banner  = self._banner.scaledToHeight(
                phys_h, Qt.TransformationMode.SmoothTransformation)
            s_banner.setDevicePixelRatio(self._dpr)
            b_logical_w = s_banner.width() / self._dpr
            bx = int((_W - b_logical_w) // 2)
            painter.drawPixmap(int(bx), sub_y, s_banner)
            banner_h = target_h + 6
        else:
            f_sub = QFont("Heebo", 10)
            painter.setFont(f_sub)
            painter.setPen(_GREY)
            painter.drawText(QRect(20, sub_y, _W - 40, 22),
                             Qt.AlignmentFlag.AlignHCenter,
                             "Area & Power Optimized Hardware Accelerator — 3×3 Convolution Kernel")
            banner_h = 30

        # ── 3×3 kernel visualisation ──────────────────────────────────────────
        kernel_y = sub_y + banner_h
        self._draw_kernel_grid(painter, _W // 2, kernel_y)

        # ── divider ───────────────────────────────────────────────────────────
        # grid cells: 3×22 + 2×4 = 74px, "3×3 Kernel" label adds 18px → total 92px
        div_y = kernel_y + 98
        painter.setPen(QPen(_GREY_DIM, 1))
        painter.drawLine(40, div_y, _W - 40, div_y)

        # ── progress bar ──────────────────────────────────────────────────────
        bar_y  = div_y + 14
        bar_h  = 8
        bar_x  = 50
        bar_w  = _W - 100
        bar_r  = bar_h // 2

        # track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_CARD))
        track_path = QPainterPath()
        track_path.addRoundedRect(bar_x, bar_y, bar_w, bar_h, bar_r, bar_r)
        painter.drawPath(track_path)

        # fill
        fill_w = int(bar_w * self._progress / 100)
        if fill_w > 0:
            fill_grad = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            fill_grad.setColorAt(0.0, QColor(0, 120, 180))
            fill_grad.setColorAt(1.0, _CYAN)
            fill_path = QPainterPath()
            fill_path.addRoundedRect(bar_x, bar_y, fill_w, bar_h, bar_r, bar_r)
            painter.fillPath(fill_path, QBrush(fill_grad))

        # pulse glow at tip
        if fill_w > bar_r:
            pulse_alpha = int(abs(math.sin(self._pulse_tick * 0.07 * math.pi)) * 160) + 40
            glow = QColor(0, 200, 255, pulse_alpha)
            gp = QLinearGradient(bar_x + fill_w - 20, 0, bar_x + fill_w, 0)
            gp.setColorAt(0.0, QColor(0, 200, 255, 0))
            gp.setColorAt(1.0, glow)
            glow_path = QPainterPath()
            glow_path.addRoundedRect(bar_x + fill_w - 20, bar_y,
                                     20, bar_h, bar_r, bar_r)
            painter.fillPath(glow_path, QBrush(gp))

        # ── progress % ────────────────────────────────────────────────────────
        pct_y = bar_y + bar_h + 6
        f_pct = QFont("Heebo", 9)
        painter.setFont(f_pct)
        painter.setPen(_CYAN)
        painter.drawText(QRect(bar_x, pct_y, bar_w, 18),
                         Qt.AlignmentFlag.AlignRight,
                         f"{self._progress}%")

        # ── status message ────────────────────────────────────────────────────
        msg_y = pct_y
        msg   = self.message() or "Loading …"
        painter.setPen(_GREY)
        painter.drawText(QRect(bar_x, msg_y, bar_w - 44, 18),
                         Qt.AlignmentFlag.AlignLeft, msg)

        # ── footer ────────────────────────────────────────────────────────────
        f_eng = QFont("Heebo", 9)
        painter.setFont(f_eng)
        painter.setPen(_GREY)
        painter.drawText(QRect(20, _H - 46, _W - 40, 18),
                         Qt.AlignmentFlag.AlignHCenter,
                         "Roy Friedman  ·  Idan Marchevsky")

        footer_y = _H - 28
        f_foot = QFont("Heebo", 8)
        painter.setFont(f_foot)
        painter.setPen(_GREY_DIM)
        painter.drawText(QRect(20, footer_y, _W - 40, 20),
                         Qt.AlignmentFlag.AlignHCenter,
                         "Tel Aviv University  ·  Electrical Engineering  ·  v1.0")

    # ── decorative helpers ─────────────────────────────────────────────────────
    def _draw_circuit_deco(self, p: QPainter):
        """Draw faint circuit-board lines in the background corners."""
        pen = QPen(_CYAN20, 1)
        p.setPen(pen)
        # bottom-right corner decoration
        for i in range(4):
            x = _W - 30 - i * 18
            p.drawLine(x, _H - 10, x, _H - 10 - 10 - i * 8)
            p.drawLine(x, _H - 10 - 10 - i * 8,
                       x - 12, _H - 10 - 10 - i * 8)
        # top-left corner decoration
        for i in range(3):
            y = 16 + i * 16
            p.drawLine(14, y, 14 + 10 + i * 8, y)
            p.drawLine(14 + 10 + i * 8, y,
                       14 + 10 + i * 8, y + 10)

    def _draw_kernel_grid(self, p: QPainter, cx: int, top: int):
        """Draw an animated 3×3 grid representing the convolution kernel."""
        cell  = 22
        gap   = 4
        total = 3 * cell + 2 * gap
        x0    = cx - total // 2
        y0    = top

        tick = self._pulse_tick

        for row in range(3):
            for col in range(3):
                bx = x0 + col * (cell + gap)
                by = y0 + row * (cell + gap)

                # animated alpha cycling through cells
                phase = (row * 3 + col - tick // 8) % 9
                alpha = 40 + int((1 - phase / 9) * 180)

                fill  = QColor(0, 173, 239, alpha)
                brd   = QColor(0, 173, 239, 180) if (row == 1 and col == 1) else \
                        QColor(0, 173, 239, 90)

                p.setPen(QPen(brd, 1))
                p.setBrush(QBrush(fill))
                p.drawRoundedRect(bx, by, cell, cell, 4, 4)

                # centre value label
                val = ["1","0","1","0","4","0","1","0","1"][row * 3 + col]
                f   = QFont("Heebo", 7)
                p.setFont(f)
                p.setPen(QColor(200, 230, 255, 200))
                p.drawText(QRect(bx, by, cell, cell),
                           Qt.AlignmentFlag.AlignCenter, val)

        # label
        f_lbl = QFont("Heebo", 8)
        p.setFont(f_lbl)
        p.setPen(_GREY_DIM)
        p.drawText(QRect(cx - total // 2, y0 + total + 2, total, 16),
                   Qt.AlignmentFlag.AlignHCenter, "3×3 Kernel")


import math   # used in drawContents — ensure available at module level
