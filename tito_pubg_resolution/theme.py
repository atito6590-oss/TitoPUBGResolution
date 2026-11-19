"""PUBG-inspired tactical dark theme QSS & Windows dark titlebar integration."""

from __future__ import annotations

import ctypes
import sys

PUBG_QSS = """
QMainWindow, QDialog {
    background-color: #0E1014;
    color: #E8EAED;
    font-family: "Segoe UI", "Bahnschrift", sans-serif;
    font-size: 13px;
}

QWidget#CentralRoot {
    background-color: #0E1014;
}

QFrame#TacticalHeader {
    background-color: #14171D;
    border-bottom: 1px solid #262B36;
}

QFrame#PanelCard {
    background-color: #161920;
    border: 1px solid #262B36;
    border-radius: 6px;
}

QFrame#PresetCard {
    background-color: #1B1F28;
    border: 1px solid #2C3240;
    border-radius: 6px;
}

QFrame#PresetCard:hover {
    border: 1px solid #F2A900;
    background-color: #202530;
}

QLabel#AppTitle {
    font-size: 18px;
    font-weight: 700;
    color: #F8FAFC;
    letter-spacing: 0.4px;
}

QLabel#SectionHeading {
    font-size: 13px;
    font-weight: 700;
    color: #F2A900;
    letter-spacing: 0.6px;
}

QLabel#MutedMeta {
    font-size: 12px;
    color: #949BA8;
}

QLabel#MonoValue {
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 13px;
    font-weight: 700;
    color: #F8FAFC;
}

QPushButton {
    background-color: #222733;
    color: #E8EAED;
    border: 1px solid #323949;
    border-radius: 5px;
    padding: 7px 14px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #2A303E;
    border-color: #495368;
}

QPushButton:pressed {
    background-color: #1B1F29;
}

QPushButton#PrimaryBtn {
    background-color: #F2A900;
    color: #0E1014;
    border: 1px solid #F2A900;
    font-weight: 700;
}

QPushButton#PrimaryBtn:hover {
    background-color: #FFBA1A;
    border-color: #FFBA1A;
}

QPushButton#PrimaryBtn:pressed {
    background-color: #D89400;
}

QPushButton#DangerBtn {
    background-color: #2A1618;
    color: #F87171;
    border: 1px solid #5C262B;
}

QPushButton#DangerBtn:hover {
    background-color: #3B1D20;
    border-color: #EF4444;
}

QPushButton#HzChip {
    background-color: #1A1E26;
    color: #CBD5E1;
    border: 1px solid #2D3442;
    padding: 5px 10px;
    font-family: "Consolas", monospace;
    font-weight: 600;
}

QPushButton#HzChip:checked {
    background-color: #F2A900;
    color: #0E1014;
    border-color: #F2A900;
}

QPushButton#HzChip:disabled {
    background-color: #12151B;
    color: #474F5E;
    border-color: #1F242E;
}

QLineEdit, QSpinBox, QComboBox {
    background-color: #101318;
    color: #F8FAFC;
    border: 1px solid #2D3442;
    border-radius: 5px;
    padding: 6px 10px;
    font-family: "Consolas", "Segoe UI", monospace;
    font-size: 13px;
}

QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #F2A900;
}

QSlider::groove:horizontal {
    height: 6px;
    background: #232834;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: #F2A900;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #F8FAFC;
    border: 2px solid #F2A900;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}

QTableWidget, QListWidget {
    background-color: #11141A;
    color: #E2E8F0;
    border: 1px solid #262B36;
    border-radius: 5px;
    gridline-color: #1E232D;
    selection-background-color: #2B2514;
    selection-color: #F2A900;
}

QHeaderView::section {
    background-color: #181C24;
    color: #949BA8;
    border: none;
    border-bottom: 1px solid #262B36;
    padding: 6px 10px;
    font-weight: 600;
    font-size: 12px;
}

QTabWidget::pane {
    border: 1px solid #262B36;
    background-color: #161920;
    border-radius: 6px;
}

QTabBar::tab {
    background-color: #14171D;
    color: #949BA8;
    padding: 8px 16px;
    border: 1px solid #262B36;
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    margin-right: 4px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background-color: #161920;
    color: #F2A900;
    border-top: 2px solid #F2A900;
}

QStatusBar {
    background-color: #12151B;
    color: #949BA8;
    border-top: 1px solid #262B36;
}
"""


def enable_windows_dark_titlebar(hwnd: int) -> None:
    """Enable native Windows 10/11 dark window frame via DwmSetWindowAttribute."""
    if sys.platform != "win32":
        return
    try:
        dwmapi = ctypes.windll.dwmapi
        value = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win10 2004+ / Win11), fallback 19
        for attr in (20, 19):
            dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(attr),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        pass
