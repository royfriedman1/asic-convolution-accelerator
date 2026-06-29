"""
Embedded Matplotlib power-consumption graph widget.
Supports:
  - CSV import (time_ns, power_mW)
  - Auto-simulation from bit-toggle activity
  - Animated playhead cursor synced to frame index
"""

from __future__ import annotations
import numpy as np

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as _FigureCanvasBase
from matplotlib.figure import Figure
from matplotlib.lines import Line2D


class FigureCanvas(_FigureCanvasBase):
    """FigureCanvas that does not consume scroll-wheel events.

    By default Matplotlib intercepts wheel events for zoom/pan, which
    prevents any parent QScrollArea from scrolling while the mouse is
    over the graph.  Forwarding them with ``event.ignore()`` lets Qt
    propagate the event up the widget tree as normal.
    """
    def wheelEvent(self, event):
        event.ignore()

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QSizePolicy
)
from PyQt6.QtCore import Qt


_BG   = "#08080f"
_AX   = "#0d0d1e"
_GRID = "#15153a"
_LINE = "#00d4ff"
_FILL = "#003060"
_CURSOR = "#ff4444"
_TEXT = "#5a7090"


class PowerGraph(QWidget):
    """Matplotlib canvas embedded in a PyQt6 widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._times: np.ndarray | None = None
        self._powers: np.ndarray | None = None
        self._cursor_line: Line2D | None = None
        self._bg_cache = None   # saved canvas background for blit
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # toolbar — two rows so labels and buttons never overlap
        toolbar_wrap = QVBoxLayout()
        toolbar_wrap.setSpacing(4)
        toolbar_wrap.setContentsMargins(0, 0, 0, 0)

        # row 1: title + hover readout + stats
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        title = QLabel("POWER CONSUMPTION")
        title.setObjectName("lbl_section")
        row1.addWidget(title)
        row1.addStretch()

        self._lbl_hover = QLabel("")
        self._lbl_hover.setObjectName("img_info")
        row1.addWidget(self._lbl_hover)

        self._lbl_peak = QLabel("Peak: —")
        self._lbl_peak.setObjectName("img_info")
        row1.addWidget(self._lbl_peak)

        self._lbl_avg = QLabel("Avg: —")
        self._lbl_avg.setObjectName("img_info")
        row1.addWidget(self._lbl_avg)

        def _mk_btn(label, obj, tip, slot):
            b = QPushButton(label)
            if obj:
                b.setObjectName(obj)
            if tip:
                b.setToolTip(tip)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(slot)
            return b

        # row 2: Load CSV | Simulate
        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(_mk_btn("Load CSV",  "btn_primary", "", self._load_csv))
        row2.addWidget(_mk_btn("Simulate",  "btn_warn",
                               "Generate simulated power trace from output activity",
                               self._simulate_power))

        # row 3: Export PNG | Clear
        row3 = QHBoxLayout()
        row3.setSpacing(6)
        row3.addWidget(_mk_btn("Export PNG", "btn_success",
                               "Save the current graph as a PNG image",
                               self._export_png))
        row3.addWidget(_mk_btn("Clear", "", "", self.clear))

        toolbar_wrap.addLayout(row1)
        toolbar_wrap.addLayout(row2)
        toolbar_wrap.addLayout(row3)
        layout.addLayout(toolbar_wrap)

        # Matplotlib figure
        self._fig = Figure(facecolor=_BG, tight_layout=True)
        self._ax = self._fig.add_subplot(111, facecolor=_AX)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._canvas)

        self._canvas.mpl_connect("motion_notify_event", self._on_graph_hover)
        self._canvas.mpl_connect("axes_leave_event",
                                 lambda _e: self._lbl_hover.setText(""))

        self._init_axes()

    def _init_axes(self):
        ax = self._ax
        ax.set_facecolor(_AX)
        ax.tick_params(colors=_TEXT, labelsize=9)
        ax.xaxis.label.set_color(_TEXT)
        ax.yaxis.label.set_color(_TEXT)
        ax.set_xlabel("Time (ns)", color=_TEXT, fontsize=9)
        ax.set_ylabel("Power (mW)", color=_TEXT, fontsize=9)
        ax.spines[:].set_color(_GRID)
        ax.grid(True, color=_GRID, linestyle="--", linewidth=0.5, alpha=0.7)
        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.text(
            0.5, 0.5, "Load CSV or click Simulate",
            transform=ax.transAxes,
            ha="center", va="center",
            color=_TEXT, fontsize=10, alpha=0.5,
        )
        self._canvas.draw()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_data(self, times: np.ndarray, powers: np.ndarray) -> None:
        """Plot a power trace.  times in ns, powers in mW."""
        self._times = np.asarray(times, dtype=float)
        self._powers = np.asarray(powers, dtype=float)
        self._redraw()

    def set_cursor(self, time_ns: float) -> None:
        """Move the vertical cursor to the given time (blit for speed)."""
        if self._cursor_line is None or self._times is None:
            return
        self._cursor_line.set_xdata([time_ns, time_ns])
        if self._bg_cache is not None:
            # Fast path: restore background, redraw only the cursor line, blit
            self._canvas.restore_region(self._bg_cache)
            self._ax.draw_artist(self._cursor_line)
            self._canvas.blit(self._ax.bbox)
        else:
            self._canvas.draw_idle()

    def clear(self) -> None:
        self._times = None
        self._powers = None
        self._cursor_line = None
        self._bg_cache = None
        self._ax.cla()
        self._init_axes()

    # ── Graph hover ───────────────────────────────────────────────────────────

    def _on_graph_hover(self, event):
        if event.inaxes and self._times is not None and self._powers is not None:
            idx = int(np.argmin(np.abs(self._times - event.xdata)))
            t = self._times[idx]
            p = self._powers[idx]
            self._lbl_hover.setText(f"t: {t:.1f} ns   P: {p:.2f} mW")
        else:
            self._lbl_hover.setText("")

    # ── CSV loading ───────────────────────────────────────────────────────────

    def _export_png(self) -> None:
        """Save the current figure as a PNG file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Power Graph", "power_graph.png",
            "PNG Image (*.png);;All Files (*)"
        )
        if not path:
            return
        try:
            self._fig.savefig(path, dpi=150, bbox_inches="tight",
                              facecolor=_BG)
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Export Error", str(exc))

    def _load_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Power CSV", "",
            "CSV Files (*.csv);;Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            data = np.loadtxt(path, delimiter=",", comments="#", skiprows=1)
            if data.ndim == 1:
                data = data.reshape(1, -1)
            self.set_data(data[:, 0], data[:, 1])
        except Exception as exc:
            self._ax.set_title(f"Load error: {exc}", color="#ff4444", fontsize=9)
            self._canvas.draw()

    # ── Simulation ────────────────────────────────────────────────────────────

    def simulate_from_activity(self, output_map: np.ndarray) -> None:
        """
        Estimate a power trace from binary output activity.
        Models: P(t) = P_static + P_dynamic * activity_rate(t)
        """
        bits = output_map.flatten().astype(float)
        n = len(bits)
        # clock period = 1 ns (1 GHz), scan-out happens pixel-by-pixel
        window = max(1, n // 256)
        activity = np.convolve(bits, np.ones(window) / window, mode="same")

        P_static = 12.0   # mW
        P_dynamic = 28.0  # mW peak
        powers = P_static + P_dynamic * activity
        # add mild thermal noise
        powers += np.random.normal(0, 0.3, powers.shape)
        times = np.arange(n, dtype=float)   # 1 ns per pixel

        self.set_data(times, powers)

    def _simulate_power(self):
        """Simulate a demonstration power trace."""
        n = 256 * 256
        t = np.linspace(0, n, n)
        # Simulate burst activity with idle periods
        P_static = 12.0
        P_dynamic = np.zeros(n)
        # Bursts every 4096 pixels
        for start in range(0, n, 4096):
            end = min(start + 2048, n)
            P_dynamic[start:end] = 25.0 * np.random.rand(end - start)
        powers = P_static + P_dynamic + np.random.normal(0, 0.5, n)
        self.set_data(t, powers)

    # ── Redraw ────────────────────────────────────────────────────────────────

    def _redraw(self):
        ax = self._ax
        ax.cla()
        ax.set_facecolor(_AX)

        t = self._times
        p = self._powers

        ax.fill_between(t, p, alpha=0.15, color=_FILL)
        ax.plot(t, p, color=_LINE, linewidth=0.9, alpha=0.9)

        # cursor
        y_max = float(np.max(p)) * 1.15
        self._cursor_line = ax.axvline(x=t[0], color=_CURSOR, linewidth=1.2, linestyle="--", alpha=0.8)

        ax.set_xlim(t[0], t[-1])
        ax.set_ylim(0, y_max)
        ax.set_xlabel("Time (ns)", color=_TEXT, fontsize=9)
        ax.set_ylabel("Power (mW)", color=_TEXT, fontsize=9)
        ax.tick_params(colors=_TEXT, labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID)
        ax.grid(True, color=_GRID, linestyle="--", linewidth=0.5, alpha=0.7)

        peak = float(np.max(p))
        avg = float(np.mean(p))
        self._lbl_peak.setText(f"Peak: {peak:.1f} mW")
        self._lbl_avg.setText(f"Avg:  {avg:.1f} mW")

        self._canvas.draw()
        # Cache the background (cursor excluded) for fast blit updates
        self._cursor_line.set_visible(False)
        self._canvas.draw()
        self._bg_cache = self._canvas.copy_from_bbox(self._ax.bbox)
        self._cursor_line.set_visible(True)
        self._canvas.draw_idle()
