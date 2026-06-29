"""
About Dialog — TAU ASIC Verification Suite
"""
from __future__ import annotations
import os
import sys

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QUrl, QSize
from PyQt6.QtGui import QDesktopServices, QFont, QPixmap

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AboutDialog(QDialog):

    _STYLE = """
        QDialog {
            background: #1A1A1B;
        }
        QLabel {
            color: #E0E0E5;
            font-family: 'Heebo', 'Segoe UI', Arial;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About — ASIC Verification Suite")
        self.setFixedSize(600, 480)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint
        )
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setStyleSheet(self._STYLE)
        self._build_ui()
        # Center on primary screen, not on parent (avoids going off-screen)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 20, 32, 24)
        lay.setSpacing(10)

        # ── Logo header ───────────────────────────────────────────────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(16)

        # TAU logo (left side, white background pill)
        tau_pix = QPixmap(os.path.join(_PKG_ROOT, "tau_logo.png"))
        if not tau_pix.isNull():
            tau_pix = tau_pix.scaledToHeight(
                60, Qt.TransformationMode.SmoothTransformation)
            logo_lbl = QLabel()
            logo_lbl.setPixmap(tau_pix)
            logo_lbl.setFixedSize(tau_pix.width() + 16, 72)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo_lbl.setStyleSheet(
                "background: #FFFFFF; border-radius: 8px; padding: 6px 8px;")
            header.addWidget(logo_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Banner logo (right side — "EXPANDING the BOUNDARIES of POSSIBILITY")
        banner_pix = QPixmap(os.path.join(_PKG_ROOT, "banner logo.png"))
        if not banner_pix.isNull():
            banner_pix = banner_pix.scaledToHeight(
                64, Qt.TransformationMode.SmoothTransformation)
            banner_lbl = QLabel()
            banner_lbl.setPixmap(banner_pix)
            banner_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            banner_lbl.setStyleSheet("background: transparent;")
            header.addWidget(banner_lbl, stretch=1,
                             alignment=Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(header)

        # ── Title ─────────────────────────────────────────────────────────────
        title = QLabel("ASIC Verification Suite")
        title.setFont(QFont("Heebo", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #00ADEF;")
        lay.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel(
            "Area & Power Optimized Hardware Accelerator\n"
            "for Single Convolutional Kernel"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #8A8A8E; font-size: 11px;")
        lay.addWidget(subtitle)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #3A3A3C;")
        lay.addWidget(sep)

        # ── Info grid ─────────────────────────────────────────────────────────
        def _row(label: str, value: str, link: str = ""):
            row_w = QFrame()
            row_w.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setMinimumWidth(130)       # Python-side — not dependent on CSS
            lbl.setStyleSheet("color: #6E6E73; font-size: 11px;")
            row_l.addWidget(lbl)
            if link:
                val = QLabel(f'<a href="{link}" style="color:#00ADEF;">{value}</a>')
                val.setOpenExternalLinks(True)
            else:
                val = QLabel(value)
                val.setStyleSheet("font-size: 11px;")
            row_l.addWidget(val, stretch=1)
            return row_w

        lay.addWidget(_row("Version",       "v1.0  (2025)"))
        lay.addWidget(_row("Institution",   "Tel Aviv University — Electrical Engineering"))
        lay.addWidget(_row("Authors",       "Roy Friedman,  Idan Marchevsky"))
        lay.addWidget(_row("Roy Friedman",  "LinkedIn",
                           "https://www.linkedin.com/in/roy-friedman-557aaa288"))
        lay.addWidget(_row("Idan Marchevsky", "LinkedIn",
                           "https://www.linkedin.com/in/idan-marchevsky-96b434359"))

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: #3A3A3C;")
        lay.addWidget(sep2)

        # ── HW Spec ───────────────────────────────────────────────────────────
        spec = QLabel(
            "Hardware Spec:  3×3 convolution accelerator  |  256×256 input  "
            "|  20-bit ACC  |  1 px/clk\n"
            "Valid region: 254×254  |  8-bit weights / bias  |  20-bit threshold"
        )
        spec.setStyleSheet("color: #5A5A60; font-size: 10px;")
        spec.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spec.setWordWrap(True)
        lay.addWidget(spec)

        # ── Stack info ────────────────────────────────────────────────────────
        stack = QLabel("Built with  PyQt6 · NumPy · Matplotlib · OpenCV")
        stack.setStyleSheet("color: #4A4A50; font-size: 10px;")
        stack.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(stack)

        lay.addStretch()

        # ── Close button ──────────────────────────────────────────────────────
        close_btn = QPushButton("Close")
        close_btn.setFixedSize(100, 30)
        close_btn.setStyleSheet(
            "QPushButton { background:#2C2C2E; color:#E0E0E5; border:1px solid #3A3A3C;"
            "border-radius:6px; font-size:12px; }"
            "QPushButton:hover { background:#3A3A3C; }"
        )
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)
