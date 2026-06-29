"""
LoadingOverlay — animated full-cover loading card.
Visual style matches the SplashScreen: dark card with animated 3×3 kernel
grid, cyan progress bar with pulse glow, and smooth spinner.

Usage:
    overlay = LoadingOverlay(parent_widget)
    overlay.show_loading("Running Golden Model…")
    overlay.show_loading("Processing Video…", "0 / 40 frames",
                         determinate=True, max_val=40)
    overlay.set_progress(12, "12 / 40 frames done")
    overlay.hide_loading()

The overlay resizes itself automatically when the parent widget is resized.
"""

from __future__ import annotations

import math

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore    import Qt, QThread, QEvent, QRect, QRectF, pyqtSignal
from PyQt6.QtGui     import (
    QPainter, QColor, QFont, QPainterPath,
    QLinearGradient, QBrush, QPen,
)


class _AnimThread(QThread):
    """
    Drives overlay animation at 20 fps in its own OS thread, completely
    independent of the main-thread event loop.  Even when the UI thread is
    busy parsing large files the spinner keeps moving smoothly.
    """
    tick = pyqtSignal(int, int)   # (spinner_idx, tick_count)
    _N   = 10                     # number of Braille frames

    def run(self) -> None:
        s = t = 0
        while not self.isInterruptionRequested():
            self.msleep(50)                    # 20 fps cadence
            if self.isInterruptionRequested():
                break
            s = (s + 1) % self._N
            t = (t + 1) % 200
            self.tick.emit(s, t)

# ── palette (matches splash screen) ───────────────────────────────────────────
_BG       = QColor(8,   8,  12, 210)   # dim backdrop
_CARD_BG  = QColor(28,  28,  30)
_CARD_BRD = QColor(0,  173, 239)
_CYAN     = QColor(0,  173, 239)
_CYAN_DIM = QColor(0,   95, 135)
_WHITE    = QColor(240, 240, 245)
_GREY     = QColor(150, 150, 158)
_GREY_DIM = QColor(80,  80,  88)

_CARD_W          = 420
_CARD_H_BASE     = 280   # card height without cancel button
_CARD_H_CANCEL   = 322   # card height with cancel button


