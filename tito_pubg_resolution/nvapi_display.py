"""Windows Display Driver & NVIDIA NVAPI backend for Tito PUBG Resolution.

Automatically detects NVIDIA GPU + connected monitor(s), reads all supported
resolutions and refresh rates (60Hz-300Hz), and applies or registers custom
resolutions directly via Windows User32 + NVIDIA NVAPI without launching
NVIDIA Control Panel.
"""

from __future__ import annotations

import ctypes
import math
import os
import subprocess
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Optional

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import winreg

# Win32 Constants
CCHDEVICENAME = 32
CCHFORMNAME = 32

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004

ENUM_CURRENT_SETTINGS = -1
ENUM_REGISTRY_SETTINGS = -2
EDS_RAWMODE = 0x00000002

DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_BITSPERPEL = 0x00040000
DM_DISPLAYFREQUENCY = 0x00400000
DM_DISPLAYFLAGS = 0x00200000
DM_DISPLAYFIXEDOUTPUT = 0x20000000

# Values for DEVMODE.dmDisplayFixedOutput. Windows passes DMDFO_STRETCH to
# the display driver so non-native modes fill the panel instead of letterboxing.
DMDFO_DEFAULT = 0
DMDFO_CENTER = 1
DMDFO_STRETCH = 2

CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
CDS_FULLSCREEN = 0x00000004
CDS_GLOBAL = 0x00000008
CDS_SET_PRIMARY = 0x00000010
CDS_RESET = 0x40000000

DISP_CHANGE_SUCCESSFUL = 0
DISP_CHANGE_RESTART = 1
DISP_CHANGE_FAILED = -1
DISP_CHANGE_BADMODE = -2
DISP_CHANGE_NOTUPDATED = -3
DISP_CHANGE_BADFLAGS = -4
DISP_CHANGE_BADPARAM = -5
DISP_CHANGE_BADDUALVIEW = -6

# NVAPI Function IDs (publicly documented NVAPI query interface IDs)
NVAPI_ID_INITIALIZE = 0x0150E828
NVAPI_ID_UNLOAD = 0xD22BDD7E
NVAPI_ID_GET_INTERFACE_VERSION = 0x01053FA5
NVAPI_ID_SYS_GET_DRIVER_VERSION = 0x2926AAAD
NVAPI_ID_ENUM_PHYSICAL_GPUS = 0xE5AC921F
NVAPI_ID_GPU_GET_FULL_NAME = 0xCEEE8E9F
NVAPI_ID_ENUM_NVIDIA_DISPLAY_HANDLE = 0x9ABDD40D
NVAPI_ID_DISP_GET_DISPLAY_ID_BY_NAME = 0xAE457190
NVAPI_ID_DISP_TRY_CUSTOM_DISPLAY = 0x1F7DB630
NVAPI_ID_DISP_SAVE_CUSTOM_DISPLAY = 0x49882876
NVAPI_ID_DISP_REVERT_CUSTOM_DISPLAY = 0xCBBD40F0


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class POINTL(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class DEVMODE_ORIENTATION(ctypes.Structure):
    _fields_ = [
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
    ]


class DEVMODE_DISPLAY_UNION(ctypes.Union):
    _fields_ = [
        ("dmPosition", POINTL),
        ("orientation", DEVMODE_ORIENTATION),
    ]


class DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * CCHDEVICENAME),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("display", DEVMODE_DISPLAY_UNION),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", wintypes.WCHAR * CCHFORMNAME),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


# NVAPI Structures for Custom Display Timing (NV_CUSTOM_DISPLAY)
class NV_TIMING_INPUT_FLAGS(ctypes.Structure):
    _fields_ = [("raw", ctypes.c_uint32)]


class NV_TIMINGEXT(ctypes.Structure):
    _fields_ = [
        ("flag", ctypes.c_uint32),
        ("rr", ctypes.c_uint16),
        ("rrx1k", ctypes.c_uint32),
        ("aspect", ctypes.c_uint32),
        ("rep", ctypes.c_uint16),
        ("status", ctypes.c_uint32),
        ("name", ctypes.c_char * 40),
    ]


