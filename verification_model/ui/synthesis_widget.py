"""
Synthesis Reports Viewer
Select a synthesis output folder; files are auto-discovered by name pattern.
Displays parsed data in tabs with matplotlib charts and a textual analysis.
"""

from __future__ import annotations
import re
import os
from typing import Optional

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as _FigureCanvasBase
from matplotlib.figure import Figure

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QGroupBox, QGridLayout, QTableWidget, QTableWidgetItem,
    QFrame, QFileDialog, QHeaderView, QSizePolicy, QScrollArea,
    QTextEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont


# ─── Matplotlib canvas (no wheel-event capture) ───────────────────────────────

class _Canvas(_FigureCanvasBase):
    def wheelEvent(self, e):
        e.ignore()


# ─── Chart colour palette ─────────────────────────────────────────────────────

_BG    = "#1A1A1B"
_AX    = "#222224"
_GRID  = "#2C2C2E"
_TEXT  = "#8A8A8E"
_CYAN  = "#00ADEF"
_GREEN = "#34C759"
_AMBER = "#FF9F0A"
_RED   = "#FF453A"
_PIE   = ["#00ADEF", "#34C759", "#FF9F0A", "#AF52DE", "#FF453A",
          "#5AC8FA", "#30D158", "#FFD60A"]


# ─── Tiny helpers ─────────────────────────────────────────────────────────────

def _first(pattern: str, text: str, default: str = "—") -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else default


def _table_item(text: str, align=Qt.AlignmentFlag.AlignCenter) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text))
    it.setTextAlignment(align)
    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return it


def _make_fig(nrows=1, ncols=1, figsize=(6, 3.5)):
    fig = Figure(figsize=figsize, facecolor=_BG, tight_layout=True)
    axes = []
    for i in range(nrows * ncols):
        ax = fig.add_subplot(nrows, ncols, i + 1)
        ax.set_facecolor(_AX)
        ax.tick_params(colors=_TEXT, labelsize=8)
        ax.xaxis.label.set_color(_TEXT)
        ax.yaxis.label.set_color(_TEXT)
        for spine in ax.spines.values():
            spine.set_edgecolor(_GRID)
        ax.grid(True, color=_GRID, linestyle="--", linewidth=0.5, alpha=0.6)
        axes.append(ax)
    return fig, (axes[0] if len(axes) == 1 else axes)


def _canvas_widget(fig) -> QWidget:
    c = _Canvas(fig)
    c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(c)
    return w


def _metric_card(label: str, value: str, unit: str = "",
                 ok: Optional[bool] = None) -> QFrame:
    card = QFrame()
    card.setObjectName("synth_card")
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if ok is True:
        card.setProperty("card_state", "ok")
    elif ok is False:
        card.setProperty("card_state", "warn")
    else:
        card.setProperty("card_state", "neutral")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(2)
    lbl = QLabel(label)
    lbl.setObjectName("synth_card_label")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(lbl)
    val_row = QHBoxLayout()
    val_row.setContentsMargins(0, 0, 0, 0)
    val_row.setSpacing(4)
    vl = QLabel(value)
    vl.setObjectName("synth_card_value")
    vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val_row.addStretch()
    val_row.addWidget(vl)
    if unit:
        ul = QLabel(unit)
        ul.setObjectName("synth_card_unit")
        val_row.addWidget(ul)
    val_row.addStretch()
    lay.addLayout(val_row)
    return card


