"""PySide6 Main Window, Safety Confirmation Dialog, and System Tray for Tito PUBG Resolution."""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QStatusBar,
    QSystemTrayIcon,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __app_name__, __version__
from .icon_gen import ensure_icon_files
from .nvapi_display import (
    GPUInfo,
    MonitorInfo,
    apply_resolution,
    detect_gpu,
    detect_monitors,
    is_user_admin,
    relaunch_as_admin,
)
from .profiles import (
    OriginalDisplaySnapshot,
    ResolutionProfile,
    create_desktop_shortcut,
    load_profiles,
    save_original_snapshot_if_missing,
    save_profiles,
    update_original_snapshot,
)
from .theme import enable_windows_dark_titlebar


class KeepChangesDialog(QDialog):
    """15-second auto-revert confirmation dialog protecting against unsupported timings."""

    def __init__(self, width: int, height: int, hz: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm Display Settings")
        self.setModal(True)
        self.setFixedSize(440, 210)
        self.remaining = 15

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"Keep {width} × {height} at {hz} Hz?")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        self.countdown_label = QLabel(
            f"Reverting to previous display settings automatically in {self.remaining} seconds."
        )
        self.countdown_label.setWordWrap(True)
        self.countdown_label.setObjectName("MutedMeta")
        layout.addWidget(self.countdown_label)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        revert_btn = QPushButton("Revert Now")
        revert_btn.clicked.connect(self.reject)

        keep_btn = QPushButton("Keep Changes")
        keep_btn.setObjectName("PrimaryBtn")
        keep_btn.setDefault(True)
        keep_btn.clicked.connect(self.accept)

        btn_row.addWidget(revert_btn)
        btn_row.addWidget(keep_btn)
        layout.addLayout(btn_row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

    def _tick(self) -> None:
        self.remaining -= 1
        if self.remaining <= 0:
            self.timer.stop()
            self.reject()
            return
        self.countdown_label.setText(
            f"Reverting to previous display settings automatically in {self.remaining} seconds."
        )


class MainWindow(QMainWindow):
    """Main desktop interface for Tito PUBG Resolution."""

    STANDARD_HZ_CHIPS = [60, 75, 100, 120, 144, 165, 180, 240, 280, 300]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(__app_name__)
        self.setMinimumSize(1020, 720)
        self.resize(1120, 780)

        ico_path, png_path = ensure_icon_files()
        self.app_icon = QIcon(str(ico_path))
        self.setWindowIcon(self.app_icon)
        self.png_path = png_path

        self.gpu_info: GPUInfo = detect_gpu()
        self.monitors: list[MonitorInfo] = detect_monitors()
        self.current_monitor: MonitorInfo = self.monitors[0]
        self.baseline: OriginalDisplaySnapshot = save_original_snapshot_if_missing(self.current_monitor)
        self.profiles: list[ResolutionProfile] = load_profiles(
            default_device=self.current_monitor.device_name,
            default_max_hz=self.current_monitor.max_supported_hz,
        )

        self._build_ui()
        self._build_tray()
        self._sync_monitor_state()

        enable_windows_dark_titlebar(int(self.winId()))

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("CentralRoot")
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Tactical Top Header ──────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("TacticalHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 14, 20, 14)
        header_layout.setSpacing(14)

        icon_label = QLabel()
        pix = QPixmap(str(self.png_path)).scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pix)
        icon_label.setFixedSize(44, 44)
        header_layout.addWidget(icon_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_lbl = QLabel(__app_name__)
        title_lbl.setObjectName("AppTitle")
        subtitle_lbl = QLabel(
            f"v{__version__}  ·  Direct NVIDIA Custom Resolution & Refresh Rate Controller"
        )
        subtitle_lbl.setObjectName("MutedMeta")
        title_col.addWidget(title_lbl)
        title_col.addWidget(subtitle_lbl)
        header_layout.addLayout(title_col)

        header_layout.addStretch()

        if not is_user_admin():
            admin_btn = QPushButton("Run as Admin")
            admin_btn.setToolTip("Elevate privileges so NVAPI can register brand-new custom timings")
            admin_btn.clicked.connect(self._handle_elevate)
            header_layout.addWidget(admin_btn)

        refresh_hw_btn = QPushButton("Rescan Hardware")
        refresh_hw_btn.clicked.connect(self._rescan_hardware)
        header_layout.addWidget(refresh_hw_btn)

        self.restore_btn = QPushButton("Restore Original Display")
        self.restore_btn.setObjectName("DangerBtn")
        self.restore_btn.clicked.connect(self._restore_original_display)
        header_layout.addWidget(self.restore_btn)

        main_layout.addWidget(header)

        # ── Body Content Area ────────────────────────────────────────────────
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 18, 20, 14)
        body_layout.setSpacing(16)

        # 1. Hardware Detection Strip
        hw_panel = QFrame()
        hw_panel.setObjectName("PanelCard")
        hw_grid = QGridLayout(hw_panel)
        hw_grid.setContentsMargins(16, 14, 16, 14)
        hw_grid.setHorizontalSpacing(24)
        hw_grid.setVerticalSpacing(6)

        hw_grid.addWidget(self._muted_label("DETECTED GPU"), 0, 0)
        hw_grid.addWidget(self._muted_label("ACTIVE MONITOR"), 0, 1)
        hw_grid.addWidget(self._muted_label("CURRENT MODE"), 0, 2)
        hw_grid.addWidget(self._muted_label("ORIGINAL BASELINE"), 0, 3)

        self.gpu_value_lbl = QLabel()
        self.gpu_value_lbl.setObjectName("MonoValue")
        hw_grid.addWidget(self.gpu_value_lbl, 1, 0)

        self.monitor_combo = QComboBox()
        self.monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)
        hw_grid.addWidget(self.monitor_combo, 1, 1)

        self.current_mode_lbl = QLabel()
        self.current_mode_lbl.setObjectName("MonoValue")
        hw_grid.addWidget(self.current_mode_lbl, 1, 2)

        baseline_row = QHBoxLayout()
        baseline_row.setSpacing(8)
        self.baseline_lbl = QLabel()
        self.baseline_lbl.setObjectName("MonoValue")
        set_base_btn = QPushButton("Set Current")
        set_base_btn.setToolTip("Save current active resolution as your new baseline restore target")
        set_base_btn.clicked.connect(self._set_current_as_baseline)
        baseline_row.addWidget(self.baseline_lbl)
        baseline_row.addWidget(set_base_btn)
        hw_grid.addLayout(baseline_row, 1, 3)

        body_layout.addWidget(hw_panel)

        # 2. Split Workspace: Left Controls (Presets + Custom Resolution & Hz) | Right Tabs (Profiles + Modes)
        split = QHBoxLayout()
        split.setSpacing(16)

        # ── Left Column ──
        left_col = QVBoxLayout()
        left_col.setSpacing(14)

        # Presets Card
        preset_panel = QFrame()
        preset_panel.setObjectName("PanelCard")
        preset_layout = QVBoxLayout(preset_panel)
        preset_layout.setContentsMargins(16, 14, 16, 14)
        preset_layout.setSpacing(10)

        p_heading = QLabel("PUBG COMPETITIVE PRESETS")
        p_heading.setObjectName("SectionHeading")
        preset_layout.addWidget(p_heading)

        preset_cards_row = QHBoxLayout()
        preset_cards_row.setSpacing(10)

        preset_cards_row.addWidget(
            self._build_preset_card(
                "1720 × 1620",
                "Pro Stretched (1.06:1)",
                "Wider horizontal player models with crisp vertical visibility.",
                1720,
                1620,
            )
        )
        preset_cards_row.addWidget(
            self._build_preset_card(
                "1920 × 1440",
                "4:3 Competitive HD",
                "High-density 4:3 stretched resolution for sharp mid-range tracking.",
                1920,
                1440,
            )
        )
        preset_layout.addLayout(preset_cards_row)
        left_col.addWidget(preset_panel)

        # Custom Resolution & Refresh Rate Card
        custom_panel = QFrame()
        custom_panel.setObjectName("PanelCard")
        custom_layout = QVBoxLayout(custom_panel)
        custom_layout.setContentsMargins(16, 14, 16, 14)
        custom_layout.setSpacing(12)

        c_heading = QLabel("CUSTOM RESOLUTION & REFRESH RATE")
        c_heading.setObjectName("SectionHeading")
        custom_layout.addWidget(c_heading)

        dim_grid = QGridLayout()
        dim_grid.setHorizontalSpacing(12)
        dim_grid.setVerticalSpacing(6)

        dim_grid.addWidget(self._muted_label("Width (px)"), 0, 0)
        dim_grid.addWidget(self._muted_label("Height (px)"), 0, 1)
        dim_grid.addWidget(self._muted_label("Aspect Ratio"), 0, 2)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(640, 7680)
        self.width_spin.setValue(1720)
        self.width_spin.valueChanged.connect(self._update_aspect_preview)
        dim_grid.addWidget(self.width_spin, 1, 0)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(480, 4320)
        self.height_spin.setValue(1620)
        self.height_spin.valueChanged.connect(self._update_aspect_preview)
        dim_grid.addWidget(self.height_spin, 1, 1)

        self.aspect_lbl = QLabel("86:81 (1.06)")
        self.aspect_lbl.setObjectName("MonoValue")
        dim_grid.addWidget(self.aspect_lbl, 1, 2)

        custom_layout.addLayout(dim_grid)

        # Refresh Rate Section (60Hz to 300Hz where monitor allows)
        hz_header = QHBoxLayout()
        self.hz_title_lbl = QLabel("Refresh Rate (60 Hz – 300 Hz)")
        self.hz_title_lbl.setObjectName("MutedMeta")
        self.hz_cap_lbl = QLabel()
        self.hz_cap_lbl.setObjectName("MutedMeta")
        hz_header.addWidget(self.hz_title_lbl)
        hz_header.addStretch()
        hz_header.addWidget(self.hz_cap_lbl)
        custom_layout.addLayout(hz_header)

        hz_slider_row = QHBoxLayout()
        hz_slider_row.setSpacing(10)
        self.hz_slider = QSlider(Qt.Horizontal)
        self.hz_slider.setRange(60, 300)
        self.hz_slider.setValue(144)
        self.hz_slider.valueChanged.connect(self._on_hz_slider_changed)

        self.hz_spin = QSpinBox()
        self.hz_spin.setRange(60, 300)
        self.hz_spin.setSuffix(" Hz")
        self.hz_spin.setValue(144)
        self.hz_spin.valueChanged.connect(self._on_hz_spin_changed)

        hz_slider_row.addWidget(self.hz_slider, 1)
        hz_slider_row.addWidget(self.hz_spin)
        custom_layout.addLayout(hz_slider_row)

        self.hz_chip_grid = QGridLayout()
        self.hz_chip_grid.setSpacing(6)
        self.hz_chips: dict[int, QPushButton] = {}
        for idx, hz_val in enumerate(self.STANDARD_HZ_CHIPS):
            chip = QPushButton(f"{hz_val} Hz")
            chip.setObjectName("HzChip")
            chip.setCheckable(True)
            chip.clicked.connect(lambda _checked=False, v=hz_val: self._select_hz(v))
            self.hz_chips[hz_val] = chip
            self.hz_chip_grid.addWidget(chip, idx // 5, idx % 5)
        custom_layout.addLayout(self.hz_chip_grid)

        # Action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.apply_btn = QPushButton("Apply Resolution Now")
        self.apply_btn.setObjectName("PrimaryBtn")
        self.apply_btn.setMinimumHeight(40)
        self.apply_btn.clicked.connect(self._apply_current_inputs)

        save_profile_btn = QPushButton("Save as Profile")
        save_profile_btn.setMinimumHeight(40)
        save_profile_btn.clicked.connect(self._save_current_as_profile)

        action_row.addWidget(self.apply_btn, 2)
        action_row.addWidget(save_profile_btn, 1)
        custom_layout.addLayout(action_row)

        left_col.addWidget(custom_panel)
        left_col.addStretch()

        split.addLayout(left_col, 5)

        # ── Right Column: Tabs for Saved Profiles & Supported Hardware Modes ──
        tabs = QTabWidget()

        # Tab 1: Profiles & Desktop Shortcuts
        prof_tab = QWidget()
        prof_layout = QVBoxLayout(prof_tab)
        prof_layout.setContentsMargins(14, 14, 14, 14)
        prof_layout.setSpacing(10)

        new_prof_row = QHBoxLayout()
        new_prof_row.setSpacing(8)
        self.profile_name_input = QLineEdit()
        self.profile_name_input.setPlaceholderText("Profile name (e.g. PUBG Ranked 1720x1620)")
        add_prof_btn = QPushButton("Save Current")
        add_prof_btn.clicked.connect(self._save_current_as_profile)
        new_prof_row.addWidget(self.profile_name_input, 1)
        new_prof_row.addWidget(add_prof_btn)
        prof_layout.addLayout(new_prof_row)

        self.profiles_table = QTableWidget(0, 4)
        self.profiles_table.setHorizontalHeaderLabels(["Profile Name", "Resolution", "Refresh", "Target"])
        self.profiles_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.profiles_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.profiles_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.profiles_table.verticalHeader().setVisible(False)
        self.profiles_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        prof_layout.addWidget(self.profiles_table, 1)

        prof_actions = QHBoxLayout()
        prof_actions.setSpacing(8)

        apply_prof_btn = QPushButton("Apply Selected")
        apply_prof_btn.setObjectName("PrimaryBtn")
        apply_prof_btn.clicked.connect(self._apply_selected_profile)

        shortcut_btn = QPushButton("Create Desktop Shortcut")
        shortcut_btn.clicked.connect(self._create_shortcut_for_selected)

        restore_sc_btn = QPushButton("Create Restore Shortcut")
        restore_sc_btn.clicked.connect(self._create_restore_shortcut)

        del_prof_btn = QPushButton("Delete")
        del_prof_btn.setObjectName("DangerBtn")
        del_prof_btn.clicked.connect(self._delete_selected_profile)

        prof_actions.addWidget(apply_prof_btn)
        prof_actions.addWidget(shortcut_btn)
        prof_actions.addWidget(restore_sc_btn)
        prof_actions.addWidget(del_prof_btn)
        prof_layout.addLayout(prof_actions)

        tabs.addTab(prof_tab, "Saved Profiles & Shortcuts")

        # Tab 2: Supported Hardware Modes
        modes_tab = QWidget()
        modes_layout = QVBoxLayout(modes_tab)
        modes_layout.setContentsMargins(14, 14, 14, 14)
        modes_layout.setSpacing(10)

        filter_row = QHBoxLayout()
        self.modes_filter_input = QLineEdit()
        self.modes_filter_input.setPlaceholderText("Filter supported modes (e.g. 1920, 1440, 240)")
        self.modes_filter_input.textChanged.connect(self._populate_modes_table)
        load_mode_btn = QPushButton("Load into Editor")
        load_mode_btn.clicked.connect(self._load_selected_hardware_mode)
        filter_row.addWidget(self.modes_filter_input, 1)
        filter_row.addWidget(load_mode_btn)
        modes_layout.addLayout(filter_row)

        self.modes_table = QTableWidget(0, 4)
        self.modes_table.setHorizontalHeaderLabels(["Width", "Height", "Refresh Rate", "Color Depth"])
        self.modes_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.modes_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.modes_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.modes_table.verticalHeader().setVisible(False)
        self.modes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.modes_table.doubleClicked.connect(self._load_selected_hardware_mode)
        modes_layout.addWidget(self.modes_table, 1)

        tabs.addTab(modes_tab, "Supported Monitor Modes")

        split.addWidget(tabs, 6)
        body_layout.addLayout(split, 1)
        main_layout.addWidget(body, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. NVIDIA display driver and monitor modes loaded.")

    def _build_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self.app_icon, self)
        self.tray_icon.setToolTip(__app_name__)

        menu = QMenu(self)
        show_act = QAction("Open Tito PUBG Resolution", self)
        show_act.triggered.connect(self.showNormal)
        menu.addAction(show_act)

        restore_act = QAction("Restore Original Display Settings", self)
        restore_act.triggered.connect(self._restore_original_display)
        menu.addAction(restore_act)

        menu.addSeparator()
        quit_act = QAction("Exit", self)
        quit_act.triggered.connect(self.close)
        menu.addAction(quit_act)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _muted_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("MutedMeta")
        return lbl

    def _build_preset_card(self, title: str, badge: str, desc: str, w: int, h: int) -> QFrame:
        card = QFrame()
        card.setObjectName("PresetCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        t_lbl = QLabel(title)
        t_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #F8FAFC; font-family: Consolas;")
        b_lbl = QLabel(badge)
        b_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #F2A900;")
        d_lbl = QLabel(desc)
        d_lbl.setWordWrap(True)
        d_lbl.setObjectName("MutedMeta")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(lambda _c=False, width=w, height=h: self._load_preset(width, height, apply_now=False))
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("PrimaryBtn")
        apply_btn.clicked.connect(lambda _c=False, width=w, height=h: self._load_preset(width, height, apply_now=True))
        btn_row.addWidget(load_btn)
        btn_row.addWidget(apply_btn)

        lay.addWidget(t_lbl)
        lay.addWidget(b_lbl)
        lay.addWidget(d_lbl, 1)
        lay.addLayout(btn_row)
        return card

    def _sync_monitor_state(self) -> None:
        nvapi_tag = "NVAPI Ready" if self.gpu_info.nvapi_available else "WDDM Mode"
        self.gpu_value_lbl.setText(f"{self.gpu_info.name} ({self.gpu_info.driver_version} · {nvapi_tag})")

        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        for mon in self.monitors:
            primary_tag = " [Primary]" if mon.is_primary else ""
            self.monitor_combo.addItem(f"{mon.friendly_name}{primary_tag}", mon.device_name)
        self.monitor_combo.blockSignals(False)

        self._refresh_active_monitor_labels()
        self._populate_profiles_table()
        self._populate_modes_table()
        self._update_aspect_preview()

    def _refresh_active_monitor_labels(self) -> None:
        mon = self.current_monitor
        self.current_mode_lbl.setText(f"{mon.current_width} × {mon.current_height} @ {mon.current_hz} Hz")
        self.baseline_lbl.setText(f"{self.baseline.width} × {self.baseline.height} @ {self.baseline.refresh_hz} Hz")

        max_hz = max(60, min(300, mon.max_supported_hz))
        self.hz_slider.setRange(60, max_hz)
        self.hz_spin.setRange(60, max_hz)
        self.hz_cap_lbl.setText(f"Monitor Max Allowed: {max_hz} Hz")

        for hz_val, chip in self.hz_chips.items():
            allowed = hz_val <= max_hz
            chip.setEnabled(allowed)
            if not allowed:
                chip.setToolTip(f"Exceeds {mon.friendly_name} max supported {max_hz} Hz")
            else:
                chip.setToolTip(f"Set refresh rate to {hz_val} Hz")

        target_hz = min(self.hz_spin.value(), max_hz)
        self._select_hz(target_hz)

    def _on_monitor_changed(self, index: int) -> None:
        if 0 <= index < len(self.monitors):
            self.current_monitor = self.monitors[index]
            self._refresh_active_monitor_labels()
            self._populate_modes_table()

    def _rescan_hardware(self) -> None:
        self.gpu_info = detect_gpu()
        self.monitors = detect_monitors()
        self.current_monitor = self.monitors[0]
        self._sync_monitor_state()
        self.status_bar.showMessage("Hardware rescanned successfully.")

    def _update_aspect_preview(self) -> None:
        w = self.width_spin.value()
        h = self.height_spin.value()
        g = math.gcd(w, h) or 1
        ratio = w / h
        self.aspect_lbl.setText(f"{w // g}:{h // g} ({ratio:.2f}:1)")

    def _on_hz_slider_changed(self, val: int) -> None:
        self.hz_spin.blockSignals(True)
        self.hz_spin.setValue(val)
        self.hz_spin.blockSignals(False)
        self._sync_hz_chips(val)

    def _on_hz_spin_changed(self, val: int) -> None:
        self.hz_slider.blockSignals(True)
        self.hz_slider.setValue(val)
        self.hz_slider.blockSignals(False)
        self._sync_hz_chips(val)

    def _select_hz(self, val: int) -> None:
        val = max(60, min(self.hz_spin.maximum(), val))
        self.hz_slider.setValue(val)
        self.hz_spin.setValue(val)
        self._sync_hz_chips(val)

    def _sync_hz_chips(self, val: int) -> None:
        for hz_val, chip in self.hz_chips.items():
            chip.blockSignals(True)
            chip.setChecked(hz_val == val)
            chip.blockSignals(False)

    def _load_preset(self, width: int, height: int, apply_now: bool) -> None:
        self.width_spin.setValue(width)
        self.height_spin.setValue(height)
        if apply_now:
            self._apply_resolution_with_guard(width, height, self.hz_spin.value())

    def _apply_current_inputs(self) -> None:
        self._apply_resolution_with_guard(
            self.width_spin.value(),
            self.height_spin.value(),
            self.hz_spin.value(),
        )

    def _apply_resolution_with_guard(self, width: int, height: int, hz: int) -> None:
        prev_w = self.current_monitor.current_width
        prev_h = self.current_monitor.current_height
        prev_hz = self.current_monitor.current_hz
        device = self.current_monitor.device_name

        result = apply_resolution(device, width, height, hz, persist=True)
        if not result.success:
            if result.requires_admin:
                reply = QMessageBox.question(
                    self,
                    "Administrator Privileges Required",
                    f"{result.message}\n\nRestart Tito PUBG Resolution as Administrator to register this custom resolution via NVAPI?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes and relaunch_as_admin():
                    self.close()
                return
            QMessageBox.warning(self, "Could Not Apply Resolution", result.message)
            self.status_bar.showMessage(f"Error: {result.message}")
            return

        dlg = KeepChangesDialog(width, height, hz, self)
        if dlg.exec() == QDialog.Accepted:
            self._rescan_hardware()
            self.status_bar.showMessage(result.message)
        else:
            apply_resolution(device, prev_w, prev_h, prev_hz, persist=True)
            self._rescan_hardware()
            self.status_bar.showMessage(f"Reverted to {prev_w} × {prev_h} @ {prev_hz} Hz.")

    def _restore_original_display(self) -> None:
        snap = self.baseline
        res = apply_resolution(snap.device_name, snap.width, snap.height, snap.refresh_hz, persist=True)
        if res.success:
            self._rescan_hardware()
            self.status_bar.showMessage(
                f"Restored original display: {snap.width} × {snap.height} @ {snap.refresh_hz} Hz."
            )
        else:
            QMessageBox.warning(self, "Restore Failed", res.message)

    def _set_current_as_baseline(self) -> None:
        self.baseline = update_original_snapshot(self.current_monitor)
        self._refresh_active_monitor_labels()
        self.status_bar.showMessage("Updated baseline display snapshot to current mode.")

    def _populate_profiles_table(self) -> None:
        self.profiles_table.setRowCount(len(self.profiles))
        for row, prof in enumerate(self.profiles):
            self.profiles_table.setItem(row, 0, QTableWidgetItem(prof.name))
            self.profiles_table.setItem(row, 1, QTableWidgetItem(f"{prof.width} × {prof.height}"))
            self.profiles_table.setItem(row, 2, QTableWidgetItem(f"{prof.refresh_hz} Hz"))
            self.profiles_table.setItem(row, 3, QTableWidgetItem(prof.device_name))

    def _populate_modes_table(self) -> None:
        query = self.modes_filter_input.text().strip().lower()
        filtered = [
            m
            for m in self.current_monitor.supported_modes
            if not query or query in f"{m.width}x{m.height} {m.width} {m.height} {m.refresh_hz}hz".lower()
        ]
        self.modes_table.setRowCount(len(filtered))
        for row, mode in enumerate(filtered):
            self.modes_table.setItem(row, 0, QTableWidgetItem(str(mode.width)))
            self.modes_table.setItem(row, 1, QTableWidgetItem(str(mode.height)))
            self.modes_table.setItem(row, 2, QTableWidgetItem(f"{mode.refresh_hz} Hz"))
            self.modes_table.setItem(row, 3, QTableWidgetItem(f"{mode.bits_per_pel}-bit"))

    def _load_selected_hardware_mode(self) -> None:
        row = self.modes_table.currentRow()
        if row < 0:
            return
        w = int(self.modes_table.item(row, 0).text())
        h = int(self.modes_table.item(row, 1).text())
        hz = int(self.modes_table.item(row, 2).text().replace(" Hz", ""))
        self.width_spin.setValue(w)
        self.height_spin.setValue(h)
        self._select_hz(hz)
        self.status_bar.showMessage(f"Loaded {w} × {h} @ {hz} Hz into editor.")

    def _save_current_as_profile(self) -> None:
        w = self.width_spin.value()
        h = self.height_spin.value()
        hz = self.hz_spin.value()
        name = self.profile_name_input.text().strip() or f"PUBG {w}x{h} {hz}Hz"

        new_prof = ResolutionProfile(
            name=name,
            width=w,
            height=h,
            refresh_hz=hz,
            device_name=self.current_monitor.device_name,
            is_preset=False,
        )
        self.profiles = [p for p in self.profiles if p.name.lower() != name.lower()]
        self.profiles.insert(0, new_prof)
        save_profiles(self.profiles)
        self.profile_name_input.clear()
        self._populate_profiles_table()
        self.status_bar.showMessage(f"Saved profile '{name}'.")

    def _apply_selected_profile(self) -> None:
        row = self.profiles_table.currentRow()
        if row < 0 or row >= len(self.profiles):
            QMessageBox.information(self, "Select Profile", "Select a saved profile first.")
            return
        prof = self.profiles[row]
        self.width_spin.setValue(prof.width)
        self.height_spin.setValue(prof.height)
        self._select_hz(prof.refresh_hz)
        self._apply_resolution_with_guard(prof.width, prof.height, prof.refresh_hz)

    def _delete_selected_profile(self) -> None:
        row = self.profiles_table.currentRow()
        if row < 0 or row >= len(self.profiles):
            return
        removed = self.profiles.pop(row)
        save_profiles(self.profiles)
        self._populate_profiles_table()
        self.status_bar.showMessage(f"Deleted profile '{removed.name}'.")

    def _create_shortcut_for_selected(self) -> None:
        row = self.profiles_table.currentRow()
        if row < 0 or row >= len(self.profiles):
            QMessageBox.information(self, "Select Profile", "Select a profile to create a desktop shortcut.")
            return
        prof = self.profiles[row]
        ok, msg = create_desktop_shortcut(
            shortcut_title=prof.name,
            cli_args=f'--apply-profile "{prof.name}"',
            description=f"Apply {prof.width}x{prof.height} @ {prof.refresh_hz}Hz via Tito PUBG Resolution",
        )
        if ok:
            QMessageBox.information(self, "Desktop Shortcut Created", msg)
            self.status_bar.showMessage(msg)
        else:
            QMessageBox.warning(self, "Shortcut Failed", msg)

    def _create_restore_shortcut(self) -> None:
        ok, msg = create_desktop_shortcut(
            shortcut_title="Restore Display - Tito PUBG",
            cli_args="--restore",
            description="Restore original display settings via Tito PUBG Resolution",
        )
        if ok:
            QMessageBox.information(self, "Restore Shortcut Created", msg)
            self.status_bar.showMessage(msg)
        else:
            QMessageBox.warning(self, "Shortcut Failed", msg)

    def _handle_elevate(self) -> None:
        if relaunch_as_admin():
            self.close()