class NV_TIMING(ctypes.Structure):
    _fields_ = [
        ("HVisible", ctypes.c_uint16),
        ("HBorder", ctypes.c_uint16),
        ("HFrontPorch", ctypes.c_uint16),
        ("HSyncWidth", ctypes.c_uint16),
        ("HTotal", ctypes.c_uint16),
        ("HSyncPol", ctypes.c_uint8),
        ("VVisible", ctypes.c_uint16),
        ("VBorder", ctypes.c_uint16),
        ("VFrontPorch", ctypes.c_uint16),
        ("VSyncWidth", ctypes.c_uint16),
        ("VTotal", ctypes.c_uint16),
        ("VSyncPol", ctypes.c_uint8),
        ("interlaced", ctypes.c_uint16),
        ("pclk", ctypes.c_uint32),  # in 10 kHz units
        ("etc", NV_TIMINGEXT),
    ]


class NV_CUSTOM_DISPLAY(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("depth", ctypes.c_uint32),
        ("colorFormat", ctypes.c_uint32),
        ("srcPartition", ctypes.c_float * 4),
        ("xRatio", ctypes.c_float),
        ("yRatio", ctypes.c_float),
        ("timing", NV_TIMING),
        ("hwModeSetOnly", ctypes.c_uint32),
    ]


def make_nv_version(struct_cls: type[ctypes.Structure], ver: int = 1) -> int:
    return ctypes.sizeof(struct_cls) | (ver << 16)


@dataclass
class DisplayMode:
    width: int
    height: int
    refresh_hz: int
    bits_per_pel: int = 32

    @property
    def label(self) -> str:
        return f"{self.width} × {self.height} @ {self.refresh_hz} Hz"


@dataclass
class MonitorInfo:
    device_name: str  # e.g. \\.\DISPLAY1
    friendly_name: str  # e.g. ASUS ROG Swift PG259QN
    adapter_name: str  # e.g. NVIDIA GeForce RTX 4070
    device_id: str
    is_primary: bool
    current_width: int
    current_height: int
    current_hz: int
    native_width: int
    native_height: int
    max_supported_hz: int
    supported_hz_list: list[int] = field(default_factory=list)
    supported_modes: list[DisplayMode] = field(default_factory=list)


@dataclass
class GPUInfo:
    name: str
    vendor: str
    driver_version: str
    is_nvidia: bool
    nvapi_available: bool
    vram_mb: Optional[int] = None


@dataclass
class ApplyResult:
    success: bool
    message: str
    used_nvapi: bool = False
    requires_admin: bool = False
    applied_mode: Optional[DisplayMode] = None


def is_user_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(args: Optional[list[str]] = None) -> bool:
    """Request UAC elevation to register brand-new NVAPI custom timings."""
    if not IS_WINDOWS:
        return False
    exe = sys.executable
    params = " ".join(f'"{a}"' for a in (args or sys.argv[1:]))
    if not getattr(sys, "frozen", False):
        script = os.path.abspath(sys.argv[0])
        params = f'"{script}" {params}'.strip()
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    return int(ret) > 32