class LoadingOverlay(QWidget):
    """
    Semi-transparent full-cover overlay with:
    - Animated 3×3 kernel grid (identical to SplashScreen)
    - Cyan progress bar with glow tip
    - Braille spinner + title + optional message
    - Optional Cancel button
    """

    _FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    sig_cancel = pyqtSignal()   # emitted when the Cancel button is clicked

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.resize(parent.size())

        self._title       = "Processing…"
        self._msg         = ""
        self._determinate = False
        self._max_val     = 100
        self._value       = 0
        self._cancellable = False
        self._cancel_rect: QRect | None = None

        self._spinner_idx = 0
        self._tick_count  = 0           # drives animations

        self._anim_thread: _AnimThread | None = None
        parent.installEventFilter(self)
        self.hide()

    # ── Public API ────────────────────────────────────────────────────────────

    def show_loading(
        self,
        title: str = "Processing…",
        msg:   str = "",
        *,
        determinate: bool = False,
        max_val: int = 100,
        cancellable: bool = False,
    ) -> None:
        self._title       = title
        self._msg         = msg
        self._determinate = determinate
        self._max_val     = max(1, max_val)
        self._value       = 0
        self._cancellable = cancellable
        self._cancel_rect = None
        self._spinner_idx = 0
        self._tick_count  = 0
        self.resize(self.parent().size())
        self.show()
        self.raise_()
        self._start_anim()

    def set_progress(self, value: int, msg: str = "") -> None:
        self._value = max(0, min(value, self._max_val))
        if msg:
            self._msg = msg
        self.update()

    def set_message(self, msg: str) -> None:
        self._msg = msg
        self.update()

    def hide_loading(self) -> None:
        self._stop_anim()
        self.hide()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _start_anim(self) -> None:
        """Start (or restart) the animation thread."""
        self._stop_anim()
        self._anim_thread = _AnimThread()
        self._anim_thread.tick.connect(self._on_anim_tick)
        self._anim_thread.start()

    def _stop_anim(self) -> None:
        """Stop the animation thread, waiting up to 500 ms for clean exit."""
        if self._anim_thread is not None and self._anim_thread.isRunning():
            self._anim_thread.requestInterruption()
            self._anim_thread.quit()
            if not self._anim_thread.wait(500):
                self._anim_thread.terminate()
                self._anim_thread.wait(200)
        self._anim_thread = None

    def _on_anim_tick(self, spinner_idx: int, tick_count: int) -> None:
        self._spinner_idx = spinner_idx
        self._tick_count  = tick_count
        self.update()

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.resize(obj.size())
        return False

    def mousePressEvent(self, event):
        if (self._cancellable and self._cancel_rect is not None
                and self._cancel_rect.contains(event.pos())):
            self.sig_cancel.emit()
        super().mousePressEvent(event)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        _CARD_H = _CARD_H_CANCEL if self._cancellable else _CARD_H_BASE

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── dim backdrop ──────────────────────────────────────────────────────
        p.fillRect(self.rect(), _BG)

        # ── card position (centred) ───────────────────────────────────────────
        pw, ph = self.width(), self.height()
        cx = (pw - _CARD_W) // 2
        cy = (ph - _CARD_H) // 2

        # ── card background ───────────────────────────────────────────────────
        card_path = QPainterPath()
        card_path.addRoundedRect(QRectF(cx, cy, _CARD_W, _CARD_H), 16, 16)
        p.fillPath(card_path, QBrush(_CARD_BG))
        p.setPen(QPen(_CARD_BRD, 1.5))
        p.drawPath(card_path)

        # ── top cyan stripe ───────────────────────────────────────────────────
        sg = QLinearGradient(cx, 0, cx + _CARD_W, 0)
        sg.setColorAt(0.0, QColor(0, 173, 239, 0))
        sg.setColorAt(0.25, _CYAN)
        sg.setColorAt(0.75, _CYAN)
        sg.setColorAt(1.0, QColor(0, 173, 239, 0))
        p.setPen(Qt.PenStyle.NoPen)
        stripe_path = QPainterPath()
        stripe_path.addRoundedRect(QRectF(cx + 2, cy + 2, _CARD_W - 4, 4), 2, 2)
        p.fillPath(stripe_path, QBrush(sg))

        # ── spinner ───────────────────────────────────────────────────────────
        spin_y = cy + 22
        f_spin = QFont("Segoe UI", 20)
        p.setFont(f_spin)
        p.setPen(_CYAN)
        p.drawText(
            QRect(cx, spin_y, _CARD_W, 30),
            Qt.AlignmentFlag.AlignHCenter,
            self._FRAMES[self._spinner_idx],
        )

        # ── title ─────────────────────────────────────────────────────────────
        title_y = spin_y + 32
        f_title = QFont("Heebo", 13, QFont.Weight.Bold)
        p.setFont(f_title)
        p.setPen(_WHITE)
        p.drawText(
            QRect(cx + 20, title_y, _CARD_W - 40, 28),
            Qt.AlignmentFlag.AlignHCenter,
            self._title,
        )

        # ── animated 3×3 kernel grid ──────────────────────────────────────────
        grid_top = title_y + 34
        self._draw_kernel_grid(p, cx + _CARD_W // 2, grid_top)

        # ── message ───────────────────────────────────────────────────────────
        msg_y = grid_top + 82
        if self._msg:
            f_msg = QFont("Heebo", 9)
            p.setFont(f_msg)
            p.setPen(_GREY)
            p.drawText(
                QRect(cx + 20, msg_y, _CARD_W - 40, 20),
                Qt.AlignmentFlag.AlignHCenter,
                self._msg,
            )

        # ── cancel button (optional) ──────────────────────────────────────────
        if self._cancellable:
            btn_w, btn_h = 110, 28
            btn_x = cx + (_CARD_W - btn_w) // 2
            btn_y = cy + _CARD_H - 76   # above progress bar area
            self._cancel_rect = QRect(btn_x, btn_y, btn_w, btn_h)
            # button background
            btn_path = QPainterPath()
            btn_path.addRoundedRect(QRectF(btn_x, btn_y, btn_w, btn_h), 6, 6)
            p.fillPath(btn_path, QBrush(QColor(60, 30, 30)))
            p.setPen(QPen(QColor(200, 60, 60), 1))
            p.drawPath(btn_path)
            # button label
            f_btn = QFont("Heebo", 9, QFont.Weight.Bold)
            p.setFont(f_btn)
            p.setPen(QColor(240, 100, 100))
            p.drawText(
                self._cancel_rect,
                Qt.AlignmentFlag.AlignCenter,
                "✕  Cancel",
            )
        else:
            self._cancel_rect = None

        # ── progress bar ──────────────────────────────────────────────────────
        bar_x = cx + 30
        bar_y = cy + _CARD_H - 46
        bar_w = _CARD_W - 60
        bar_h = 7
        bar_r = bar_h // 2

        # track
        p.setPen(Qt.PenStyle.NoPen)
        track = QPainterPath()
        track.addRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), bar_r, bar_r)
        p.fillPath(track, QBrush(QColor(50, 50, 55)))

        # fill
        if self._determinate:
            fill_frac = self._value / self._max_val
        else:
            # indeterminate: sliding pulse
            t = self._tick_count / 200.0
            fill_frac = abs(math.sin(t * math.pi))

        fill_w = max(bar_r * 2, int(bar_w * fill_frac))
        if fill_w > 0:
            grad = QLinearGradient(bar_x, 0, bar_x + fill_w, 0)
            grad.setColorAt(0.0, QColor(0, 100, 170))
            grad.setColorAt(1.0, _CYAN)
            fill_path = QPainterPath()
            fill_path.addRoundedRect(
                QRectF(bar_x, bar_y, fill_w, bar_h), bar_r, bar_r
            )
            p.fillPath(fill_path, QBrush(grad))

            # pulse glow tip
            glow_alpha = int(
                abs(math.sin(self._tick_count * 0.08 * math.pi)) * 160
            ) + 60
            glow_len = min(30, fill_w)
            gp = QLinearGradient(bar_x + fill_w - glow_len, 0, bar_x + fill_w, 0)
            gp.setColorAt(0.0, QColor(0, 220, 255, 0))
            gp.setColorAt(1.0, QColor(0, 220, 255, glow_alpha))
            glow_path = QPainterPath()
            glow_path.addRoundedRect(
                QRectF(bar_x + fill_w - glow_len, bar_y, glow_len, bar_h),
                bar_r, bar_r,
            )
            p.fillPath(glow_path, QBrush(gp))

        # percentage (determinate only) — drawn above the track, left-aligned
        if self._determinate:
            f_pct = QFont("Heebo", 8)
            p.setFont(f_pct)
            p.setPen(_CYAN)
            pct = int(self._value / self._max_val * 100)
            p.drawText(
                QRect(bar_x, bar_y + bar_h + 4, bar_w, 14),
                Qt.AlignmentFlag.AlignCenter,
                f"{pct}%",
            )

        p.end()

    def _draw_kernel_grid(self, p: QPainter, center_x: int, top_y: int):
        """Animated 3×3 grid — same as SplashScreen."""
        cell  = 20
        gap   = 4
        total = 3 * cell + 2 * gap
        x0    = center_x - total // 2
        tick  = self._tick_count

        for row in range(3):
            for col in range(3):
                bx = x0 + col * (cell + gap)
                by = top_y + row * (cell + gap)

                phase = (row * 3 + col - tick // 6) % 9
                alpha = 35 + int((1 - phase / 9) * 190)

                fill = QColor(0, 173, 239, alpha)
                brd  = (QColor(0, 173, 239, 200)
                        if (row == 1 and col == 1)
                        else QColor(0, 173, 239, 90))

                p.setPen(QPen(brd, 1))
                p.setBrush(QBrush(fill))
                p.drawRoundedRect(bx, by, cell, cell, 4, 4)

                val = ["1", "0", "1", "0", "4", "0", "1", "0", "1"][row * 3 + col]
                f   = QFont("Heebo", 7)
                p.setFont(f)
                p.setPen(QColor(200, 230, 255, 200))
                p.drawText(
                    QRect(bx, by, cell, cell),
                    Qt.AlignmentFlag.AlignCenter,
                    val,
                )
