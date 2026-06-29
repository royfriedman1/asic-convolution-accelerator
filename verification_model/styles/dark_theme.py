"""
TAU 360 Dual-Theme Stylesheet
Exports DARK_STYLESHEET, LIGHT_STYLESHEET, and get_stylesheet(dark: bool).
"""

_ACCENT   = "#00ADEF"   # Electric Cyan — TAU brand colour
_ACCENT_P = "#0090C8"   # Pressed / dimmed variant
_FONT     = "'Heebo', 'Segoe UI', Arial, sans-serif"


def _make(
    bg: str,       # page / root background
    bg_card: str,  # group-box / panel surface
    bg_in: str,    # input / elevated surface
    bg_sb: str,    # sidebar background
    brd: str,      # default border colour
    fg: str,       # primary text
    fg2: str,      # secondary / dim text
    btn: str,      # button resting background
    btn_h: str,    # button hover background
    is_dark: bool,
) -> str:

    A   = _ACCENT
    AP  = _ACCENT_P
    F   = _FONT

    # Semantic colours that flip between modes
    green   = "#34C759" if is_dark else "#1A8A35"
    amber   = "#FF9F0A" if is_dark else "#B86E00"
    red_c   = "#FF453A" if is_dark else "#C0392B"
    img_bg  = "#000000" if is_dark else "#E4E4E8"
    sel_bg  = "rgba(0,173,239,.22)" if is_dark else "rgba(0,173,239,.14)"
    nav_act = "rgba(0,173,239,.14)" if is_dark else "rgba(0,173,239,.11)"
    nav_hov = "rgba(0,173,239,.07)" if is_dark else "rgba(0,173,239,.06)"
    pri_bg  = "rgba(0,173,239,.13)" if is_dark else "rgba(0,173,239,.09)"
    pri_brd = "rgba(0,173,239,.42)" if is_dark else "rgba(0,173,239,.35)"

    return f"""
/* ═══════════════════════════════════════════════════════════════
   TAU 360  ·  {"Dark" if is_dark else "Light"} Mode
   Accent: {A}  |  Font: Heebo
   ═══════════════════════════════════════════════════════════════ */

/* ─── Global ──────────────────────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {bg};
}}
QWidget {{
    background-color: {bg};
    color: {fg};
    font-family: {F};
    font-size: 14px;
}}

/* ─── Sidebar ──────────────────────────────────────────────── */
#sidebar {{
    background-color: {bg_sb};
    border-right: 1px solid {brd};
    min-width: 240px;
    max-width: 240px;
}}
#logo_block {{
    background-color: {bg_sb};
    border-bottom: 1px solid {brd};
}}

/* Theme toggle pill */
#theme_toggle {{
    background-color: {btn};
    border: 1px solid {brd};
    border-radius: 13px;
    color: {fg2};
    font-size: 12px;
    font-weight: bold;
    font-family: {F};
    padding: 4px 16px;
    min-height: 26px;
    min-width: 140px;
    letter-spacing: 0.5px;
}}
#theme_toggle:hover {{
    border: 1px solid {A};
    color: {A};
    background-color: {btn_h};
}}
#theme_toggle:pressed {{
    color: {AP};
}}

/* Product title */
#product_title {{
    color: {fg};
    font-size: 13px;
    font-weight: bold;
    font-family: {F};
    line-height: 1.5;
    qproperty-alignment: AlignLeft;
}}
#product_accent {{
    color: {A};
    font-size: 12px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2px;
}}

/* Nav section label */
#nav_section_hdr {{
    color: {fg2};
    font-size: 11px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2px;
    padding: 8px 12px 2px 12px;
}}

/* Nav buttons */
#nav_btn {{
    background-color: transparent;
    color: {fg2};
    border: none;
    border-left: 3px solid transparent;
    padding: 8px 8px 8px 12px;
    text-align: left;
    font-size: 12px;
    font-weight: bold;
    font-family: {F};
    min-height: 34px;
}}
#nav_btn:hover {{
    background-color: {nav_hov};
    color: {fg};
    border-left: 3px solid {brd};
}}
#nav_btn:checked {{
    background-color: {nav_act};
    color: {A};
    border-left: 3px solid {A};
}}

/* Sidebar divider */
#nav_separator {{
    background-color: {brd};
    max-height: 1px;
    margin: 5px 18px;
}}

/* Credits footer */
#credits_lbl {{
    color: {fg};
    font-size: 11px;
    font-family: {F};
    letter-spacing: 0.3px;
    padding: 4px 0;
}}
#credits_link {{
    color: {A};
    font-size: 11px;
    font-family: {F};
    padding: 2px 0;
    text-decoration: underline;
}}
#version_label {{
    color: {fg2};
    font-size: 12px;
    font-family: {F};
    padding: 2px 0;
    opacity: 0.6;
}}

/* ─── Header bar (mode title) ─────────────────────────────── */
#analyst_top_bar {{
    background-color: {bg};
}}
#header_bar {{
    background-color: {bg_card};
    border-bottom: 1px solid {brd};
    padding: 6px 16px;
    min-height: 42px;
    max-height: 52px;
}}
#mode_title {{
    color: {A};
    font-size: 20px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 3px;
}}
#mode_subtitle {{
    color: {fg2};
    font-size: 12px;
    font-family: {F};
    letter-spacing: 2px;
}}

/* ─── GroupBox ────────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid {brd};
    border-radius: 9px;
    margin-top: 18px;
    padding: 12px 10px 8px 10px;
    background-color: {bg_card};
    font-family: {F};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 2px 10px;
    color: {A};
    font-size: 11px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2.5px;
    background-color: {bg_card};
    border: 1px solid {brd};
    border-radius: 4px;
}}

/* ─── Tab Widget ──────────────────────────────────────────── */
QTabWidget#right_tabs::pane {{
    border: 1px solid {brd};
    border-top: none;
    border-radius: 0 0 9px 9px;
    background-color: {bg_card};
}}
QTabWidget#right_tabs > QTabBar {{
    alignment: justify;
}}
QTabBar::tab {{
    background-color: {bg_in};
    color: {fg2};
    border: 1px solid {brd};
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 1.5px;
    min-width: 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    background-color: {bg_card};
    color: {A};
    border-bottom-color: {bg_card};
}}
QTabBar::tab:hover:!selected {{
    background-color: {btn_h};
    color: {fg};
    border-color: {A};
}}

/* ─── Frame cards ─────────────────────────────────────────── */
#img_frame {{
    background-color: {bg_card};
    border: 1px solid {brd};
    border-radius: 9px;
}}

/* ─── Image display (1px cyan border as per spec) ─────────── */
#img_label_display {{
    background-color: {img_bg};
    border: 1px solid {A};
    border-radius: 8px;
    qproperty-alignment: AlignCenter;
}}
#img_title {{
    color: {A};
    font-size: 11px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2.5px;
}}
#img_info {{
    color: {fg2};
    font-size: 11px;
    font-family: 'Consolas', 'Courier New', monospace;
}}

/* ─── Inputs ──────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit {{
    background-color: {bg_in};
    border: 1px solid {brd};
    border-radius: 6px;
    padding: 4px 8px;
    color: {fg};
    selection-background-color: {A};
    selection-color: #ffffff;
    font-family: {F};
    font-size: 13px;
    min-height: 28px;
}}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border: 1.5px solid {A};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {btn_h};
    border: none;
    border-left: 1px solid {brd};
    width: 18px;
    border-radius: 0px;
}}
QSpinBox::up-button {{
    border-top-right-radius: 5px;
}}
QSpinBox::down-button {{
    border-bottom-right-radius: 5px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {A};
}}

/* Weight cells — height controlled by setFixedHeight() in code */
#weight_cell {{
    background-color: {bg_in};
    border: 1px solid {brd};
    border-radius: 6px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 14px;
    font-weight: bold;
    color: {fg};
    min-width: 46px;
    padding: 2px 4px;
    qproperty-alignment: AlignCenter;
}}
#weight_cell:focus {{
    border: 1.5px solid {A};
    color: {A};
}}

/* ─── Buttons (base) ──────────────────────────────────────── */
QPushButton {{
    background-color: {btn};
    border: 1px solid {brd};
    border-radius: 7px;
    padding: 4px 14px;
    color: {fg};
    font-weight: bold;
    font-family: {F};
    font-size: 13px;
    letter-spacing: 0.3px;
    min-height: 28px;
    min-width: 60px;
}}
QPushButton:hover {{
    background-color: {btn_h};
    border: 1px solid {A};
    color: {A};
}}
QPushButton:pressed {{
    background-color: {bg_in};
    border: 1px solid {AP};
    color: {AP};
}}
QPushButton:disabled {{
    background-color: {bg};
    border: 1px solid {brd};
    color: {fg2};
    opacity: 0.5;
}}

/* Primary — cyan accent fill */
#btn_primary {{
    background-color: {A};
    border: 1px solid {A};
    color: #ffffff;
    font-weight: bold;
    min-width: 50px;
    min-height: 27px;
    max-height: 33px;
    padding: 3px 8px;
}}
#btn_primary:hover {{
    background-color: #33C3FF;
    border: 1px solid #33C3FF;
    color: #ffffff;
}}
#btn_primary:pressed {{
    background-color: {AP};
    border: 1px solid {AP};
    color: #ffffff;
}}
#btn_primary:disabled {{
    background-color: {bg_in};
    border: 1px solid {brd};
    color: {fg2};
}}

/* Export — green CTA */
#btn_export {{
    background-color: rgba(52,199,89,.13);
    border: 1.5px solid rgba(52,199,89,.50);
    color: {green};
    font-size: 13px;
    font-weight: bold;
    letter-spacing: 0.4px;
    padding: 3px 18px;
    min-height: 27px;
    max-height: 33px;
    min-width: 50px;
    border-radius: 9px;
    font-family: {F};
}}
#btn_export:hover {{
    background-color: rgba(52,199,89,.24);
    border: 1.5px solid {green};
    color: #ffffff;
}}
#btn_export:pressed {{
    background-color: rgba(52,199,89,.35);
}}

/* Success */
#btn_success {{
    background-color: rgba(52,199,89,.11);
    border: 1px solid rgba(52,199,89,.42);
    color: {green};
    font-weight: bold;
    min-width: 50px;
    min-height: 27px;
    max-height: 33px;
    padding: 3px 8px;
}}
#btn_success:hover {{
    background-color: rgba(52,199,89,.22);
    border: 1px solid {green};
    color: #ffffff;
}}
#btn_success:pressed {{
    background-color: rgba(52,199,89,.32);
}}

/* Warning / amber — kernel presets */
#btn_warn {{
    background-color: rgba(255,159,10,.10);
    border: 1px solid rgba(255,159,10,.35);
    color: {amber};
    font-weight: bold;
    font-size: 12px;
    min-width: 50px;
    min-height: 27px;
    max-height: 33px;
    padding: 3px 8px;
    letter-spacing: 0.2px;
}}
#btn_warn:hover {{
    background-color: rgba(255,159,10,.22);
    border: 1px solid {amber};
    color: #ffffff;
}}
#btn_warn:pressed {{
    background-color: rgba(255,159,10,.35);
    border: 1px solid {amber};
    color: #ffffff;
}}

/* ─── Zoom buttons (ImageDisplay) ─────────────────────────── */
#btn_zoom {{
    background-color: rgba(255,255,255,.06);
    border: 1px solid {brd};
    color: {fg2};
    font-size: 14px;
    font-weight: bold;
    padding: 0px;
    border-radius: 4px;
}}
#btn_zoom:hover {{
    background-color: rgba(0,173,239,.18);
    border: 1px solid {A};
    color: {A};
}}
#btn_zoom:pressed {{
    background-color: rgba(0,173,239,.30);
    border: 1px solid {A};
    color: #ffffff;
}}
#btn_zoom:disabled {{
    background-color: transparent;
    border: 1px solid {brd};
    color: {brd};
}}

/* ─── Labels ──────────────────────────────────────────────── */
QLabel {{
    background-color: transparent;
    color: {fg};
    font-family: {F};
}}
#lbl_metric_value {{
    color: {green};
    font-size: 24px;
    font-weight: bold;
    font-family: 'Consolas', 'Courier New', monospace;
}}
#lbl_metric_unit {{ color: {fg2}; font-size: 12px; }}
#lbl_metric_name {{
    color: {fg2};
    font-size: 12px;
    letter-spacing: 2px;
    font-weight: bold;
    font-family: {F};
}}
#lbl_stat_value {{
    color: {amber};
    font-size: 13px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}}
#lbl_error_count {{
    color: {red_c};
    font-size: 20px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}}
#lbl_match_rate {{
    color: {green};
    font-size: 20px;
    font-weight: bold;
    font-family: 'Consolas', monospace;
}}
#lbl_section {{
    color: {A};
    font-size: 11px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2.5px;
    padding-top: 2px;
}}
#lbl_unit {{
    color: {fg2};
    font-size: 11px;
    font-family: {F};
    padding-top: 2px;
}}

/* ─── Status Bar ──────────────────────────────────────────── */
QStatusBar {{
    background-color: {bg_card};
    border-top: 1px solid {brd};
    font-family: {F};
    font-size: 12px;
    min-height: 24px;
}}
QStatusBar::item {{
    border: none;
    border-right: 1px solid {brd};
}}

/* ─── Progress Bar ────────────────────────────────────────── */
QProgressBar {{
    background-color: {bg_in};
    border: 1px solid {brd};
    border-radius: 5px;
    text-align: center;
    color: {fg};
    font-family: {F};
    font-size: 11px;
    min-height: 14px;
    max-height: 14px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #005580, stop:1 {A});
    border-radius: 4px;
}}

/* ─── Scrollbars ──────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {bg};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {brd};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {A}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {bg};
    height: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {brd};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{ background: {A}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ─── ComboBox — height controlled by setFixedHeight() in code ─── */
QComboBox {{
    background-color: {bg_in};
    border: 1px solid {brd};
    border-radius: 6px;
    padding: 4px 10px;
    color: {fg};
    font-family: {F};
    font-size: 13px;
    min-height: 28px;
}}
QComboBox:focus {{ border: 1px solid {A}; }}
QComboBox::drop-down {{
    border: none;
    border-left: 1px solid {brd};
    width: 24px;
    background-color: {btn_h};
}}
QComboBox QAbstractItemView {{
    background-color: {bg_card};
    border: 1px solid {brd};
    selection-background-color: {sel_bg};
    color: {fg};
    outline: none;
    font-family: {F};
}}

/* ─── Table ───────────────────────────────────────────────── */
QTableWidget {{
    background-color: {bg_card};
    border: 1px solid {brd};
    border-radius: 7px;
    gridline-color: {bg_in};
    alternate-background-color: {bg};
    outline: none;
    font-family: {F};
}}
QTableWidget::item {{ padding: 4px 10px; }}
QTableWidget::item:selected {{
    background-color: {sel_bg};
    color: {A};
}}
QHeaderView::section {{
    background-color: {bg_in};
    color: {fg2};
    border: none;
    border-bottom: 1px solid {brd};
    border-right: 1px solid {brd};
    padding: 6px 10px;
    font-weight: bold;
    font-family: {F};
    font-size: 12px;
    letter-spacing: 1px;
}}

/* ─── Splitter ────────────────────────────────────────────── */
QSplitter::handle {{ background-color: {brd}; }}
QSplitter::handle:horizontal {{ width: 2px; }}
QSplitter::handle:vertical {{ height: 2px; }}

/* ─── Slider ──────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {bg_in};
    height: 4px;
    border-radius: 2px;
    border: 1px solid {brd};
}}
QSlider::handle:horizontal {{
    background: {A};
    border: 1px solid {AP};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::handle:horizontal:hover {{ background: #33C3FF; }}
QSlider::sub-page:horizontal {{
    background: {A};
    height: 4px;
    border-radius: 2px;
    opacity: 0.7;
}}

/* ─── Tooltip ─────────────────────────────────────────────── */
QToolTip {{
    background-color: {bg_card};
    color: {fg};
    border: 1px solid {brd};
    padding: 5px 10px;
    border-radius: 6px;
    font-family: {F};
    font-size: 13px;
}}

/* ─── Message Box ─────────────────────────────────────────── */
QMessageBox {{
    background-color: {bg_card};
    font-family: {F};
}}
QMessageBox QLabel {{
    color: {fg};
    font-size: 14px;
    font-family: {F};
}}

/* Nav warn button — Clear (red tint, sidebar) */
#nav_btn_warn {{
    background-color: transparent;
    color: {red_c};
    border: none;
    border-left: 3px solid transparent;
    padding: 8px 8px 8px 12px;
    text-align: left;
    font-size: 12px;
    font-weight: bold;
    font-family: {F};
    min-height: 34px;
}}
#nav_btn_warn:hover {{
    background-color: rgba(255,69,58,.10);
    color: #ff6b60;
    border-left: 3px solid {red_c};
}}
#nav_btn_warn:pressed {{
    background-color: rgba(255,69,58,.20);
}}

/* ─── Vertical separator (import bar) ─────────────────────── */
#nav_vseparator {{
    background-color: {brd};
    min-width: 1px;
    max-width: 1px;
}}

/* ─── Import section header (inside import bar) ───────────── */
#import_section_hdr {{
    color: {fg2};
    font-size: 9px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2px;
    padding-bottom: 1px;
}}

/* ─── Kernel config bar ────────────────────────────────────── */
#kernel_bar {{
    background-color: {bg_card};
    border-top: 1px solid {brd};
    border-bottom: 1px solid {brd};
}}
#kb_caption {{
    color: {fg2};
    font-size: 9px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 1px;
}}
#kb_value {{
    color: {A};
    font-size: 10px;
    font-family: 'Consolas', monospace;
}}

/* ─── Loading Overlay ──────────────────────────────────────── */
#loading_card {{
    background-color: {bg_card};
    border: 1px solid {brd};
    border-radius: 18px;
}}
#loading_spinner {{
    color: {A};
    font-size: 34px;
    font-family: {F};
    padding: 0;
    margin: 0;
    background: transparent;
}}
#loading_title {{
    color: {fg};
    font-size: 16px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 1px;
    background: transparent;
}}
#loading_msg {{
    color: {fg2};
    font-size: 13px;
    font-family: {F};
    background: transparent;
}}
#loading_progress {{
    background-color: {bg_in};
    border: none;
    border-radius: 2px;
    min-height: 4px;
    max-height: 4px;
}}
#loading_progress::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #005580, stop:1 {A});
    border-radius: 2px;
}}

/* ─── Synthesis Reports Widget ─────────────────────────────── */
#analyst_import_bar {{
    background-color: {bg_card};
    border-bottom: 1px solid {brd};
    min-height: 52px;
    max-height: 60px;
}}
#import_bar_title {{
    color: {A};
    font-size: 14px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2px;
}}
#import_btn {{
    background-color: {bg_in};
    border: 1px solid {brd};
    border-radius: 6px;
    padding: 3px 12px;
    color: {fg2};
    font-weight: bold;
    font-family: {F};
    font-size: 12px;
    min-height: 26px;
}}
#import_btn:hover {{
    background-color: rgba(0,173,239,.14);
    border: 1px solid {A};
    color: {A};
}}
#import_btn:pressed {{
    background-color: rgba(0,173,239,.24);
    border: 1px solid {AP};
    color: {AP};
}}
#synth_tabs::pane {{
    border: none;
    background-color: {bg};
}}
#synth_tabs > QTabBar::tab {{
    background-color: {bg_in};
    color: {fg2};
    border: 1px solid {brd};
    border-bottom: none;
    border-top-left-radius: 7px;
    border-top-right-radius: 7px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 1.5px;
    min-width: 70px;
    margin-right: 2px;
}}
#synth_tabs > QTabBar::tab:selected {{
    background-color: {bg_card};
    color: {A};
    border-bottom-color: {bg_card};
}}
#synth_tabs > QTabBar::tab:hover:!selected {{
    background-color: {btn_h};
    color: {fg};
    border-color: {A};
}}
#synth_section_hdr {{
    color: {A};
    font-size: 11px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 2.5px;
    padding: 2px 0;
    border-bottom: 1px solid {brd};
    margin-bottom: 2px;
}}
#synth_card {{
    background-color: {bg_card};
    border: 1px solid {brd};
    border-radius: 9px;
    min-height: 64px;
}}
#synth_card[card_state="ok"] {{
    border: 1px solid rgba(52,199,89,.50);
    background-color: rgba(52,199,89,.07);
}}
#synth_card[card_state="warn"] {{
    border: 1px solid rgba(255,69,58,.50);
    background-color: rgba(255,69,58,.07);
}}
#synth_card_label {{
    color: {fg2};
    font-size: 10px;
    font-weight: bold;
    font-family: {F};
    letter-spacing: 1.5px;
}}
#synth_card_value {{
    color: {fg};
    font-size: 18px;
    font-weight: bold;
    font-family: 'Consolas', 'Courier New', monospace;
}}
#synth_card_unit {{
    color: {fg2};
    font-size: 11px;
    font-family: {F};
    padding-top: 4px;
}}
#synth_group {{
    background-color: {bg_card};
    border: 1px solid {brd};
    border-radius: 8px;
}}
#synth_mono {{
    color: {fg};
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
}}
#synth_placeholder {{
    color: {fg2};
    font-size: 15px;
    font-family: {F};
    line-height: 1.8;
}}
#synth_dot_empty {{ color: {brd}; font-size: 12px; }}
#synth_dot_ok    {{ color: {green}; font-size: 12px; }}
#synth_dot_err   {{ color: {red_c}; font-size: 12px; }}
#util_bar_bg {{
    background-color: {bg_in};
    border: 1px solid {brd};
    border-radius: 4px;
}}

/* ─── Memory Simulation Widget ─────────────────────────────── */
#sim_ctrl_bar {{
    background-color: {bg_card};
    border-bottom: 1px solid {brd};
    min-height: 52px;
    max-height: 64px;
}}
#sim_cycle_card {{
    background-color: {bg_card};
    border-bottom: 1px solid {brd};
    padding: 4px 0;
}}
/* Architecture quick-reference strip */
#sim_arch_card {{
    background-color: {bg_in};
    border-bottom: 1px solid {brd};
    min-height: 48px;
    max-height: 60px;
}}
/* Current-operation info strip */
#sim_op_card {{
    background-color: {bg_card};
    border-bottom: 1px solid {brd};
    min-height: 52px;
    max-height: 68px;
}}
#sim_op_main {{
    color: {A};
    font-size: 13px;
    font-weight: 700;
    font-family: 'Consolas', 'Courier New', monospace;
    letter-spacing: 0.4px;
}}
#sim_op_detail {{
    color: {fg2};
    font-size: 11px;
    font-family: 'Consolas', 'Courier New', monospace;
}}
#sim_badge_valid {{
    background-color: rgba(34,197,94,.13);
    border: 1.5px solid rgba(34,197,94,.65);
    border-radius: 17px;
    color: {green};
    font-weight: 700;
    font-size: 13px;
    font-family: 'Consolas', 'Courier New', monospace;
    padding: 4px 16px;
    letter-spacing: 0.3px;
}}
#sim_badge_invalid {{
    background-color: rgba(239,68,68,.10);
    border: 1.5px solid rgba(239,68,68,.55);
    border-radius: 17px;
    color: {red_c};
    font-weight: 700;
    font-size: 13px;
    font-family: 'Consolas', 'Courier New', monospace;
    padding: 4px 16px;
    letter-spacing: 0.3px;
}}
"""


# ── Exported theme objects ────────────────────────────────────────────────────

DARK_STYLESHEET = _make(
    bg="#1A1A1B", bg_card="#222224", bg_in="#2C2C2E",
    bg_sb="#111113", brd="#3A3A3C",
    fg="#FFFFFF",   fg2="#8A8A8E",
    btn="#2C2C2E",  btn_h="#3A3A3C",
    is_dark=True,
)

LIGHT_STYLESHEET = _make(
    bg="#F5F5F7", bg_card="#FFFFFF", bg_in="#EBEBED",
    bg_sb="#E8E8EC", brd="#C8C8CC",
    fg="#1A1A1B",  fg2="#6E6E73",
    btn="#EBEBED", btn_h="#DCDCE0",
    is_dark=False,
)


def get_stylesheet(dark: bool = True) -> str:
    """Return the active stylesheet. Pass dark=False for Light Mode."""
    return DARK_STYLESHEET if dark else LIGHT_STYLESHEET