def compute_cvt_rb_timing(width: int, height: int, refresh_hz: int) -> NV_TIMING:
    """Compute VESA CVT-RB (Reduced Blanking) v1 timing parameters for NVAPI custom modes."""
    # Standard CVT-RB constants
    h_blank = 160
    h_front_porch = 48
    h_sync_width = 32
    v_front_porch = 3
    v_sync_width = 5  # conservative 16:9 / custom friendly sync width
    min_v_blank_us = 460.0

    # Round width to 8-pixel cell
    h_active = (width // 8) * 8
    h_total = h_active + h_blank

    # Estimate horizontal period
    h_period_est = ((1_000_000.0 / refresh_hz) - min_v_blank_us) / height
    v_blank_lines = max(12, math.floor(min_v_blank_us / h_period_est) + 1)
    v_total = height + v_blank_lines

    # Pixel clock in Hz, rounded to 0.25 MHz step
    pixel_clock_hz = h_total * v_total * refresh_hz
    pixel_clock_10khz = int(round(pixel_clock_hz / 10_000.0))

    timing = NV_TIMING()
    timing.HVisible = h_active
    timing.HBorder = 0
    timing.HFrontPorch = h_front_porch
    timing.HSyncWidth = h_sync_width
    timing.HTotal = h_total
    timing.HSyncPol = 0  # +H / -V standard for CVT-RB

    timing.VVisible = height
    timing.VBorder = 0
    timing.VFrontPorch = v_front_porch
    timing.VSyncWidth = v_sync_width
    timing.VTotal = v_total
    timing.VSyncPol = 1

    timing.interlaced = 0
    timing.pclk = pixel_clock_10khz
    timing.etc.rr = refresh_hz
    timing.etc.rrx1k = refresh_hz * 1000
    timing.etc.name = f"{width}x{height}@{refresh_hz}Hz".encode("ascii", errors="ignore")[:39]
    return timing



class NvApiBridge:
    """Lightweight ctypes wrapper around nvapi64.dll."""

    def __init__(self) -> None:
        self.dll = None
        self.initialized = False
        self._query_fn = None
        self._funcs: dict[int, object] = {}
        self._load()

    def _load(self) -> None:
        if not IS_WINDOWS:
            return

        try:
            self.dll = ctypes.WinDLL("nvapi64.dll")
            query_addr = self.dll.nvapi_QueryInterface
            query_addr.argtypes = [ctypes.c_uint32]
            query_addr.restype = ctypes.c_void_p
            self._query_fn = query_addr

            init_ptr = self._query_fn(NVAPI_ID_INITIALIZE)
            if not init_ptr:
                return

            init_fn = ctypes.CFUNCTYPE(ctypes.c_int)(init_ptr)

            if init_fn() == 0:
                self.initialized = True

        except Exception:
            self.initialized = False

    def _get_func(self, func_id: int, restype, *argtypes):
        if not self.initialized or not self._query_fn:
            return None

        if func_id not in self._funcs:
            ptr = self._query_fn(func_id)

            if not ptr:
                return None

            self._funcs[func_id] = ctypes.CFUNCTYPE(
                restype, *argtypes
            )(ptr)

        return self._funcs[func_id]

    def get_driver_and_gpu(self) -> Optional[tuple[str, str]]:
        """Read NVIDIA GPU name and driver version through NVAPI."""

        if not self.initialized:
            return None

        try:
            get_drv = self._get_func(
                NVAPI_ID_SYS_GET_DRIVER_VERSION,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.POINTER(ctypes.c_char),
            )

            driver_ver = "Unknown"

            if get_drv:
                ver = ctypes.c_uint32(0)
                branch = ctypes.create_string_buffer(64)

                status = get_drv(
                    ctypes.byref(ver),
                    branch,
                )

                if status == 0 and ver.value:
                    driver_ver = f"{ver.value / 100:.2f}"

            enum_gpus = self._get_func(
                NVAPI_ID_ENUM_PHYSICAL_GPUS,
                ctypes.c_int,
                ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(ctypes.c_uint32),
            )

            if not enum_gpus:
                return None

            handles = (ctypes.c_void_p * 64)()
            count = ctypes.c_uint32(0)

            status = enum_gpus(
                handles,
                ctypes.byref(count),
            )

            if status != 0 or count.value == 0:
                return None

            get_name = self._get_func(
                NVAPI_ID_GPU_GET_FULL_NAME,
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_char),
            )

            if not get_name:
                return None

            name_buffer = ctypes.create_string_buffer(64)

            status = get_name(
                handles[0],
                name_buffer,
            )

            if status != 0:
                return None

            gpu_name = name_buffer.value.decode(
                "ascii",
                errors="replace",
            ).strip()

            if not gpu_name:
                return None

            return gpu_name, driver_ver

        except Exception:
            return None

    def get_display_id(
        self, gdi_device_name: str
    ) -> Optional[int]:

        if not self.initialized:
            return None

        fn = self._get_func(
            NVAPI_ID_DISP_GET_DISPLAY_ID_BY_NAME,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_uint32),
        )

        if not fn:
            return None

        display_id = ctypes.c_uint32(0)

        status = fn(
            gdi_device_name.encode("ascii", errors="ignore"),
            ctypes.byref(display_id),
        )

        if status == 0:
            return int(display_id.value)

        return None

    def create_and_save_custom_resolution(
        self,
        gdi_device_name: str,
        width: int,
        height: int,
        refresh_hz: int,
    ) -> tuple[bool, str]:

        if not self.initialized:
            return False, "NVAPI unavailable (nvapi64.dll not initialized)."

        display_id = self.get_display_id(gdi_device_name)

        if display_id is None:
            return False, f"Could not resolve NVAPI displayId for {gdi_device_name}."

        try_fn = self._get_func(
            NVAPI_ID_DISP_TRY_CUSTOM_DISPLAY,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_uint32,
            ctypes.POINTER(NV_CUSTOM_DISPLAY),
        )

        save_fn = self._get_func(
            NVAPI_ID_DISP_SAVE_CUSTOM_DISPLAY,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_uint32,
        )

        if not try_fn or not save_fn:
            return False, "NVAPI custom timing entrypoints not exposed by current driver."

        custom = NV_CUSTOM_DISPLAY()
        custom.version = make_nv_version(NV_CUSTOM_DISPLAY, 1)
        custom.width = width
        custom.height = height
        custom.depth = 32
        custom.colorFormat = 0
        custom.srcPartition = (ctypes.c_float * 4)(
            0.0, 0.0, 1.0, 1.0
        )
        custom.xRatio = 1.0
        custom.yRatio = 1.0
        custom.timing = compute_cvt_rb_timing(
            width, height, refresh_hz
        )
        custom.hwModeSetOnly = 0

        disp_ids = (ctypes.c_uint32 * 1)(display_id)
        arr = (NV_CUSTOM_DISPLAY * 1)(custom)

        status_try = try_fn(disp_ids, 1, arr)

        if status_try != 0:
            return False, (
                f"NvAPI_DISP_TryCustomDisplay failed with code {status_try}."
            )

        status_save = save_fn(disp_ids, 1, 1, 1)

        if status_save != 0:
            return False, (
                f"NvAPI_DISP_SaveCustomDisplay failed with code {status_save}."
            )

        return True, "Custom timing registered through NVIDIA NVAPI."



