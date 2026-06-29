"""
Main Application Window — TAU 360 Design
Sidebar: TAU branding, theme toggle, navigation.
Status bar: live 3-segment operation / kernel / HW info.
"""

from __future__ import annotations
import json
import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QPushButton, QLabel, QFrame,
    QStatusBar, QSizePolicy, QApplication, QScrollArea,
    QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QSize, QUrl, QSettings, QRectF, QEvent
from PyQt6.QtGui import QFont, QPixmap, QDesktopServices, QPainter

from ui.generator_widget   import GeneratorWidget
from ui.analyst_widget     import AnalystWidget
from ui.pe_widget          import PEWidget
from ui.synthesis_widget   import SynthesisWidget
from ui.memory_sim_widget  import MemorySimWidget
from core.app_logger       import AppLogger
from styles.dark_theme     import get_stylesheet

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Full product title (used in window bar and sidebar)
_TITLE_LONG = (
    "Area & Power Optimized Hardware Accelerator\n"
    "for Single Convolutional Kernel"
)
_WIN_TITLE  = (
    "Area & Power Optimized Hardware Accelerator "
    "for Single Convolutional Kernel  —  TAU EE"
)


class _LogoLabel(QLabel):
    """
    A QLabel that always paints its source pixmap scaled to fill its current
    width while preserving aspect ratio — using paintEvent directly.

    This avoids every layout/margin/DPR calculation: Qt gives the widget its
    allocated size, and we draw the pixmap to fill it exactly.  No clipping is
    possible because we never set a fixed QPixmap on the label.
    """

    def __init__(self, pix: QPixmap, parent=None):
        super().__init__(parent)
        self._src = pix
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("background: transparent;")

    # ── Layout hints ──────────────────────────────────────────────────────────

    def hasHeightForWidth(self) -> bool:
        return not self._src.isNull()

    def heightForWidth(self, w: int) -> int:
        if self._src.isNull() or self._src.width() == 0:
            return 0
        return round(w * self._src.height() / self._src.width())

    def sizeHint(self) -> QSize:
        w = max(self.width(), 40)
        return QSize(w, self.heightForWidth(w))

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 0)

    # ── Painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if self._src.isNull():
            super().paintEvent(event)
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        dpr = self.devicePixelRatioF()
        # Scale source to physical pixels, keeping aspect ratio
        scaled = self._src.scaled(
            QSize(round(w * dpr), round(h * dpr)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Logical size of the scaled pixmap
        lw = scaled.width()  / dpr
        lh = scaled.height() / dpr
        # Centre within the widget
        x = (w - lw) * 0.5
        y = (h - lh) * 0.5
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(
            QRectF(x, y, lw, lh),
            scaled,
            QRectF(0, 0, scaled.width(), scaled.height()),
        )


class _ResponsiveSidebar(QWidget):
    """
    Sidebar that rescales its registered buttons whenever the widget
    is resized, so all navigation and action buttons always fit inside
    the available vertical space without overflow or scrolling.

    Algorithm
    ---------
    1. Subtract the approximate height of all *fixed* content
       (logo block, nav header, separators, banner, footer) from the
       current sidebar height to get the space available for buttons.
    2. Divide evenly among the registered buttons, clamping each to
       [_BTN_MIN, _BTN_MAX] px.
    3. Derive a matching font size so text stays readable at every size.

    Fixed-content estimate (px):
        theme-toggle strip  42
        logo block         158
        nav section header  30
        4 × spacing (4 px)  16
        2 × separator (1 px) 2
        banner              46
        footer separator     1
        footer widget       98
        ─────────────────────
        total              393  →  _FIXED_H = 400  (with safety margin)
    """

    _FIXED_H  = 400
    _BTN_MIN  = 24    # px — compact but still tap-friendly
    _BTN_MAX  = 40    # px — comfortable on large displays

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dyn_btns: list[QPushButton] = []

    def register(self, btn: QPushButton) -> QPushButton:
        """Mark *btn* as dynamically sized.  Returns *btn* for chaining."""
        self._dyn_btns.append(btn)
        return btn

    # Called by Qt whenever the widget is resized (window resize, maximise …)
    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._refit()

    def _refit(self) -> None:
        n = len(self._dyn_btns)
        if n == 0:
            return

        avail   = max(n * self._BTN_MIN, self.height() - self._FIXED_H)
        per_btn = max(self._BTN_MIN, min(self._BTN_MAX, avail // n))

        # Font: 10 pt at ≤28 px, 11 pt at ≤34 px, 12 pt above
        if per_btn <= 28:
            fs = 10
        elif per_btn <= 34:
            fs = 11
        else:
            fs = 12

        for btn in self._dyn_btns:
            # setFixedHeight overrides QSS min/max-height at the C++ level
            btn.setFixedHeight(per_btn)
            f = QFont(btn.font())
            f.setPointSize(fs)
            btn.setFont(f)


class MainWindow(QMainWindow):

    APP_VERSION = "v1.0"
    WIN_SIZE    = (1600, 900)   # 16:9 default; overridden by showMaximized below

    def __init__(self):
        super().__init__()
        self._is_dark = True
        self._build_window()
        self.showMaximized()   # open full-screen on any 16:9 monitor

    # ══════════════════════════════════════════════════════════════════════════
    # Construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_window(self):
        self.setWindowTitle(_WIN_TITLE)
        self.resize(*self.WIN_SIZE)
        self.setMinimumSize(1060, 660)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_content(), stretch=1)

        self._build_status_bar()

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> _ResponsiveSidebar:
        sidebar = _ResponsiveSidebar()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(240)   # never grows or shrinks — prevents logo clip

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Theme toggle strip ──────────────────────────────────────────────
        toggle_strip = QFrame()
        toggle_strip.setStyleSheet("background: transparent;")
        ts_lay = QHBoxLayout(toggle_strip)
        ts_lay.setContentsMargins(14, 8, 14, 8)

        self._theme_btn = QPushButton("Dark Mode")
        self._theme_btn.setObjectName("theme_toggle")
        self._theme_btn.setCheckable(False)
        self._theme_btn.clicked.connect(self._toggle_theme)
        ts_lay.addStretch()
        ts_lay.addWidget(self._theme_btn)
        lay.addWidget(toggle_strip)

        # ── Logo / branding block ───────────────────────────────────────────
        logo_block = QFrame()
        logo_block.setObjectName("logo_block")
        logo_lay = QVBoxLayout(logo_block)
        logo_lay.setContentsMargins(10, 10, 10, 10)
        logo_lay.setSpacing(6)

        # TAU logo inside a white rounded frame (dark mode) / plain (light)
        self._logo_img_frame = QFrame()
        self._logo_img_frame.setObjectName("logo_img_frame")
        li_lay = QHBoxLayout(self._logo_img_frame)
        li_lay.setContentsMargins(8, 6, 8, 6)

        logo_path = os.path.join(_PKG_ROOT, "tau_logo.png")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path)
        else:
            pix = QPixmap()

        if not pix.isNull():
            # _LogoLabel draws the pixmap scaled to its own width via paintEvent —
            # no fixed QPixmap, no clipping, works at any container size.
            self._logo_lbl = _LogoLabel(pix)
        else:
            self._logo_lbl = QLabel("TAU")
            self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._logo_lbl.setStyleSheet("background: transparent;")

        li_lay.addWidget(self._logo_lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        logo_lay.addWidget(self._logo_img_frame)

        # Product accent tag
        accent_lbl = QLabel("ASIC VERIFICATION SUITE")
        accent_lbl.setObjectName("product_accent")
        accent_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        logo_lay.addWidget(accent_lbl)

        # Full product title — multiline
        title_lbl = QLabel(_TITLE_LONG)
        title_lbl.setObjectName("product_title")
        title_lbl.setWordWrap(True)
        logo_lay.addWidget(title_lbl)

        lay.addWidget(logo_block)
        self._apply_logo_frame()

        # ── Navigation ──────────────────────────────────────────────────────
        lay.addSpacing(4)

        nav_hdr = QLabel("  NAVIGATION")
        nav_hdr.setObjectName("nav_section_hdr")
        lay.addWidget(nav_hdr)

        self._nav_buttons: list[QPushButton] = []
        nav_items = [
            ("\u25a3   Generator Mode",
             "PRE-SIMULATION\nStimulus Generation & .hex Export", 0),
            ("\u25a3   Analyst Mode",
             "POST-SIMULATION\nChip Comparison & Metrics",        1),
            ("\u25a3   PE Stimulus",
             "PE UNIT-TEST\nProcessing Element Vector Generator", 2),
            ("\u25a3   Synthesis Reports",
             "SYNTHESIS\nArea / Power / Timing / QoR / Utilization", 3),
            ("\u25a3   Memory Simulation",
             "ARCHITECTURE\n9-Bank SRAM  \u00b7  Pixel Mapping  \u00b7  3\u00d73 Window", 4),
        ]
        for label, tip, idx in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("nav_btn")
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _, i=idx: self._switch_mode(i))
            lay.addWidget(btn)
            self._nav_buttons.append(btn)
            sidebar.register(btn)   # ← participates in responsive scaling

        lay.addSpacing(4)
        sep = QFrame()
        sep.setObjectName("nav_separator")
        sep.setFixedHeight(1)
        lay.addWidget(sep)
        lay.addSpacing(4)

        xfer_btn = QPushButton("\u2192   Send to Analyst")
        xfer_btn.setObjectName("nav_btn")
        xfer_btn.setToolTip("Transfer Generator golden output → Analyst reference")
        xfer_btn.clicked.connect(self._transfer_to_analyst)
        lay.addWidget(xfer_btn)
        sidebar.register(xfer_btn)

        clear_btn = QPushButton("\u2715   Clear")
        clear_btn.setObjectName("nav_btn_warn")
        clear_btn.setToolTip("Clear all loaded data in the current mode")
        clear_btn.clicked.connect(self._clear_current_widget)
        lay.addWidget(clear_btn)
        sidebar.register(clear_btn)

        lay.addSpacing(4)
        sep2 = QFrame()
        sep2.setObjectName("nav_separator")
        sep2.setFixedHeight(1)
        lay.addWidget(sep2)
        lay.addSpacing(4)

        save_btn = QPushButton("Save Session")
        save_btn.setObjectName("nav_btn")
        save_btn.setToolTip("Save current kernel + metrics to a JSON session file")
        save_btn.clicked.connect(self._save_session)
        lay.addWidget(save_btn)
        sidebar.register(save_btn)

        load_btn = QPushButton("Load Session")
        load_btn.setObjectName("nav_btn")
        load_btn.setToolTip("Restore a previously saved session file")
        load_btn.clicked.connect(self._load_session)
        lay.addWidget(load_btn)
        sidebar.register(load_btn)

        lay.addStretch()

        # ── TAU banner — bottom-left corner ────────────────────────────────
        banner_path = os.path.join(_PKG_ROOT, "banner logo.png")
        if os.path.exists(banner_path):
            banner_pix = QPixmap(banner_path)
            if not banner_pix.isNull():
                banner_pix = banner_pix.scaledToWidth(
                    210, Qt.TransformationMode.SmoothTransformation)
                banner_lbl = QLabel()
                banner_lbl.setPixmap(banner_pix)
                banner_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
                banner_lbl.setStyleSheet(
                    "background: transparent; padding: 6px 10px 4px 10px;")
                lay.addWidget(banner_lbl)

        # ── Credits footer ──────────────────────────────────────────────────
        foot_sep = QFrame()
        foot_sep.setFixedHeight(1)
        foot_sep.setObjectName("nav_separator")
        lay.addWidget(foot_sep)

        foot = QWidget()
        foot_lay = QVBoxLayout(foot)
        foot_lay.setContentsMargins(10, 6, 10, 8)
        foot_lay.setSpacing(2)

        credits = QLabel("Tel Aviv University\nElectrical Engineering")
        credits.setObjectName("credits_lbl")
        credits.setAlignment(Qt.AlignmentFlag.AlignLeft)
        credits.setWordWrap(True)
        credits.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        foot_lay.addWidget(credits)

        def _link_label(text: str, url: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("credits_link")
            lbl.setWordWrap(True)
            lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            def _open(_e, u=url):           # must return None (void C++ override)
                QDesktopServices.openUrl(QUrl(u))
            lbl.mousePressEvent = _open
            return lbl

        foot_lay.addWidget(_link_label(
            "Roy Friedman",
            "https://www.linkedin.com/in/roy-friedman-557aaa288",
        ))
        foot_lay.addWidget(_link_label(
            "Idan Marchevsky",
            "https://www.linkedin.com/in/idan-marchevsky-96b434359",
        ))

        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(0, 0, 0, 0)
        ver = QLabel(self.APP_VERSION)
        ver.setObjectName("version_label")
        ver_row.addWidget(ver)
        ver_row.addStretch()
        about_btn = QPushButton("About")
        about_btn.setObjectName("nav_btn")
        about_btn.setFixedHeight(22)
        about_btn.setFixedWidth(56)
        about_btn.clicked.connect(self._show_about)
        ver_row.addWidget(about_btn)
        foot_lay.addLayout(ver_row)

        lay.addWidget(foot)

        self._nav_buttons[0].setChecked(True)
        return sidebar

    # ── Content stack ─────────────────────────────────────────────────────────

    def _build_content(self) -> QStackedWidget:
        self._stack = QStackedWidget()
        self._generator  = GeneratorWidget()
        self._analyst    = AnalystWidget()
        self._pe         = PEWidget()
        self._synthesis  = SynthesisWidget()
        self._mem_sim    = MemorySimWidget()

        # Generator and PE get a QScrollArea wrapper; Analyst and Synthesis
        # manage their own internal scroll areas so the import bar stays fixed.
        for widget in (self._generator, self._pe):
            sa = QScrollArea()
            sa.setWidget(widget)
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            self._stack.addWidget(sa)

        # Analyst added directly — it owns its scroll area internally
        self._stack.insertWidget(1, self._analyst)

        # Synthesis Reports added directly
        self._stack.addWidget(self._synthesis)

        # Memory Simulation — manages its own scroll area
        self._stack.addWidget(self._mem_sim)

        self._stack.setCurrentIndex(0)

        # Connect signals → status bar
        self._generator.sig_status.connect(self._sb_set_op)
        self._generator.sig_kernel.connect(self._sb_set_kernel)
        self._generator.sig_frame.connect(self._sb_set_frame)
        self._analyst.sig_status.connect(self._sb_set_op)
        self._pe.sig_status.connect(self._sb_set_op)
        self._synthesis.sig_status.connect(self._sb_set_op)
        self._mem_sim.sig_status.connect(self._sb_set_op)
        # Keep Analyst always in sync with the current kernel configuration
        self._generator.sig_kernel_cfg.connect(self._analyst.update_kernel_cfg)
        # Sync Analyst frame display when Generator playback steps (live video mirror)
        self._generator.sig_video_step.connect(self._analyst.go_to_frame)

        return self._stack

    # ── Status bar ────────────────────────────────────────────────────────────

    def _build_status_bar(self):
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.setSizeGripEnabled(False)

        self._sb_op = QLabel("Ready")
        self._sb_op.setStyleSheet("color: #8A8A8E; font-size: 12px; padding: 0 10px;")
        sb.addWidget(self._sb_op, 1)

        self._sb_kernel = QLabel(
            "Kernel: IDENTITY  |  Bias: 0  |  Thr: 2000"
        )
        self._sb_kernel.setStyleSheet(
            "color: #6E6E73; font-size: 12px; padding: 0 14px;"
            "border-left: 1px solid #3A3A3C; border-right: 1px solid #3A3A3C;"
        )
        sb.addPermanentWidget(self._sb_kernel)

        hw_lbl = QLabel(
            "HW: 256\u00d7256  |  1 px/clk  |  20-bit ACC  |  3\u00d73 MAC  |  Valid: 254\u00d7254"
        )
        hw_lbl.setStyleSheet("color: #3A3A3C; font-size: 12px; padding: 0 10px;")
        sb.addPermanentWidget(hw_lbl)

    # ── Status bar update slots ───────────────────────────────────────────────

    def _sb_set_op(self, msg: str, color: str):
        self._sb_op.setText(msg)
        self._sb_op.setStyleSheet(
            f"color: {color}; font-size: 12px; padding: 0 10px;"
        )

    def _sb_set_kernel(self, s: str):
        self._sb_kernel.setText(s)

    def _sb_set_frame(self, cur: int, total: int):
        base = self._sb_kernel.text().split("  |  Frame")[0]
        self._sb_kernel.setText(f"{base}  |  Frame: {cur}/{total}")

    # ══════════════════════════════════════════════════════════════════════════
    # Theme switching
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_theme(self):
        self._is_dark = not self._is_dark
        app = QApplication.instance()
        app.setStyleSheet(get_stylesheet(self._is_dark))

        # Button text reflects next possible action
        self._theme_btn.setText(
            "Light Mode" if self._is_dark else "Dark Mode"
        )
        self._apply_logo_frame()

        # Notify widgets that have theme-sensitive inline styles
        self._mem_sim.update_theme(self._is_dark)

        # Update status-bar separators colour for visibility in both modes
        brd = "#3A3A3C" if self._is_dark else "#C8C8CC"
        self._sb_kernel.setStyleSheet(
            f"color: #6E6E73; font-size: 12px; "
            f"padding: 0 14px; border-left: 1px solid {brd}; border-right: 1px solid {brd};"
        )

    def _apply_logo_frame(self):
        """White rounded frame in dark mode; transparent in light mode.
        No CSS padding — li_lay already provides internal margins (8 px h, 6 px v).
        CSS padding would stack on top of the Python margins and clip the logo.
        """
        if self._is_dark:
            self._logo_img_frame.setStyleSheet(
                "QFrame#logo_img_frame {"
                "  background: #FFFFFF;"
                "  border-radius: 8px;"
                "}"
            )
        else:
            self._logo_img_frame.setStyleSheet(
                "QFrame#logo_img_frame {"
                "  background: transparent;"
                "  border: none;"
                "}"
            )

    # ══════════════════════════════════════════════════════════════════════════
    # Navigation
    # ══════════════════════════════════════════════════════════════════════════

    def _switch_mode(self, index: int):
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self._stack.setCurrentIndex(index)

    def _clear_current_widget(self):
        idx = self._stack.currentIndex()
        if idx == 0:
            self._generator._clear_all()
        elif idx == 1:
            self._analyst._clear_all()
        elif idx == 2:
            self._pe._clear_all()
        elif idx == 3:
            self._synthesis._clear_all()
        # idx == 4 is Memory Simulation — reset to cycle 0
        elif idx == 4:
            self._mem_sim._cyc_slider.setValue(0)

    def _transfer_to_analyst(self):
        config = self._generator.get_current_config()
        if config.get("golden") is None:
            self._sb_set_op("No golden output — run the model first.", "#FF453A")
            return
        self._analyst.load_from_generator(config)
        self._switch_mode(1)
        self._sb_set_op("Golden reference transferred to Analyst Mode.", "#34C759")

    # ══════════════════════════════════════════════════════════════════════════
    # About dialog
    # ══════════════════════════════════════════════════════════════════════════

    def _show_about(self):
        from ui.about_dialog import AboutDialog
        dlg = AboutDialog(self)
        dlg.exec()

    # ══════════════════════════════════════════════════════════════════════════
    # Session Save / Load
    # ══════════════════════════════════════════════════════════════════════════

    def _save_session(self):
        """Save current kernel + synthesis metrics to a JSON session file."""
        s = QSettings("TAU-EE", "ASIC-Suite")
        default_dir = s.value("session/last_dir", "") or ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Session", os.path.join(default_dir, "session.json"),
            "Session Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            gen_cfg = self._generator.get_current_config()
            weights = gen_cfg.get("weights")
            session = {
                "version": "1.0",
                "kernel": {
                    "weights":   weights.tolist() if hasattr(weights, "tolist") else weights,
                    "bias":      gen_cfg.get("bias",      0),
                    "threshold": gen_cfg.get("threshold", 2000),
                    "preset":    self._generator._active_preset,
                },
                "metrics": {},
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(session, f, indent=2)

            s.setValue("session/last_dir", os.path.dirname(path))



            self._sb_set_op(f"Session saved → {os.path.basename(path)}", "#34C759")
        except Exception as exc:
            QMessageBox.critical(self, "Session Save Error", str(exc))

    def _load_session(self):
        """Restore kernel + synthesis metrics from a JSON session file."""
        s = QSettings("TAU-EE", "ASIC-Suite")
        default_dir = s.value("session/last_dir", "") or ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Session", default_dir,
            "Session Files (*.json);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                session = json.load(f)
            # Apply kernel
            k = session.get("kernel", {})
            weights = k.get("weights")
            if weights and len(weights) == 3:
                for r in range(3):
                    for c in range(3):
                        self._generator._weight_boxes[r][c].blockSignals(True)
                        self._generator._weight_boxes[r][c].setValue(int(weights[r][c]))
                        self._generator._weight_boxes[r][c].blockSignals(False)
            bias = k.get("bias")
            if bias is not None:
                self._generator._bias_sb.blockSignals(True)
                self._generator._bias_sb.setValue(int(bias))
                self._generator._bias_sb.blockSignals(False)
            thr = k.get("threshold")
            if thr is not None:
                self._generator._thr_sb.blockSignals(True)
                self._generator._thr_sb.setValue(int(thr))
                self._generator._thr_sb.blockSignals(False)
            preset = k.get("preset")
            if preset:
                self._generator._active_preset = preset
            self._generator._emit_kernel_info()
            # metrics removed from session (now in Synthesis Reports tab)




            AppLogger.instance().ok(f"Session loaded ← {os.path.basename(path)}")
            self._sb_set_op(f"Session loaded ← {os.path.basename(path)}", "#34C759")
        except Exception as exc:
            QMessageBox.critical(self, "Session Load Error", str(exc))

    # ══════════════════════════════════════════════════════════════════════════
    # Clean shutdown
    # ══════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event):
        """Stop all background threads before the window closes."""
        # Generator threads
        for thread_attr, worker_attr in [
            ("_worker_thread",      "_worker"),
            ("_batch_thread",       "_batch_worker"),
            ("_video_load_thread",  "_video_load_worker"),
        ]:
            t = getattr(self._generator, thread_attr, None)
            if t is not None and t.isRunning():
                w = getattr(self._generator, worker_attr, None)
                if w is not None and hasattr(w, "cancel"):
                    w.cancel()
                t.quit()
                t.wait(400)

        # Analyst load thread
        t = getattr(self._analyst, "_load_thread", None)
        if t is not None and t.isRunning():
            w = getattr(self._analyst, "_load_worker", None)
            if w is not None and hasattr(w, "cancel"):
                w.cancel()
            t.quit()
            t.wait(400)

        # Stop animation threads in overlays
        for widget in (self._generator, self._analyst):
            overlay = getattr(widget, "_overlay", None)
            if overlay is not None:
                overlay.hide_loading()   # calls _stop_anim internally

        event.accept()
