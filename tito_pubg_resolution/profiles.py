"""Profile storage, original display snapshot, and Windows desktop shortcut creator."""

from __future__ import annotations

import json
import base64
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from .icon_gen import ensure_icon_files
from .nvapi_display import MonitorInfo

IS_WINDOWS = sys.platform == "win32"


@dataclass
class ResolutionProfile:
    name: str
    width: int
    height: int
    refresh_hz: int
    device_name: str
    is_preset: bool = False


@dataclass
class OriginalDisplaySnapshot:
    device_name: str
    width: int
    height: int
    refresh_hz: int


def get_config_dir() -> Path:
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path.home() / ".config"
    cfg_dir = base / "TitoPUBGResolution"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def get_profiles_file() -> Path:
    return get_config_dir() / "profiles.json"


def get_baseline_file() -> Path:
    return get_config_dir() / "original_display.json"


def load_profiles(default_device: str = r"\\.\DISPLAY1", default_max_hz: int = 144) -> list[ResolutionProfile]:
    """Load saved profiles, seeding the two competitive PUBG presets on first launch."""
    path = get_profiles_file()
    if not path.exists():
        presets = [
            ResolutionProfile(
                name="PUBG 1720x1620 Stretched",
                width=1720,
                height=1620,
                refresh_hz=min(240, default_max_hz),
                device_name=default_device,
                is_preset=True,
            ),
            ResolutionProfile(
                name="PUBG 1920x1440 4:3 High-Res",
                width=1920,
                height=1440,
                refresh_hz=min(240, default_max_hz),
                device_name=default_device,
                is_preset=True,
            ),
        ]
        save_profiles(presets)
        return presets

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [ResolutionProfile(**item) for item in raw]
    except Exception:
        return []


def save_profiles(profiles: list[ResolutionProfile]) -> None:
    path = get_profiles_file()
    payload = [asdict(p) for p in profiles]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def save_original_snapshot_if_missing(monitor: MonitorInfo) -> OriginalDisplaySnapshot:
    """Capture original baseline display settings once so user can always restore."""
    path = get_baseline_file()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return OriginalDisplaySnapshot(**data)
        except Exception:
            pass

    snap = OriginalDisplaySnapshot(
        device_name=monitor.device_name,
        width=monitor.current_width,
        height=monitor.current_height,
        refresh_hz=monitor.current_hz,
    )
    path.write_text(json.dumps(asdict(snap), indent=2), encoding="utf-8")
    return snap


def update_original_snapshot(monitor: MonitorInfo) -> OriginalDisplaySnapshot:
    """Explicitly update the saved baseline to the current monitor configuration."""
    snap = OriginalDisplaySnapshot(
        device_name=monitor.device_name,
        width=monitor.current_width,
        height=monitor.current_height,
        refresh_hz=monitor.current_hz,
    )
    get_baseline_file().write_text(json.dumps(asdict(snap), indent=2), encoding="utf-8")
    return snap


def load_original_snapshot() -> Optional[OriginalDisplaySnapshot]:
    path = get_baseline_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return OriginalDisplaySnapshot(**data)
    except Exception:
        return None


def _get_desktop_dir() -> Path:
    if IS_WINDOWS:
        # Query actual Desktop folder (supports OneDrive Desktop redirection)
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
                text=True,
                timeout=4,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()
            if out and Path(out).exists():
                return Path(out)
        except Exception:
            pass
    return Path.home() / "Desktop"


def create_desktop_shortcut(
    shortcut_title: str,
    cli_args: str,
    description: str = "Tito PUBG Resolution Profile Shortcut",
) -> tuple[bool, str]:
    """Create a real Windows .lnk Desktop Shortcut using the custom PUBG Soldier icon."""
    ico_path, _ = ensure_icon_files()
    desktop = _get_desktop_dir()
    safe_name = "".join(ch for ch in shortcut_title if ch.isalnum() or ch in (" ", "-", "_", "x")).strip()
    if not safe_name:
        safe_name = "Tito PUBG Resolution"
    lnk_path = desktop / f"{safe_name}.lnk"

    if getattr(sys, "frozen", False):
        target_exe = sys.executable
        arguments = cli_args
        working_dir = str(Path(sys.executable).parent)
    else:
        python_exe = Path(sys.executable)
        pythonw = python_exe.with_name("pythonw.exe")
        target_exe = str(pythonw if pythonw.exists() else python_exe)
        main_py = str(Path(__file__).resolve().parent.parent / "main.py")
        arguments = f'"{main_py}" {cli_args}'.strip()
        working_dir = str(Path(main_py).parent)

    if not IS_WINDOWS:
        return True, f"[Preview Simulation] Shortcut would be created at: {lnk_path}"

    # Copy icon to persistent AppData location so shortcuts stay valid even if temp dirs move
    persistent_ico = get_config_dir() / "pubg_soldier.ico"
    try:
        persistent_ico.write_bytes(ico_path.read_bytes())
        icon_loc = f"{persistent_ico},0"
    except Exception:
        icon_loc = f"{ico_path},0"

    def _ps_escape(val: str) -> str:
        return val.replace("'", "''")

    ps_script = "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "$ws = New-Object -ComObject WScript.Shell",
            f"$sc = $ws.CreateShortcut('{_ps_escape(str(lnk_path))}')",
            f"$sc.TargetPath = '{_ps_escape(target_exe)}'",
            f"$sc.Arguments = '{_ps_escape(arguments)}'",
            f"$sc.WorkingDirectory = '{_ps_escape(working_dir)}'",
            f"$sc.IconLocation = '{_ps_escape(icon_loc)}'",
            f"$sc.Description = '{_ps_escape(description)}'",
            "$sc.Save()",
            f"if (-not (Test-Path -LiteralPath '{_ps_escape(str(lnk_path))}')) {{ throw 'Shortcut file was not created.' }}",
        ]
    )
    encoded_script = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")

    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_script],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or f"PowerShell exited with code {completed.returncode}").strip()
            return False, f"Failed to create desktop shortcut: {detail}"
        if not lnk_path.is_file():
            return False, f"PowerShell finished without creating the shortcut: {lnk_path}"
        return True, f"Desktop shortcut created: {lnk_path}"
    except Exception as exc:
        return False, f"Failed to create desktop shortcut: {exc}"