def _parse_edid_monitor_name_and_max_hz(device_id: str) -> tuple[Optional[str], Optional[int]]:
    """Read monitor friendly model name and max vertical Hz from Windows Registry EDID."""
    if not IS_WINDOWS or not device_id:
        return None, None
    try:
        # Typical DeviceID: MONITOR\AUS27A1\{4d36e96e-e325-11ce-bfc1-08002be10318}\0001
        parts = device_id.split("\\")
        if len(parts) < 2:
            return None, None
        pnp_id = parts[1]
        base_path = rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{pnp_id}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_path) as pnp_key:
            sub_count = winreg.QueryInfoKey(pnp_key)[0]
            for idx in range(sub_count):
                sub_name = winreg.EnumKey(pnp_key, idx)
                edid_path = rf"{base_path}\{sub_name}\Device Parameters"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, edid_path) as dp_key:
                        edid, _ = winreg.QueryValueEx(dp_key, "EDID")
                        if not edid or len(edid) < 128:
                            continue
                        name = None
                        max_hz = None
                        # Parse 4 18-byte detailed descriptor blocks at offsets 54, 72, 90, 108
                        for off in (54, 72, 90, 108):
                            block = edid[off : off + 18]
                            if len(block) < 18:
                                continue
                            if block[0] == 0 and block[1] == 0 and block[2] == 0:
                                tag = block[3]
                                if tag == 0xFC:  # Monitor Name
                                    raw_name = bytes(block[5:18]).split(b"\n")[0]
                                    decoded = raw_name.decode("ascii", errors="ignore").strip()
                                    if decoded:
                                        name = decoded
                                elif tag == 0xFD:  # Monitor Range Limits
                                    # byte 6 = max vertical rate (Hz)
                                    v_max = block[6]
                                    if 50 <= v_max <= 540:
                                        max_hz = int(v_max)
                        return name, max_hz
                except OSError:
                    continue
    except OSError:
        return None, None
    return None, None



