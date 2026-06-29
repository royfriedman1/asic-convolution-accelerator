"""
ASIC Verification & Analysis Suite
Entry point — bootstraps PyQt6 application, shows splash screen, then opens
the main window.

Run:
    python main.py
"""

import sys
import os
import traceback
import tempfile
import threading
from datetime import datetime

# Ensure the package root is on the Python path when run directly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Stderr → file (frozen only) ────────────────────────────────────────────────
# When built with console=False, sys.stderr is None and SIP's "real" exception
# text (printed to stderr before sipBadCatcherResult is raised) disappears.
# Redirect it to a persistent log so we can see the actual error.
if getattr(sys, "frozen", False):
    _stderr_log = os.path.join(
        tempfile.gettempdir(), "ASIC_Suite_stderr.log"
    )
    try:
        # 'w' truncates on every launch so the file stays small
        sys.stderr = open(_stderr_log, "w", encoding="utf-8", buffering=1)
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore    import Qt, QTimer
from PyQt6.QtGui     import QFont, QIcon

from styles.dark_theme import get_stylesheet


# ── Crash logging ──────────────────────────────────────────────────────────────

def _write_crash_log(crash_text: str) -> str:
    """Write crash_text to %TEMP%/ASIC_Suite_crash_<ts>.log. Returns the path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(tempfile.gettempdir(), f"ASIC_Suite_crash_{ts}.log")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"ASIC Suite — crash report  {datetime.now()}\n\n")
            f.write(crash_text)
    except Exception:
        pass
    return log_path


def _show_crash_dialog(exc_type, exc_value, log_path: str) -> None:
    try:
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "ASIC Suite — Unexpected Error",
                f"The application encountered an unexpected error:\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"A crash log has been saved to:\n{log_path}",
            )
    except Exception:
        pass


def _install_crash_logger() -> None:
    """
    Install three complementary exception catchers:

    1. sys.excepthook          — uncaught exceptions on the main thread
    2. threading.excepthook    — uncaught exceptions on any Python thread
    3. SafeApp.notify override — exceptions inside Qt event handlers / C++ slots
                                 (the SIP layer would otherwise swallow these and
                                  produce the cryptic sipBadCatcherResult error)
    """
    # 1. Main-thread hook
    def _main_hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        crash_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_path = _write_crash_log(crash_text)
        _show_crash_dialog(exc_type, exc_value, log_path)
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _main_hook

    # 2. Background-thread hook (Python 3.8+)
    def _thread_hook(args):
        if args.exc_type is SystemExit:
            return
        crash_text = "".join(
            traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
        )
        thread_name = args.thread.name if args.thread else "unknown"
        _write_crash_log(f"Thread: {thread_name}\n\n{crash_text}")
        # Don't show dialog for background thread errors — just log silently

    threading.excepthook = _thread_hook


class _SafeApp(QApplication):
    """
    QApplication subclass that overrides notify() to catch ALL Python exceptions
    raised inside Qt event handlers and C++ slots.

    Without this, any exception in a slot called from C++ propagates through SIP,
    which swallows it and raises the unhelpful
      TypeError: invalid argument to sipBadCatcherResult()
    instead, making the real error invisible.
    """

    def notify(self, receiver, event):
        try:
            return super().notify(receiver, event)
        except Exception:
            crash_text = traceback.format_exc()
            log_path = _write_crash_log(crash_text)
            exc_lines = crash_text.strip().splitlines()
            # Last line is the actual error message
            last_line = exc_lines[-1] if exc_lines else "unknown error"
            _show_crash_dialog(type(None), last_line, log_path)
            return False


# ── Helpers ────────────────────────────────────────────────────────────────────

def _app_icon_path() -> str:
    """Return path to the bundled ICO (PyInstaller) or dev-time ICO/PNG."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS          # type: ignore[attr-defined]
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    for name in ("app_icon.ico", "tau_logo.png"):
        p = os.path.join(base, name)
        if os.path.exists(p):
            return p
    return ""


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    _install_crash_logger()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")

    app = _SafeApp(sys.argv)
    app.setApplicationName(
        "Area & Power Optimized Hardware Accelerator for Single Convolutional Kernel"
    )
    app.setApplicationVersion("1.0")
    app.setOrganizationName("Tel Aviv University — Electrical Engineering")
    app.setStyleSheet(get_stylesheet(dark=True))

    # Application icon (taskbar + window chrome)
    icon_path = _app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Heebo", 11)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(font)

    # ── splash screen ─────────────────────────────────────────────────────────
    from ui.splash_screen import SplashScreen
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    splash.set_progress(10, "Initialising hardware model …")
    app.processEvents()

    # ── import heavy modules (triggers compilation caches) ────────────────────
    from core.golden_model import run_golden_model_fast          # noqa: F401
    splash.set_progress(30, "Loading convolution engine …")
    app.processEvents()

    from core.hex_exporter import export_stimulus, export_scoreboard  # noqa: F401
    splash.set_progress(50, "Preparing analysis tools …")
    app.processEvents()

    from ui.main_window import MainWindow
    splash.set_progress(70, "Building UI components …")
    app.processEvents()

    # ── create main window ────────────────────────────────────────────────────
    window = MainWindow()
    if icon_path:
        window.setWindowIcon(QIcon(icon_path))

    splash.set_progress(90, "Finalising …")
    app.processEvents()

    splash.set_progress(100, "Ready.")
    app.processEvents()

    # Small delay so the user sees "Ready." before the window appears
    QTimer.singleShot(350, lambda: (window.show(), splash.finish(window)))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
