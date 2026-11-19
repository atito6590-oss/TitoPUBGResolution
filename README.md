# Tito PUBG Resolution

Professional Windows 10/11 desktop utility built with **Python** and **PySide6** for competitive PUBG resolution and high-refresh-rate management on NVIDIA GPUs — without needing to open the NVIDIA Control Panel.

## Key Features

- **Automatic Hardware Detection**: Identifies your NVIDIA GeForce GPU (driver version, bus info) and connected gaming monitor model (via Windows Display API + Registry EDID parsing).
- **Supported Modes & Refresh Rate Discovery**: Reads every hardware-supported resolution and refresh rate (`60 Hz` up to `300 Hz`) directly from the Windows display driver.
- **Competitive Presets**: One-click presets for **`1720x1620`** (Pro Stretched) and **`1920x1440`** (4:3 Crisp High-Res), plus custom width and height input.
- **Direct NVIDIA Custom Resolution Registration**: Uses **NVAPI (`nvapi64.dll`)** with CVT-RB timing calculation and `ChangeDisplaySettingsExW` to register and apply custom resolutions directly without opening NVIDIA Control Panel.
- **15-Second Auto-Revert Safety Guard**: Automatically restores your previous display mode if you do not confirm within 15 seconds.
- **Saved Profiles & Desktop Shortcuts**: Save custom resolution + refresh rate profiles and generate `.lnk` Windows Desktop shortcuts (featuring the custom PUBG Soldier icon) to switch modes or restore settings in one click.
- **One-Click Restore**: Saves your original baseline display settings on first launch and restores them anytime from the main window, system tray, or `--restore` CLI flag.

## Running from Source (Windows 10/11)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m tito_pubg_resolution.icon_gen
python main.py
```

> **Note**: Registering brand-new custom resolutions via NVAPI requires Administrator privileges. Running as Administrator (enabled automatically in the compiled EXE via `uac_admin=True`) ensures seamless custom timing creation.

## Building Standalone Windows EXE

Double-click `build_exe.bat` or run:

```bat
python -m tito_pubg_resolution.icon_gen
pyinstaller --clean --noconfirm TitoPUBGResolution.spec
```

The standalone executable will be generated at:

`dist\TitoPUBGResolution.exe`

## CLI Arguments (Used by Desktop Shortcuts)

- `TitoPUBGResolution.exe --apply-profile "1720x1620 Competitive"` — Applies a saved profile directly.
- `TitoPUBGResolution.exe --restore` — Restores original display settings immediately.