def detect_gpu() -> GPUInfo:
    """Detect the actual NVIDIA GPU without relying on the first display adapter."""

    nvapi = NvApiBridge()

    # First try NVAPI.
    try:
        nvapi_res = nvapi.get_driver_and_gpu()
        if nvapi_res:
            gpu_name, driver_version = nvapi_res
            return GPUInfo(
                name=gpu_name,
                vendor="NVIDIA",
                driver_version=driver_version,
                is_nvidia=True,
                nvapi_available=nvapi.initialized,
            )
    except Exception:
        pass

    if not IS_WINDOWS:
        return GPUInfo(
            name="Windows required",
            vendor="Unknown",
            driver_version="Unknown",
            is_nvidia=False,
            nvapi_available=False,
        )

    # Try nvidia-smi.
    smi_paths = (
        "nvidia-smi",
        r"C:\Windows\System32\nvidia-smi.exe",
        r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    )

    for smi_path in smi_paths:
        try:
            output = subprocess.check_output(
                [
                    smi_path,
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).strip()

            if output:
                columns = [item.strip() for item in output.splitlines()[0].split(",")]
                return GPUInfo(
                    name=columns[0],
                    vendor="NVIDIA",
                    driver_version=columns[1] if len(columns) > 1 else "Unknown",
                    is_nvidia=True,
                    nvapi_available=nvapi.initialized,
                    vram_mb=(
                        int(float(columns[2]))
                        if len(columns) > 2 and columns[2]
                        else None
                    ),
                )
        except Exception:
            continue

    # Enumerate all Windows display adapters, not only adapter zero.
    first_adapter = None
    user32 = ctypes.windll.user32

    for index in range(32):
        adapter = DISPLAY_DEVICEW()
        adapter.cb = ctypes.sizeof(DISPLAY_DEVICEW)

        result = user32.EnumDisplayDevicesW(
            None, index, ctypes.byref(adapter), 0
        )

        if not result:
            break

        adapter_name = adapter.DeviceString.strip()

        if not adapter_name:
            continue

        if first_adapter is None:
            first_adapter = adapter_name

        if "nvidia" in adapter_name.lower():
            return GPUInfo(
                name=adapter_name,
                vendor="NVIDIA",
                driver_version="Windows Display Driver",
                is_nvidia=True,
                nvapi_available=nvapi.initialized,
            )

    if first_adapter:
        return GPUInfo(
            name=first_adapter,
            vendor="Other display adapter",
            driver_version="Unknown",
            is_nvidia=False,
            nvapi_available=nvapi.initialized,
        )

    return GPUInfo(
        name="No display adapter detected",
        vendor="Unknown",
        driver_version="Unknown",
        is_nvidia=False,
        nvapi_available=False,
    )



def detect_monitors() -> list[MonitorInfo]:
    """Detect real connected monitors and enumerate Windows-supported modes."""

    if not IS_WINDOWS:
        return []

    user32 = ctypes.windll.user32
    monitors: list[MonitorInfo] = []

    idx = 0
    while True:
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)

        if not user32.EnumDisplayDevicesW(
            None, idx, ctypes.byref(dd), 0
        ):
            break

        idx += 1

        if not (dd.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP):
            continue

        device_name = dd.DeviceName
        adapter_name = dd.DeviceString
        is_primary = bool(
            dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE
        )

        # Detect the physical monitor.
        mon_dd = DISPLAY_DEVICEW()
        mon_dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)

        mon_friendly = "Generic PnP Monitor"
        mon_id = ""

        if user32.EnumDisplayDevicesW(
            device_name, 0, ctypes.byref(mon_dd), 0
        ):
            mon_id = mon_dd.DeviceID
            edid_name, _ = _parse_edid_monitor_name_and_max_hz(mon_id)
            mon_friendly = (
                edid_name or mon_dd.DeviceString or mon_friendly
            )

        # Read current display mode.
        cur_dm = DEVMODEW()
        cur_dm.dmSize = ctypes.sizeof(DEVMODEW)

        cur_w = 0
        cur_h = 0
        cur_hz = 0

        if user32.EnumDisplaySettingsExW(
            device_name,
            ENUM_CURRENT_SETTINGS,
            ctypes.byref(cur_dm),
            0,
        ):
            cur_w = int(cur_dm.dmPelsWidth)
            cur_h = int(cur_dm.dmPelsHeight)
            cur_hz = int(cur_dm.dmDisplayFrequency)

        # Enumerate modes reported by the Windows display driver.
        seen_modes: set[tuple[int, int, int]] = set()
        modes: list[DisplayMode] = []
        hz_set: set[int] = set()

        max_w = cur_w
        max_h = cur_h

        for flags in (EDS_RAWMODE, 0):
            mode_idx = 0
            found_mode = False

            while True:
                dm = DEVMODEW()
                dm.dmSize = ctypes.sizeof(DEVMODEW)

                result = user32.EnumDisplaySettingsExW(
                    device_name,
                    mode_idx,
                    ctypes.byref(dm),
                    flags,
                )

                if not result:
                    break

                mode_idx += 1

                w = int(dm.dmPelsWidth)
                h = int(dm.dmPelsHeight)
                hz = int(dm.dmDisplayFrequency)
                bpp = int(dm.dmBitsPerPel)

                if w <= 0 or h <= 0 or bpp != 32 or hz < 50:
                    continue

                found_mode = True
                key = (w, h, hz)

                if key in seen_modes:
                    continue

                seen_modes.add(key)

                modes.append(
                    DisplayMode(
                        width=w,
                        height=h,
                        refresh_hz=hz,
                        bits_per_pel=bpp,
                    )
                )

                hz_set.add(hz)

                if w * h > max_w * max_h:
                    max_w, max_h = w, h

            # Try standard enumeration if raw enumeration found nothing.
            if found_mode:
                break

        # Keep the actual current mode if the driver did not list it.
        if cur_w > 0 and cur_h > 0 and cur_hz >= 50:
            key = (cur_w, cur_h, cur_hz)

            if key not in seen_modes:
                modes.append(
                    DisplayMode(
                        width=cur_w,
                        height=cur_h,
                        refresh_hz=cur_hz,
                        bits_per_pel=32,
                    )
                )
                hz_set.add(cur_hz)

        modes.sort(
            key=lambda m: (
                m.width * m.height,
                m.refresh_hz,
            ),
            reverse=True,
        )

        max_supported_hz = max(hz_set) if hz_set else cur_hz
        supported_hz = sorted(hz_set)

        monitors.append(
            MonitorInfo(
                device_name=device_name,
                friendly_name=mon_friendly,
                adapter_name=adapter_name,
                device_id=mon_id,
                is_primary=is_primary,
                current_width=cur_w,
                current_height=cur_h,
                current_hz=cur_hz,
                native_width=max_w,
                native_height=max_h,
                max_supported_hz=max_supported_hz,
                supported_hz_list=supported_hz,
                supported_modes=modes,
            )
        )

    monitors.sort(key=lambda m: not m.is_primary)
    return monitors


