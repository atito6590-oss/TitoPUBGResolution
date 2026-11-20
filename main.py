"""Entry point for Tito PUBG Resolution desktop application."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from tito_pubg_resolution import __app_name__
from tito_pubg_resolution.icon_gen import ensure_icon_files
from tito_pubg_resolution.nvapi_display import apply_resolution, detect_monitors
from tito_pubg_resolution.profiles import load_original_snapshot, load_profiles
from tito_pubg_resolution.theme import PUBG_QSS
from tito_pubg_resolution.ui_main import KeepChangesDialog, MainWindow


def _run_cli_action(args: argparse.Namespace) -> int:
    """Handle profile shortcut execution and display confirmation before keeping a mode."""
    app = QApplication(sys.argv)
    app.setStyleSheet(PUBG_QSS)

    if args.restore:
        snap = load_original_snapshot()
        if not snap:
            QMessageBox.warning(None, __app_name__, "No original display snapshot found yet.")
            return 1
        res = apply_resolution(snap.device_name, snap.width, snap.height, snap.refresh_hz, persist=True)
        if not res.success:
            QMessageBox.warning(None, __app_name__, res.message)
            return 1
        return 0

    if args.apply_profile:
        monitors = detect_monitors()
        if not monitors:
            QMessageBox.warning(None, __app_name__, "No active display was detected.")
            return 1
        default_mon = monitors[0]
        profiles = load_profiles(default_mon.device_name, default_mon.max_supported_hz)
        match = next((p for p in profiles if p.name.lower() == args.apply_profile.lower()), None)
        if not match:
            QMessageBox.warning(None, __app_name__, f"Profile '{args.apply_profile}' not found.")
            return 1
        previous = next(
            (monitor for monitor in monitors if monitor.device_name == match.device_name),
            default_mon,
        )
        res = apply_resolution(
            match.device_name,
            match.width,
            match.height,
            match.refresh_hz,
            persist=True,
            stretch=True,
        )
        if not res.success:
            QMessageBox.warning(None, __app_name__, res.message)
            return 1
        language = str(QSettings("Tito", "PUBGResolution").value("language", "en"))
        dialog = KeepChangesDialog(match.width, match.height, match.refresh_hz, language=language)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return 0
        restored = apply_resolution(
            previous.device_name,
            previous.current_width,
            previous.current_height,
            previous.current_hz,
            persist=True,
        )
        if not restored.success:
            QMessageBox.warning(None, __app_name__, f"Automatic restore failed: {restored.message}")
            return 1
        return 1

    return -1


def main() -> int:
    parser = argparse.ArgumentParser(description=__app_name__)
    parser.add_argument("--apply-profile", type=str, help="Apply a saved resolution profile immediately")
    parser.add_argument("--restore", action="store_true", help="Restore original display settings immediately")
    args, unknown = parser.parse_known_args()

    if args.restore or args.apply_profile:
        return _run_cli_action(args)

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication([sys.argv[0], *unknown])
    app.setApplicationName(__app_name__)
    app.setStyle("Fusion")
    app.setStyleSheet(PUBG_QSS)

    ensure_icon_files()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