def _section_hdr(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setObjectName("synth_section_hdr")
    return lbl


# ─── Report parsers ───────────────────────────────────────────────────────────

class _AreaData:
    def __init__(self, text: str):
        self.design      = _first(r"Design\s*:\s*(\S+)", text)
        self.version     = _first(r"Version:\s*(.+)", text)
        self.date        = _first(r"Date\s*:\s*(.+)", text)
        self.ports       = _first(r"Number of ports:\s+(\d+)", text)
        self.nets        = _first(r"Number of nets:\s+(\d+)", text)
        self.cells       = _first(r"Number of cells:\s+(\d+)", text)
        self.comb_cells  = _first(r"Number of combinational cells:\s+(\d+)", text)
        self.seq_cells   = _first(r"Number of sequential cells:\s+(\d+)", text)
        self.bufinv      = _first(r"Number of buf/inv:\s+(\d+)", text)
        self.comb_area   = _first(r"Combinational area:\s+([\d.]+)", text)
        self.bufinv_area = _first(r"Buf/Inv area:\s+([\d.]+)", text)
        self.noncomb_area= _first(r"Noncombinational area:\s+([\d.]+)", text)
        self.total_area  = _first(r"Total cell area:\s+([\d.]+)", text)
        self.hier_rows: list[tuple] = []
        in_tbl = False
        for line in text.splitlines():
            if re.match(r"^-{10,}", line):
                in_tbl = True
                continue
            if in_tbl and re.match(r"^Total\s", line):
                in_tbl = False
                continue
            if in_tbl and line.strip():
                parts = line.split()
                if len(parts) >= 6:
                    self.hier_rows.append((parts[0], parts[1],
                                           parts[2] + "%", parts[3],
                                           parts[4], parts[5] if len(parts) > 5 else "0.00"))


class _PowerData:
    def __init__(self, text: str):
        self.design      = _first(r"Design\s*:\s*(\S+)", text)
        self.scenario    = _first(r"Scenario:\s+(\S+)", text)
        self.voltage     = _first(r"Voltage:\s+([\d.]+)", text)
        self.temperature = _first(r"Temperature:\s+([\d.]+)", text)
        self.internal_nw = _first(r"Cell Internal Power\s*=\s*([\d.e+]+)\s*nW", text)
        self.switching_nw= _first(r"Net Switching Power\s*=\s*([\d.e+]+)\s*nW", text)
        self.dynamic_nw  = _first(r"Total Dynamic Power\s*=\s*([\d.e+]+)\s*nW", text)
        self.leakage_nw  = _first(r"Cell Leakage Power\s*=\s*([\d.e+]+)\s*nW", text)
        self.internal    = _first(r"Cell Internal Power\s*=\s*([\d.e+]+\s*\S+)\s*\(", text)
        self.switching   = _first(r"Net Switching Power\s*=\s*([\d.e+]+\s*\S+)\s*\(", text)
        self.dynamic     = _first(r"Total Dynamic Power\s*=\s*([\d.e+]+\s*\S+)", text)
        self.leakage     = _first(r"Cell Leakage Power\s*=\s*([\d.e+]+\s*\S+)", text)
        self.groups: list[tuple] = []
        in_tbl = False
        for line in text.splitlines():
            if line.startswith("Power Group"):
                in_tbl = True
                continue
            if in_tbl and re.match(r"^-{10,}", line):
                continue
            if in_tbl and line.strip().startswith("Total"):
                in_tbl = False
                continue
            if in_tbl and line.strip():
                parts = line.split()
                if len(parts) >= 5:
                    self.groups.append((parts[0], parts[1], parts[2], parts[3], parts[4],
                                        parts[5] if len(parts) > 5 else ""))


class _TimingData:
    def __init__(self, text: str):
        self.design     = _first(r"Design\s*:\s*(\S+)", text)
        self.startpoint = _first(r"Startpoint:\s+(.+)", text)
        self.endpoint   = _first(r"Endpoint:\s+(.+)", text)
        self.scenario   = _first(r"Scenario:\s+(\S+)", text)
        self.corner     = _first(r"Corner:\s+(\S+)", text)
        self.path_group = _first(r"Path Group:\s+(\S+)", text)
        self.clk_period = _first(r"clock clk.*?(\d+\.\d+)\s*$", text, "—")
        self.arrival    = _first(r"data arrival time\s+([\d.]+)", text)
        self.required   = _first(r"data required time\s+([\d.]+)", text)
        sm = re.search(r"slack\s+\((MET|VIOLATED)\)\s+([\d.]+)", text)
        if sm:
            self.slack_status = sm.group(1)
            self.slack        = sm.group(2)
        else:
            self.slack_status = "—"
            self.slack        = "—"
        self.path_steps: list[tuple] = []
        in_path = False
        seen_clk = 0
        for line in text.splitlines():
            if re.match(r"\s*Point\s+Incr\s+Path", line):
                in_path = True
                continue
            if in_path and re.match(r"\s*-{10,}", line):
                continue
            if in_path and re.search(r"clock clk \(rise edge\)", line):
                seen_clk += 1
                if seen_clk >= 2:
                    in_path = False
                    continue
            if in_path and line.strip():
                m = re.match(r"^\s*(.+?)\s{2,}([\d.]+)\s+([\d.]+)\s*([rf]?)\s*$", line)
                if m:
                    self.path_steps.append((m.group(1).strip(), m.group(2), m.group(3)))


class _QorData:
    def __init__(self, text: str):
        self.design = _first(r"Design\s*:\s*(\S+)", text)
        self.scenarios: list[dict] = []
        blocks = re.split(r"\n(?=Scenario\s)", text)
        for block in blocks:
            if not block.startswith("Scenario"):
                continue
            sc = {
                "scenario":   _first(r"Scenario\s+'([^']+)'", block),
                "group":      _first(r"Timing Path Group\s+'([^']+)'", block),
                "levels":     _first(r"Levels of Logic:\s+([\d.]+)", block),
                "crit_len":   _first(r"Critical Path Length:\s+([\d.]+)", block),
                "crit_slack": _first(r"Critical Path Slack:\s+([\d.]+)", block),
                "clk_period": _first(r"Critical Path Clk Period:\s+([\d.]+)", block),
                "tns":        _first(r"Total Negative Slack:\s+([\d.]+)", block),
                "viol_paths": _first(r"No\. of Violating Paths:\s+([\d.]+)", block),
                "worst_hold": _first(r"Worst Hold Violation:\s+([-\d.]+)", block, ""),
                "total_hold": _first(r"Total Hold Violation:\s+([-\d.]+)", block, ""),
                "hold_viols": _first(r"No\. of Hold Violations:\s+([\d.]+)", block, ""),
            }
            self.scenarios.append(sc)
        self.leaf_cells   = _first(r"Leaf Cell Count:\s+(\d+)", text)
        self.comb_cells   = _first(r"Combinational Cell Count:\s+(\d+)", text)
        self.seq_cells    = _first(r"Sequential Cell Count:\s+(\d+)", text)
        self.icg_cells    = _first(r"Integrated Clock-Gating Cell Count:\s+(\d+)", text)
        self.bufinv_cnt   = _first(r"Buf/Inv Cell Count:\s+(\d+)", text)
        self.comb_area    = _first(r"Combinational Area:\s+([\d.]+)", text)
        self.noncomb_area = _first(r"Noncombinational Area:\s+([\d.]+)", text)
        self.total_area   = _first(r"Cell Area \(netlist\):\s+([\d.]+)", text)
        self.total_nets   = _first(r"Total Number of Nets:\s+(\d+)", text)
        self.nets_viols   = _first(r"Nets with Violations:\s+(\d+)", text)
        self.max_cap      = _first(r"Max Cap Violations:\s+(\d+)", text)
        self.max_trans    = _first(r"Max Trans Violations:\s+(\d+)", text)


class _UtilData:
    def __init__(self, text: str):
        self.design    = _first(r"Design\s*:\s*(\S+)", text)
        self.ratio     = _first(r"Utilization Ratio:\s+([\d.]+)", text)
        self.total_area= _first(r"Total Area:\s+([\d.]+)", text)
        self.cap_area  = _first(r"Total Capacity Area:\s+([\d.]+)", text)
        self.cell_area = _first(r"Total Area of cells:\s+([\d.]+)", text)
        try:
            self.ratio_pct = f"{float(self.ratio)*100:.1f}%"
            self.ratio_f   = float(self.ratio)
        except Exception:
            self.ratio_pct = "—"
            self.ratio_f   = 0.0


# ─── Chart pages ──────────────────────────────────────────────────────────────

class _PowerChartsPage(QWidget):
    def __init__(self, data: _PowerData):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(_section_hdr("Summary"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_metric_card("Internal Power",   data.internal))
        row.addWidget(_metric_card("Switching Power",  data.switching))
        row.addWidget(_metric_card("Total Dynamic",    data.dynamic))
        row.addWidget(_metric_card("Leakage Power",    data.leakage))
        row.addWidget(_metric_card("Voltage",          data.voltage, "V"))
        row.addWidget(_metric_card("Temperature",      data.temperature, "°C"))
        root.addLayout(row)

        # ── Charts row ────────────────────────────────────────────────────────
        charts_row = QHBoxLayout()
        charts_row.setSpacing(10)

        # Pie chart — power group breakdown
        if data.groups:
            fig_pie, ax_pie = _make_fig(figsize=(5, 4))
            names, totals = [], []
            for g in data.groups:
                try:
                    val = float(g[4])
                    if val > 0:
                        names.append(g[0])
                        totals.append(val)
                except Exception:
                    pass
            if totals:
                wedges, texts, autotexts = ax_pie.pie(
                    totals, labels=None, autopct="%1.1f%%",
                    colors=_PIE[:len(totals)],
                    startangle=90,
                    wedgeprops={"edgecolor": _BG, "linewidth": 1.5},
                    textprops={"color": _TEXT, "fontsize": 7},
                )
                for at in autotexts:
                    at.set_color("#FFFFFF")
                    at.set_fontsize(8)
                ax_pie.legend(
                    wedges, names,
                    loc="lower center", bbox_to_anchor=(0.5, -0.22),
                    ncol=2, fontsize=7,
                    labelcolor=_TEXT, facecolor=_AX, edgecolor=_GRID,
                )
                ax_pie.set_title("Power Group Breakdown", color=_CYAN,
                                 fontsize=10, fontweight="bold", pad=8)
                charts_row.addWidget(_canvas_widget(fig_pie), stretch=4)

        # Bar chart — internal vs switching vs leakage
        try:
            int_val = float(data.internal_nw)
            sw_val  = float(data.switching_nw)
            lk_val  = float(data.leakage_nw)
            fig_bar, ax_bar = _make_fig(figsize=(5, 4))
            labels = ["Internal", "Switching", "Leakage"]
            values = [int_val, sw_val, lk_val]
            colors = [_CYAN, _GREEN, _AMBER]
            bars = ax_bar.barh(labels, values, color=colors,
                               edgecolor=_BG, linewidth=0.8, height=0.5)
            ax_bar.set_xlabel("Power (nW)", color=_TEXT, fontsize=9)
            ax_bar.set_title("Power Component Breakdown", color=_CYAN,
                             fontsize=10, fontweight="bold", pad=8)
            ax_bar.tick_params(colors=_TEXT, labelsize=9)
            for bar, val in zip(bars, values):
                ax_bar.text(val * 1.01, bar.get_y() + bar.get_height() / 2,
                            f"{val:.2e}", va="center", ha="left",
                            color=_TEXT, fontsize=7)
            charts_row.addWidget(_canvas_widget(fig_bar), stretch=4)
        except Exception:
            pass

        root.addLayout(charts_row)

        # Groups table
        root.addWidget(_section_hdr("Power Groups Table"))
        tbl = QTableWidget()
        tbl.setColumnCount(5)
        tbl.setHorizontalHeaderLabels(["Group", "Internal (nW)", "Switching (nW)",
                                        "Leakage (nW)", "Total (nW)"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(1, 5):
            tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.setRowCount(len(data.groups))
        for r, g in enumerate(data.groups):
            tbl.setItem(r, 0, _table_item(g[0], Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
            for c in range(1, 5):
                tbl.setItem(r, c, _table_item(g[c] if c < len(g) else "—"))
        root.addWidget(tbl)
        root.addStretch()


class _AreaChartsPage(QWidget):
    def __init__(self, data: _AreaData):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(_section_hdr("Area Summary"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_metric_card("Total Cell Area",      data.total_area,   "μm²"))
        row.addWidget(_metric_card("Combinational Area",   data.comb_area,    "μm²"))
        row.addWidget(_metric_card("Noncombinational Area",data.noncomb_area, "μm²"))
        row.addWidget(_metric_card("Buf/Inv Area",         data.bufinv_area,  "μm²"))
        root.addLayout(row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(_metric_card("Ports",       data.ports))
        row2.addWidget(_metric_card("Nets",        data.nets))
        row2.addWidget(_metric_card("Total Cells", data.cells))
        row2.addWidget(_metric_card("Comb. Cells", data.comb_cells))
        row2.addWidget(_metric_card("Seq. Cells",  data.seq_cells))
        row2.addWidget(_metric_card("Buf/Inv",     data.bufinv))
        root.addLayout(row2)

        # Stacked bar: combinational vs noncombinational vs bufinv
        try:
            ca = float(data.comb_area)
            na = float(data.noncomb_area)
            ba = float(data.bufinv_area)
            fig, ax = _make_fig(figsize=(8, 2.8))
            categories = ["Cell Area"]
            b1 = ax.barh(categories, [ca], color=_CYAN,   label="Combinational",    height=0.4)
            b2 = ax.barh(categories, [na], left=[ca],     color=_GREEN, label="Noncombinational", height=0.4)
            b3 = ax.barh(categories, [ba], left=[ca + na], color=_AMBER, label="Buf/Inv",         height=0.4)
            ax.set_xlabel("Area (μm²)", color=_TEXT, fontsize=9)
            ax.set_title("Area Composition", color=_CYAN, fontsize=10, fontweight="bold")
            ax.legend(loc="lower right", fontsize=8, labelcolor=_TEXT,
                      facecolor=_AX, edgecolor=_GRID)
            ax.tick_params(colors=_TEXT, labelsize=9)
            root.addWidget(_canvas_widget(fig))
        except Exception:
            pass

        # Hierarchical bar chart
        if data.hier_rows:
            root.addWidget(_section_hdr("Hierarchical Area Distribution"))
            try:
                names  = [r[0] for r in data.hier_rows]
                totals = [float(r[1]) for r in data.hier_rows]
                fig2, ax2 = _make_fig(figsize=(8, max(2.5, len(names) * 0.9)))
                y = np.arange(len(names))
                bars = ax2.barh(y, totals, color=_CYAN, edgecolor=_BG,
                                linewidth=0.8, height=0.6)
                ax2.set_yticks(y)
                ax2.set_yticklabels(names, fontsize=8, color=_TEXT)
                ax2.set_xlabel("Absolute Total (μm²)", color=_TEXT, fontsize=9)
                ax2.set_title("Hierarchical Area", color=_CYAN, fontsize=10, fontweight="bold")
                ax2.tick_params(colors=_TEXT, labelsize=8)
                for bar, val in zip(bars, totals):
                    ax2.text(val + max(totals) * 0.01,
                             bar.get_y() + bar.get_height() / 2,
                             f"{val:,.1f}", va="center", ha="left",
                             color=_TEXT, fontsize=7)
                root.addWidget(_canvas_widget(fig2))
            except Exception:
                tbl = QTableWidget()
                tbl.setColumnCount(6)
                tbl.setHorizontalHeaderLabels(["Cell", "Absolute", "%",
                                               "Comb", "Noncomb", "Boxes"])
                tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
                for c in range(1, 6):
                    tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
                tbl.verticalHeader().setVisible(False)
                tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
                tbl.setAlternatingRowColors(True)
                tbl.setRowCount(len(data.hier_rows))
                for r, row in enumerate(data.hier_rows):
                    for c, v in enumerate(row):
                        tbl.setItem(r, c, _table_item(v, Qt.AlignmentFlag.AlignLeft
                                    if c == 0 else Qt.AlignmentFlag.AlignCenter))
                root.addWidget(tbl)

        root.addStretch()


class _TimingChartsPage(QWidget):
    def __init__(self, data: _TimingData):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        is_met = data.slack_status == "MET"
        root.addWidget(_section_hdr("Critical Path Summary"))
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_metric_card("Status",       data.slack_status, ok=is_met))
        row.addWidget(_metric_card("Slack",        data.slack, "ns", ok=is_met))
        row.addWidget(_metric_card("Data Arrival", data.arrival, "ns"))
        row.addWidget(_metric_card("Data Required",data.required, "ns"))
        row.addWidget(_metric_card("Scenario",     data.scenario))
        row.addWidget(_metric_card("Corner",       data.corner))
        root.addLayout(row)

        # Waterfall chart: critical path steps
        if data.path_steps:
            try:
                fig, ax = _make_fig(figsize=(9, max(3, len(data.path_steps) * 0.35)))
                labels = [s[0][-40:] for s in data.path_steps]
                incrs  = [float(s[1]) for s in data.path_steps]
                paths  = [float(s[2]) for s in data.path_steps]
                y = np.arange(len(labels))
                bars = ax.barh(y, incrs, color=_CYAN, edgecolor=_BG,
                               linewidth=0.6, height=0.65, left=[p - i for p, i in zip(paths, incrs)])
                ax.set_yticks(y)
                ax.set_yticklabels(labels, fontsize=6.5, color=_TEXT)
                ax.set_xlabel("Path Delay (ns)", color=_TEXT, fontsize=9)
                ax.set_title("Critical Path Waterfall", color=_CYAN, fontsize=10, fontweight="bold")
                ax.tick_params(colors=_TEXT, labelsize=8)
                # Mark total arrival with vertical line
                if paths:
                    ax.axvline(x=float(data.arrival) if data.arrival != "—" else paths[-1],
                               color=_RED, linewidth=1.2, linestyle="--", alpha=0.8,
                               label=f"Arrival = {data.arrival} ns")
                    if data.required != "—":
                        ax.axvline(x=float(data.required), color=_GREEN,
                                   linewidth=1.2, linestyle="--", alpha=0.8,
                                   label=f"Required = {data.required} ns")
                    ax.legend(fontsize=8, labelcolor=_TEXT, facecolor=_AX, edgecolor=_GRID)
                root.addWidget(_canvas_widget(fig))
            except Exception:
                pass

        # Endpoints
        root.addWidget(_section_hdr("Path Endpoints"))
        ep_box = QGroupBox()
        ep_box.setObjectName("synth_group")
        ep_lay = QGridLayout(ep_box)
        ep_lay.setColumnStretch(1, 1)
        for i, (lbl_text, val) in enumerate([
            ("Startpoint:", data.startpoint),
            ("Endpoint:",   data.endpoint),
            ("Path Group:", data.path_group),
        ]):
            ll = QLabel(lbl_text)
            vl = QLabel(val)
            vl.setWordWrap(True)
            vl.setObjectName("synth_mono")
            ep_lay.addWidget(ll, i, 0)
            ep_lay.addWidget(vl, i, 1)
        root.addWidget(ep_box)

        # Path steps table
        if data.path_steps:
            root.addWidget(_section_hdr("Critical Path Trace"))
            tbl = QTableWidget()
            tbl.setColumnCount(3)
            tbl.setHorizontalHeaderLabels(["Point", "Incr (ns)", "Path (ns)"])
            tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            for c in range(1, 3):
                tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            tbl.setAlternatingRowColors(True)
            tbl.setRowCount(len(data.path_steps))
            for r, (pt, inc, pth) in enumerate(data.path_steps):
                tbl.setItem(r, 0, _table_item(pt, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
                tbl.setItem(r, 1, _table_item(inc))
                tbl.setItem(r, 2, _table_item(pth))
            root.addWidget(tbl)

        root.addStretch()


class _QorChartsPage(QWidget):
    def __init__(self, data: _QorData):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ── Timing slack bar chart ────────────────────────────────────────────
        if data.scenarios:
            root.addWidget(_section_hdr("Timing Slack per Scenario / Group"))
            try:
                names  = [f"{s['scenario']}\n{s['group']}" for s in data.scenarios]
                slacks = [float(s["crit_slack"]) for s in data.scenarios]
                colors = [_GREEN if v >= 0 else _RED for v in slacks]
                fig, ax = _make_fig(figsize=(9, max(3, len(names) * 0.7)))
                y = np.arange(len(names))
                ax.barh(y, slacks, color=colors, edgecolor=_BG, linewidth=0.7, height=0.6)
                ax.axvline(0, color=_TEXT, linewidth=0.8, linestyle="--", alpha=0.6)
                ax.set_yticks(y)
                ax.set_yticklabels(names, fontsize=8, color=_TEXT)
                ax.set_xlabel("Critical Path Slack (ns)", color=_TEXT, fontsize=9)
                ax.set_title("Timing Slack by Group", color=_CYAN, fontsize=10, fontweight="bold")
                ax.tick_params(colors=_TEXT, labelsize=8)
                root.addWidget(_canvas_widget(fig))
            except Exception:
                pass

        # ── Cell count donut ──────────────────────────────────────────────────
        try:
            comb = float(data.comb_cells)
            seq  = float(data.seq_cells)
            icg  = float(data.icg_cells)
            buf  = float(data.bufinv_cnt)
            others = max(0, float(data.leaf_cells) - comb - seq)
            vals = [v for v in [comb, seq - icg, icg, buf, others] if v > 0]
            lbls = [l for l, v in zip(
                ["Combinational", "Sequential", "ICG", "Buf/Inv", "Other"], vals
            ) if v > 0]
            fig2, ax2 = _make_fig(figsize=(5, 4))
            wedges, texts, autotexts = ax2.pie(
                vals, labels=None, autopct="%1.1f%%",
                colors=_PIE[:len(vals)],
                startangle=90,
                wedgeprops={"edgecolor": _BG, "linewidth": 1.5, "width": 0.55},
                textprops={"color": _TEXT, "fontsize": 8},
            )
            for at in autotexts:
                at.set_color("#FFFFFF")
                at.set_fontsize(8)
            ax2.legend(wedges, lbls, loc="lower center", bbox_to_anchor=(0.5, -0.22),
                       ncol=2, fontsize=7, labelcolor=_TEXT,
                       facecolor=_AX, edgecolor=_GRID)
            ax2.set_title("Cell Type Distribution", color=_CYAN, fontsize=10, fontweight="bold")
            root.addWidget(_canvas_widget(fig2))
        except Exception:
            pass

        # ── Scenarios table ───────────────────────────────────────────────────
        root.addWidget(_section_hdr("Timing Scenarios"))
        cols = ["Scenario", "Group", "Levels", "Crit. Len (ns)", "Crit. Slack (ns)",
                "Clk Period (ns)", "TNS", "Viol. Paths", "Worst Hold", "Hold Viols"]
        tbl = QTableWidget()
        tbl.setColumnCount(len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        for c in range(2):
            tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(2, len(cols)):
            tbl.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.setRowCount(len(data.scenarios))
        for r, sc in enumerate(data.scenarios):
            vals = [sc["scenario"], sc["group"], sc["levels"], sc["crit_len"],
                    sc["crit_slack"], sc["clk_period"], sc["tns"], sc["viol_paths"],
                    sc["worst_hold"] or "—", sc["hold_viols"] or "—"]
            for c, v in enumerate(vals):
                align = (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                         if c <= 1 else Qt.AlignmentFlag.AlignCenter)
                item = _table_item(v, align)
                if c == 7 and v not in ("—", "0"):
                    item.setForeground(QColor(_RED))
                if c == 6 and v not in ("—", "0.00", "0"):
                    item.setForeground(QColor(_RED))
                tbl.setItem(r, c, item)
        root.addWidget(tbl)

        # ── Cell counts ───────────────────────────────────────────────────────
        root.addWidget(_section_hdr("Cell Counts & Design Rules"))
        cnt_row = QHBoxLayout()
        cnt_row.setSpacing(8)
        cnt_row.addWidget(_metric_card("Leaf Cells",    data.leaf_cells))
        cnt_row.addWidget(_metric_card("Combinational", data.comb_cells))
        cnt_row.addWidget(_metric_card("Sequential",    data.seq_cells))
        cnt_row.addWidget(_metric_card("ICG",           data.icg_cells))
        cnt_row.addWidget(_metric_card("Buf/Inv",       data.bufinv_cnt))
        cnt_row.addWidget(_metric_card("Nets w/ Viols", data.nets_viols,
                                       ok=data.nets_viols == "0"))
        cnt_row.addWidget(_metric_card("Max Cap Viols", data.max_cap,
                                       ok=data.max_cap == "0"))
        root.addLayout(cnt_row)
        root.addStretch()


class _UtilChartsPage(QWidget):
    def __init__(self, data: _UtilData):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(_section_hdr("Utilization Summary"))
        util_ok = data.ratio_f < 0.85
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(_metric_card("Utilization", data.ratio_pct, ok=util_ok))
        row.addWidget(_metric_card("Cell Area",   data.cell_area, "μm²"))
        row.addWidget(_metric_card("Capacity Area",data.cap_area, "μm²"))
        row.addWidget(_metric_card("Total Area",  data.total_area,"μm²"))
        root.addLayout(row)

        # Gauge (donut)
        try:
            r = data.ratio_f
            fill_color = _GREEN if r < 0.85 else (_AMBER if r < 0.95 else _RED)
            fig, ax = _make_fig(figsize=(5, 4))
            ax.set_aspect("equal")
            theta = r * 360
            ax.pie([theta, 360 - theta],
                   startangle=90,
                   colors=[fill_color, _GRID],
                   wedgeprops={"edgecolor": _BG, "linewidth": 1.5, "width": 0.45})
            ax.text(0, 0, f"{data.ratio_pct}", ha="center", va="center",
                    fontsize=22, fontweight="bold", color=fill_color)
            ax.set_title("Utilization Gauge", color=_CYAN, fontsize=10, fontweight="bold")
            ax.grid(False)
            root.addWidget(_canvas_widget(fig))
        except Exception:
            pass

        # Bar: cell vs empty space
        try:
            cell = float(data.cell_area)
            cap  = float(data.cap_area)
            empty = max(0, cap - cell)
            fig2, ax2 = _make_fig(figsize=(7, 2.2))
            ax2.barh(["Capacity"], [cell],  color=fill_color if data.ratio_f else _CYAN,
                     label="Cell Area", edgecolor=_BG, height=0.4)
            ax2.barh(["Capacity"], [empty], left=[cell], color=_GRID,
                     label="Empty Space", edgecolor=_BG, height=0.4)
            ax2.set_xlabel("Area (μm²)", color=_TEXT, fontsize=9)
            ax2.set_title("Area Usage", color=_CYAN, fontsize=10, fontweight="bold")
            ax2.legend(fontsize=8, labelcolor=_TEXT, facecolor=_AX, edgecolor=_GRID)
            ax2.tick_params(colors=_TEXT, labelsize=9)
            root.addWidget(_canvas_widget(fig2))
        except Exception:
            pass

        root.addStretch()


# ─── Analysis / health page ───────────────────────────────────────────────────

class _AnalysisPage(QWidget):
    """Textual + visual design-health analysis derived from all parsed reports."""

    def __init__(self, loaded: dict):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        checks = self._run_checks(loaded)

        # Overall score
        passed  = sum(1 for c in checks if c["status"] == "ok")
        warned  = sum(1 for c in checks if c["status"] == "warn")
        failed  = sum(1 for c in checks if c["status"] == "fail")
        total   = len(checks)
        score   = int(100 * (passed + warned * 0.5) / max(1, total))
        score_color = _GREEN if score >= 80 else (_AMBER if score >= 55 else _RED)

        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(16)

        score_card = QFrame()
        score_card.setObjectName("synth_card")
        sc_lay = QVBoxLayout(score_card)
        sc_lay.setContentsMargins(24, 14, 24, 14)
        sc_lay.setSpacing(4)
        score_lbl = QLabel(f"{score}")
        score_lbl.setObjectName("synth_score_value")
        score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_lbl.setStyleSheet(f"color: {score_color}; font-size: 48px; font-weight: bold;")
        sc_lbl2 = QLabel("DESIGN HEALTH SCORE")
        sc_lbl2.setObjectName("synth_card_label")
        sc_lbl2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sc_lay.addWidget(score_lbl)
        sc_lay.addWidget(sc_lbl2)
        score_card.setFixedWidth(200)
        hdr_row.addWidget(score_card)

        stats_frame = QFrame()
        stats_frame.setObjectName("synth_card")
        stats_lay = QGridLayout(stats_frame)
        stats_lay.setContentsMargins(20, 14, 20, 14)
        stats_lay.setSpacing(8)
        for i, (label, val, color) in enumerate([
            ("PASS",    str(passed), _GREEN),
            ("WARN",    str(warned), _AMBER),
            ("FAIL",    str(failed), _RED),
            ("TOTAL",   str(total),  _TEXT),
        ]):
            l = QLabel(label)
            l.setObjectName("synth_card_label")
            v = QLabel(val)
            v.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: bold;")
            v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            stats_lay.addWidget(l, 0, i)
            stats_lay.addWidget(v, 1, i)
        hdr_row.addWidget(stats_frame, stretch=1)

        # Gauge chart
        try:
            fig, ax = _make_fig(figsize=(3.5, 3.5))
            ax.set_aspect("equal")
            fill_c = score_color
            ax.pie([score, 100 - score], startangle=90,
                   colors=[fill_c, _GRID],
                   wedgeprops={"edgecolor": _BG, "linewidth": 1.5, "width": 0.45})
            ax.text(0, 0, f"{score}", ha="center", va="center",
                    fontsize=26, fontweight="bold", color=fill_c)
            ax.set_title("Health Score", color=_CYAN, fontsize=9, fontweight="bold")
            ax.grid(False)
            hdr_row.addWidget(_canvas_widget(fig))
        except Exception:
            pass

        root.addLayout(hdr_row)

        # Check list
        root.addWidget(_section_hdr("Design Checks"))
        for chk in checks:
            icon  = {"ok": "✓", "warn": "⚠", "fail": "✗", "info": "ℹ"}.get(chk["status"], "•")
            color = {"ok": _GREEN, "warn": _AMBER, "fail": _RED, "info": _TEXT}.get(chk["status"], _TEXT)
            row_w = QFrame()
            row_w.setObjectName("synth_group")
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(12, 8, 12, 8)
            row_l.setSpacing(12)
            ic = QLabel(icon)
            ic.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold;")
            ic.setFixedWidth(20)
            row_l.addWidget(ic)
            txt_col = QVBoxLayout()
            txt_col.setSpacing(2)
            title_lbl = QLabel(chk["title"])
            title_lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 13px;")
            txt_col.addWidget(title_lbl)
            if chk.get("detail"):
                det_lbl = QLabel(chk["detail"])
                det_lbl.setObjectName("synth_card_label")
                det_lbl.setWordWrap(True)
                txt_col.addWidget(det_lbl)
            row_l.addLayout(txt_col, stretch=1)
            root.addWidget(row_w)

        root.addStretch()

    # ── Analysis checks ───────────────────────────────────────────────────────

    def _run_checks(self, loaded: dict) -> list[dict]:
        checks = []

        def chk(title: str, status: str, detail: str = ""):
            checks.append({"title": title, "status": status, "detail": detail})

        area_txt  = loaded.get("area",        "")
        power_txt = loaded.get("power",       "")
        timing_txt= loaded.get("timing",      "")
        qor_txt   = loaded.get("qor",         "")
        util_txt  = loaded.get("utilization", "")

        # ── Timing ────────────────────────────────────────────────────────────
        if qor_txt:
            qd = _QorData(qor_txt)
            all_met = all(s["viol_paths"] == "0" for s in qd.scenarios)
            any_tns = any(s["tns"] not in ("0.00", "0", "—") for s in qd.scenarios)
            if all_met:
                chk("Setup Timing: CLEAN",
                    "ok",
                    "All scenarios report 0 violating paths and TNS = 0.")
            else:
                viols = sum(int(s["viol_paths"]) for s in qd.scenarios
                            if s["viol_paths"] not in ("—",))
                chk("Setup Timing: VIOLATIONS DETECTED",
                    "fail",
                    f"Total violating paths across all scenarios: {viols}."
                    "  Timing closure required before tape-out.")

            hold_viols = sum(int(s["hold_viols"]) for s in qd.scenarios
                             if s.get("hold_viols") and s["hold_viols"] not in ("—", ""))
            if hold_viols > 0:
                chk("Hold Timing: VIOLATIONS",
                    "warn",
                    f"{hold_viols} hold violations detected.  These are typically"
                    " fixed post-layout with filler/buffer insertion.")
            else:
                chk("Hold Timing: CLEAN", "ok",
                    "No hold violations reported across any scenario.")

            cap_viols = _first(r"Max Cap Violations:\s+(\d+)", qor_txt)
            if cap_viols not in ("0", "—"):
                chk("Max Capacitance Violations",
                    "warn",
                    f"{cap_viols} nets exceed maximum capacitance."
                    "  May cause signal integrity issues.")
            else:
                chk("Max Capacitance: OK", "ok",
                    "No max-capacitance violations detected.")

        elif timing_txt:
            td = _TimingData(timing_txt)
            if td.slack_status == "MET":
                chk("Timing: MET", "ok",
                    f"Slack = {td.slack} ns  |  Scenario: {td.scenario}")
            elif td.slack_status == "VIOLATED":
                chk("Timing: VIOLATED", "fail",
                    f"Negative slack = {td.slack} ns  |  Scenario: {td.scenario}")
            else:
                chk("Timing: Status Unknown", "info",
                    "Could not determine timing status from the report.")

        else:
            chk("Timing: No Report Loaded", "info",
                "Load a QoR or timing report for timing analysis.")

        # ── Utilization ───────────────────────────────────────────────────────
        if util_txt:
            ud = _UtilData(util_txt)
            try:
                u = float(ud.ratio)
                if u < 0.75:
                    chk(f"Utilization: LOW ({ud.ratio_pct})", "warn",
                        "Design is significantly underutilized.  Consider reducing"
                        " floorplan area to improve power and routability.")
                elif u < 0.85:
                    chk(f"Utilization: GOOD ({ud.ratio_pct})", "ok",
                        "Utilization is within the recommended range (75–85%).")
                elif u < 0.92:
                    chk(f"Utilization: HIGH ({ud.ratio_pct})", "warn",
                        "Utilization above 85% can cause routing congestion.  "
                        "Consider relaxing the floorplan.")
                else:
                    chk(f"Utilization: CRITICAL ({ud.ratio_pct})", "fail",
                        "Utilization ≥ 92% — very high risk of routing failure.")
            except Exception:
                chk("Utilization: Parse Error", "info", "")
        else:
            chk("Utilization: No Report Loaded", "info",
                "Load a utilization report for floorplan analysis.")

        # ── Power ─────────────────────────────────────────────────────────────
        if power_txt:
            pd = _PowerData(power_txt)
            try:
                dyn = float(pd.dynamic_nw)
                lk  = float(pd.leakage_nw)
                total_mw = (dyn + lk) / 1e6
                lk_pct   = 100.0 * lk / (dyn + lk) if (dyn + lk) > 0 else 0
                chk(f"Total Power: {total_mw:.3f} mW", "ok",
                    f"Dynamic: {dyn/1e6:.3f} mW  |  Leakage: {lk/1e6:.3f} mW"
                    f"  |  Leakage fraction: {lk_pct:.1f}%")
                if lk_pct > 30:
                    chk("High Leakage Fraction", "warn",
                        f"Leakage accounts for {lk_pct:.1f}% of total power."
                        "  Consider using multi-Vt cell mix optimisation.")
            except Exception:
                chk("Power: Loaded (numeric parse failed)", "info", "")
        else:
            chk("Power: No Report Loaded", "info",
                "Load a power report for power analysis.")

        # ── Area ──────────────────────────────────────────────────────────────
        if area_txt:
            ad = _AreaData(area_txt)
            try:
                seq  = int(ad.seq_cells)
                comb = int(ad.comb_cells)
                ratio = comb / seq if seq > 0 else 0
                if ratio < 0.8:
                    chk("Comb/Seq Ratio: LOW", "warn",
                        f"Combinational/Sequential ratio = {ratio:.2f}.  "
                        "Low ratio may indicate under-exploited pipelining.")
                else:
                    chk(f"Comb/Seq Ratio: {ratio:.2f}", "ok",
                        f"Combinational cells: {comb:,}  |  Sequential: {seq:,}")
            except Exception:
                pass
            chk(f"Total Cell Area: {ad.total_area} μm²", "info",
                f"Combinational: {ad.comb_area}  |  Noncombinational: {ad.noncomb_area}")
        else:
            chk("Area: No Report Loaded", "info",
                "Load an area report for area analysis.")

        return checks


# ─── Overview / summary page (shown when folder is loaded) ────────────────────

class _OverviewPage(QWidget):
    def __init__(self, loaded: dict):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        root.addWidget(_section_hdr("Design Overview"))

        # Pull key metrics from whichever reports are loaded
        area_txt  = loaded.get("area",        "")
        power_txt = loaded.get("power",       "")
        qor_txt   = loaded.get("qor",         "")
        util_txt  = loaded.get("utilization", "")

        row1 = QHBoxLayout()
        row1.setSpacing(10)

        design_name = "—"
        for t in [area_txt, qor_txt, power_txt, util_txt]:
            if t:
                design_name = _first(r"Design\s*:\s*(\S+)", t)
                if design_name != "—":
                    break

        row1.addWidget(_metric_card("Design", design_name))

        if util_txt:
            ud = _UtilData(util_txt)
            u_ok = ud.ratio_f < 0.85
            row1.addWidget(_metric_card("Utilization", ud.ratio_pct, ok=u_ok))

        if area_txt:
            ad = _AreaData(area_txt)
            row1.addWidget(_metric_card("Total Area",  ad.total_area, "μm²"))
            row1.addWidget(_metric_card("Total Cells", ad.cells))

        if qor_txt:
            qd = _QorData(qor_txt)
            all_met = all(s["viol_paths"] == "0" for s in qd.scenarios)
            slacks = []
            for s in qd.scenarios:
                try:
                    slacks.append(float(s["crit_slack"]))
                except Exception:
                    pass
            wns = min(slacks) if slacks else None
            row1.addWidget(_metric_card("Timing", "MET" if all_met else "VIOLATED",
                                         ok=all_met))
            if wns is not None:
                row1.addWidget(_metric_card("WNS", f"{wns:.3f}", "ns", ok=wns >= 0))

        if power_txt:
            pd = _PowerData(power_txt)
            try:
                total_mw = (float(pd.dynamic_nw) + float(pd.leakage_nw)) / 1e6
                row1.addWidget(_metric_card("Total Power", f"{total_mw:.3f}", "mW"))
            except Exception:
                row1.addWidget(_metric_card("Power", pd.dynamic))

        root.addLayout(row1)

        # Summary chart: loaded reports status
        report_names = ["Area", "Power", "Timing", "QoR", "Utilization"]
        report_keys  = ["area", "power", "timing", "qor", "utilization"]
        statuses = [bool(loaded.get(k)) for k in report_keys]

        root.addWidget(_section_hdr("Loaded Reports"))
        st_row = QHBoxLayout()
        st_row.setSpacing(8)
        for name, ok in zip(report_names, statuses):
            c = _metric_card(name, "✓" if ok else "✕", ok=ok if ok else None)
            if not ok:
                c.setProperty("card_state", "neutral")
            st_row.addWidget(c)
        root.addLayout(st_row)

        root.addStretch()


# ─── Main widget ──────────────────────────────────────────────────────────────

class SynthesisWidget(QWidget):
    """
    Select a synthesis output folder → auto-discovers report logs by name.
    Displays charts, tables, and a textual design health analysis.
    Separate from the image Analyst workflow.
    """

    sig_status = pyqtSignal(str, str)

    _REPORT_PATTERNS = [
        ("area",        ["area"]),
        ("power",       ["power"]),
        ("timing",      ["timing"]),
        ("qor",         ["qor"]),
        ("utilization", ["util"]),
    ]

    _TAB_LABELS = {
        "area":        "Area",
        "power":       "Power",
        "timing":      "Timing",
        "qor":         "QoR",
        "utilization": "Utilization",
    }

    def __init__(self):
        super().__init__()
        self._loaded: dict[str, str] = {}
        self._folder: str = ""
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Import bar ────────────────────────────────────────────────────────
        bar = QFrame()
        bar.setObjectName("analyst_import_bar")
        ib = QHBoxLayout(bar)
        ib.setContentsMargins(16, 10, 16, 10)
        ib.setSpacing(12)

        title = QLabel("Synthesis Reports Viewer")
        title.setObjectName("import_bar_title")
        ib.addWidget(title)
        ib.addSpacing(16)

        self._folder_btn = QPushButton("⊕  Select Reports Folder")
        self._folder_btn.setObjectName("btn_success")
        self._folder_btn.setFixedHeight(34)
        self._folder_btn.clicked.connect(self._select_folder)
        ib.addWidget(self._folder_btn)

        self._folder_lbl = QLabel("No folder selected")
        self._folder_lbl.setObjectName("synth_card_label")
        ib.addWidget(self._folder_lbl, stretch=1)

        # Status dots
        self._status_dots: dict[str, QLabel] = {}
        for key, _ in self._REPORT_PATTERNS:
            dot = QLabel("●")
            dot.setObjectName("synth_dot_empty")
            dot.setFixedWidth(16)
            dot.setToolTip(f"{self._TAB_LABELS[key]} report")
            self._status_dots[key] = dot
            ib.addWidget(dot)

        ib.addSpacing(8)
        reload_btn = QPushButton("↺  Reload")
        reload_btn.setObjectName("import_btn")
        reload_btn.setFixedHeight(30)
        reload_btn.clicked.connect(self._reload_folder)
        ib.addWidget(reload_btn)

        clear_btn = QPushButton("✕  Clear")
        clear_btn.setObjectName("nav_btn_warn")
        clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear_all)
        ib.addWidget(clear_btn)

        root.addWidget(bar)

        # ── Placeholder ───────────────────────────────────────────────────────
        self._placeholder = QWidget()
        ph_lay = QVBoxLayout(self._placeholder)
        ph_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_lbl = QLabel(
            "Select a synthesis output folder to load reports automatically.\n\n"
            "Expected file names (case-insensitive, any extension):\n"
            "  area_report   ·   power_report   ·   timing_report   ·   qor_report   ·   utilization_report"
        )
        ph_lbl.setObjectName("synth_placeholder")
        ph_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_lay.addWidget(ph_lbl)

        # ── Tab widget ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setObjectName("synth_tabs")
        self._tab_sas: dict[str, QScrollArea] = {}

        # Fixed tabs: Overview first, then per-report, then Analysis
        overview_sa = QScrollArea()
        overview_sa.setWidgetResizable(True)
        overview_sa.setFrameShape(QFrame.Shape.NoFrame)
        overview_sa.setWidget(QLabel("Load a folder to see the overview.",
                                      alignment=Qt.AlignmentFlag.AlignCenter))
        self._tabs.addTab(overview_sa, "Overview")
        self._overview_sa = overview_sa

        for key, _ in self._REPORT_PATTERNS:
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setWidget(QLabel(f"Load the {self._TAB_LABELS[key]} report to see data.",
                                 alignment=Qt.AlignmentFlag.AlignCenter))
            self._tabs.addTab(sa, self._TAB_LABELS[key])
            self._tab_sas[key] = sa

        analysis_sa = QScrollArea()
        analysis_sa.setWidgetResizable(True)
        analysis_sa.setFrameShape(QFrame.Shape.NoFrame)
        analysis_sa.setWidget(QLabel("Load reports to see design analysis.",
                                      alignment=Qt.AlignmentFlag.AlignCenter))
        self._tabs.addTab(analysis_sa, "Analysis")
        self._analysis_sa = analysis_sa

        self._tabs.hide()

        root.addWidget(self._placeholder, stretch=1)
        root.addWidget(self._tabs, stretch=1)

    # ── Folder selection & discovery ──────────────────────────────────────────

    def _select_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Synthesis Reports Folder", self._folder or ""
        )
        if not folder:
            return
        self._folder = folder
        self._load_from_folder()

    def _reload_folder(self):
        if self._folder:
            self._load_from_folder()

    def _load_from_folder(self):
        folder = self._folder
        if not os.path.isdir(folder):
            self.sig_status.emit(f"Folder not found: {folder}", "#FF453A")
            return

        self._folder_lbl.setText(os.path.basename(folder))
        self._loaded.clear()

        try:
            all_files = os.listdir(folder)
        except Exception as exc:
            self.sig_status.emit(f"Cannot read folder: {exc}", "#FF453A")
            return

        found = []
        for key, keywords in self._REPORT_PATTERNS:
            match = None
            for fname in all_files:
                name_lower = fname.lower()
                # file must contain any keyword and have a known extension
                if (any(kw in name_lower for kw in keywords)
                        and os.path.splitext(fname)[1].lower() in
                        (".log", ".rpt", ".txt", ".rep", "")):
                    match = fname
                    break
            if match:
                path = os.path.join(folder, match)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        self._loaded[key] = f.read()
                    self._update_dot(key, ok=True)
                    found.append(match)
                except Exception as exc:
                    self._update_dot(key, ok=False)
                    self.sig_status.emit(f"Error reading {match}: {exc}", "#FF453A")
            else:
                self._update_dot(key, ok=None)

        self._refresh_all()

        n = len(self._loaded)
        if n == 0:
            self.sig_status.emit("No matching report files found in folder.", "#FF9F0A")
        else:
            self.sig_status.emit(
                f"Loaded {n} report(s) from {os.path.basename(folder)}: {', '.join(found)}",
                "#34C759",
            )
            self._show_tabs()

    def _update_dot(self, key: str, ok: Optional[bool]):
        dot = self._status_dots[key]
        if ok is True:
            dot.setObjectName("synth_dot_ok")
        elif ok is False:
            dot.setObjectName("synth_dot_err")
        else:
            dot.setObjectName("synth_dot_empty")
        dot.style().unpolish(dot)
        dot.style().polish(dot)

    # ── Content rendering ─────────────────────────────────────────────────────

    def _refresh_all(self):
        # Overview
        self._overview_sa.setWidget(_OverviewPage(self._loaded))

        # Per-report tabs
        for key, _ in self._REPORT_PATTERNS:
            text = self._loaded.get(key, "")
            sa   = self._tab_sas[key]
            if not text:
                sa.setWidget(QLabel(f"No {self._TAB_LABELS[key]} report found.",
                                     alignment=Qt.AlignmentFlag.AlignCenter))
                continue
            try:
                if key == "area":
                    sa.setWidget(_AreaChartsPage(_AreaData(text)))
                elif key == "power":
                    sa.setWidget(_PowerChartsPage(_PowerData(text)))
                elif key == "timing":
                    sa.setWidget(_TimingChartsPage(_TimingData(text)))
                elif key == "qor":
                    sa.setWidget(_QorChartsPage(_QorData(text)))
                elif key == "utilization":
                    sa.setWidget(_UtilChartsPage(_UtilData(text)))
            except Exception as exc:
                err = QLabel(f"Parse error: {exc}")
                err.setAlignment(Qt.AlignmentFlag.AlignCenter)
                sa.setWidget(err)

        # Analysis tab
        if self._loaded:
            try:
                self._analysis_sa.setWidget(_AnalysisPage(self._loaded))
            except Exception as exc:
                self._analysis_sa.setWidget(QLabel(f"Analysis error: {exc}",
                                                    alignment=Qt.AlignmentFlag.AlignCenter))

    def _show_tabs(self):
        if self._loaded:
            self._placeholder.hide()
            self._tabs.show()
            self._tabs.setCurrentIndex(0)

    # ── Public API ────────────────────────────────────────────────────────────

    def _clear_all(self):
        self._loaded.clear()
        self._folder = ""
        self._folder_lbl.setText("No folder selected")
        for key, _ in self._REPORT_PATTERNS:
            self._update_dot(key, ok=None)
            sa = self._tab_sas[key]
            sa.setWidget(QLabel(f"Load the {self._TAB_LABELS[key]} report to see data.",
                                 alignment=Qt.AlignmentFlag.AlignCenter))
        self._overview_sa.setWidget(QLabel("Load a folder to see the overview.",
                                            alignment=Qt.AlignmentFlag.AlignCenter))
        self._analysis_sa.setWidget(QLabel("Load reports to see design analysis.",
                                            alignment=Qt.AlignmentFlag.AlignCenter))
        self._tabs.hide()
        self._placeholder.show()
        self.sig_status.emit("Synthesis reports cleared.", "#8A8A8E")