def _decode_disp_change_error(code: int) -> str:
    mapping = {
        DISP_CHANGE_SUCCESSFUL: "Display settings applied successfully.",
        DISP_CHANGE_RESTART: "Windows requires a restart to apply this display mode.",
        DISP_CHANGE_FAILED: "Display driver failed the specified graphics mode.",
        DISP_CHANGE_BADMODE: "The graphics mode is not supported by the GPU/monitor.",
        DISP_CHANGE_NOTUPDATED: "Unable to write settings to the Windows registry.",
        DISP_CHANGE_BADFLAGS: "Invalid display mode flags were passed.",
        DISP_CHANGE_BADPARAM: "Invalid display parameter passed.",
        DISP_CHANGE_BADDUALVIEW: "Mode change blocked due to DualView configuration.",
    }
    return mapping.get(code, f"Unknown ChangeDisplaySettingsExW error ({code}).")


def apply_resolution(
    device_name: str,
    width: int,
    height: int,
    refresh_hz: int,
    persist: bool = True,
    stretch: bool = False,
) -> ApplyResult:
    """Apply a resolution & refresh rate directly without opening NVIDIA Control Panel.

    1. Checks if (width, height, refresh_hz) is already reported by Windows driver.
    2. If not reported (custom resolution like 1720x1620), registers the CVT-RB timing
       directly into the NVIDIA driver via NVAPI (nvapi64.dll).
    3. Tests and applies the mode using ChangeDisplaySettingsExW.
    """
    if width < 640 or height < 480:
        return ApplyResult(False, "Minimum supported resolution is 640 × 480.")
    if refresh_hz < 60 or refresh_hz > 300:
        return ApplyResult(False, "Refresh rate must be between 60 Hz and 300 Hz.")

    if not IS_WINDOWS:
        return ApplyResult(
            success=True,
            message=f"[Preview Simulation] Applied {width} × {height} @ {refresh_hz} Hz on {device_name}.",
            used_nvapi=True,
            applied_mode=DisplayMode(width, height, refresh_hz),
        )

    user32 = ctypes.windll.user32

    def _try_win32_apply() -> int:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        dm.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY | DM_BITSPERPEL
        if stretch:
            dm.dmFields |= DM_DISPLAYFIXEDOUTPUT
            dm.display.orientation.dmDisplayFixedOutput = DMDFO_STRETCH
        dm.dmPelsWidth = width
        dm.dmPelsHeight = height
        dm.dmDisplayFrequency = refresh_hz
        dm.dmBitsPerPel = 32

        test_code = user32.ChangeDisplaySettingsExW(device_name, ctypes.byref(dm), None, CDS_TEST, None)
        if test_code != DISP_CHANGE_SUCCESSFUL:
            return int(test_code)

        flags = CDS_UPDATEREGISTRY if persist else 0
        res_code = user32.ChangeDisplaySettingsExW(device_name, ctypes.byref(dm), None, flags, None)
        return int(res_code)

    # Attempt 1: Apply directly if Windows/NVIDIA driver already exposes this mode
    code = _try_win32_apply()
    if code == DISP_CHANGE_SUCCESSFUL:
        return ApplyResult(
            success=True,
            message=f"Applied {width} × {height} @ {refresh_hz} Hz directly via Windows Display API.",
            used_nvapi=False,
            applied_mode=DisplayMode(width, height, refresh_hz),
        )

    # Attempt 2: Register custom timing directly in NVIDIA driver via NVAPI
    nvapi = NvApiBridge()
    if nvapi.initialized:
        ok, nv_msg = nvapi.create_and_save_custom_resolution(device_name, width, height, refresh_hz)
        if ok:
            code2 = _try_win32_apply()
            if code2 == DISP_CHANGE_SUCCESSFUL:
                return ApplyResult(
                    success=True,
                    message=f"Registered custom NVIDIA mode and applied {width} × {height} @ {refresh_hz} Hz.",
                    used_nvapi=True,
                    applied_mode=DisplayMode(width, height, refresh_hz),
                )
            return ApplyResult(
                success=False,
                message=f"NVAPI registered mode, but Windows rejected switch: {_decode_disp_change_error(code2)}",
                used_nvapi=True,
                requires_admin=not is_user_admin(),
            )
        return ApplyResult(
            success=False,
            message=f"{nv_msg} ({_decode_disp_change_error(code)})",
            used_nvapi=True,
            requires_admin=not is_user_admin(),
        )

    return ApplyResult(
        success=False,
        message=f"{_decode_disp_change_error(code)} Ensure you are running on an NVIDIA GPU with Administrator privileges.",
        used_nvapi=False,
        requires_admin=not is_user_admin(),
    )
