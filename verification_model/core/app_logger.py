"""
AppLogger — application-level singleton logger.

Usage:
    from core.app_logger import AppLogger
    log = AppLogger.instance()
    log.ok("Chip output loaded: frame_001.txt")
    log.error("Parse error: unexpected token on line 14")

Signals:
    sig_entry(level: str, line: str)  — emitted on every new entry
"""

from __future__ import annotations
import datetime

from PyQt6.QtCore import QObject, pyqtSignal


class AppLogger(QObject):
    """Singleton application logger with Qt signal support."""

    sig_entry = pyqtSignal(str, str)   # (level, formatted_line)

    _instance: AppLogger | None = None

    @classmethod
    def instance(cls) -> AppLogger:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._entries: list[tuple[str, str, str]] = []   # (ts, level, msg)

    # ── Public API ────────────────────────────────────────────────────────────

    def info(self, msg: str)  -> None:  self._log("INFO",  msg)
    def ok(self,   msg: str)  -> None:  self._log("OK",    msg)
    def warn(self, msg: str)  -> None:  self._log("WARN",  msg)
    def error(self, msg: str) -> None:  self._log("ERROR", msg)

    def all_lines(self) -> list[str]:
        return [self._fmt(ts, lv, msg) for ts, lv, msg in self._entries]

    def export_to_file(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.all_lines()) + "\n")

    def clear(self) -> None:
        self._entries.clear()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _log(self, level: str, msg: str) -> None:
        ts   = datetime.datetime.now().strftime("%H:%M:%S")
        line = self._fmt(ts, level, msg)
        self._entries.append((ts, level, msg))
        self.sig_entry.emit(level, line)

    @staticmethod
    def _fmt(ts: str, level: str, msg: str) -> str:
        return f"[{ts}]  {level:<5}  {msg}"
