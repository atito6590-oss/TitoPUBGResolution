"""Generate transparent rounded-shield Windows .ico and .png from PUBG soldier artwork."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw


def get_assets_dir() -> Path:
    """Resolve assets directory both in development and inside PyInstaller bundle."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


def _apply_squircle_alpha_mask(img: Image.Image) -> Image.Image:
    """Remove outer white corners from the generated icon artwork using a clean rounded-shield mask."""
    rgba = img.convert("RGBA")
    w, h = rgba.size

    # Create anti-aliased rounded square mask matching the emblem outer bevel
    scale = 4
    mask_hi = Image.new("L", (w * scale, h * scale), 0)
    draw = ImageDraw.Draw(mask_hi)
    pad = int(w * scale * 0.015)
    radius = int(w * scale * 0.22)
    draw.rounded_rectangle(
        [pad, pad, w * scale - pad, h * scale - pad],
        radius=radius,
        fill=255,
    )
    mask = mask_hi.resize((w, h), Image.Resampling.LANCZOS)

    # Also knock out near-white border pixels outside the shield if any remain
    pixels = rgba.load()
    mask_px = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            m = mask_px[x, y]
            if r > 240 and g > 240 and b > 240 and (x < w * 0.14 or x > w * 0.86 or y < h * 0.14 or y > h * 0.86):
                m = 0
            pixels[x, y] = (r, g, b, min(a, m))
    return rgba


def _draw_fallback_soldier_icon(size: int = 512) -> Image.Image:
    """Vector-style Pillow fallback emblem if source artwork is absent."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(size * 0.04)
    radius = int(size * 0.22)
    # Dark obsidian shield
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=(14, 16, 20, 255),
        outline=(242, 169, 0, 255),
        width=max(4, size // 32),
    )
    # Level 3 helmet silhouette
    cx, cy = size // 2, int(size * 0.44)
    hw, hh = int(size * 0.25), int(size * 0.24)
    draw.ellipse([cx - hw, cy - hh, cx + hw, cy + hh], fill=(42, 48, 58, 255), outline=(242, 169, 0, 255), width=max(2, size // 64))
    # Ballistic visor
    vw, vh = int(size * 0.20), int(size * 0.09)
    draw.rounded_rectangle([cx - vw, cy - vh // 2, cx + vw, cy + vh], radius=max(4, size // 40), fill=(12, 14, 18, 255), outline=(242, 169, 0, 220), width=max(2, size // 80))
    # Crosshair accent
    draw.ellipse([cx - size // 18, cy + size // 4 - size // 18, cx + size // 18, cy + size // 4 + size // 18], outline=(242, 169, 0, 255), width=max(2, size // 64))
    return img


def ensure_icon_files() -> tuple[Path, Path]:
    """Ensure assets/pubg_soldier.png and assets/pubg_soldier.ico exist and return their paths."""
    assets_dir = get_assets_dir()
    assets_dir.mkdir(parents=True, exist_ok=True)

    ico_path = assets_dir / "pubg_soldier.ico"
    png_path = assets_dir / "pubg_soldier.png"
    jpg_path = assets_dir / "pubg_soldier.jpg"

    if ico_path.exists() and png_path.exists():
        return ico_path, png_path

    if jpg_path.exists():
        raw = Image.open(jpg_path)
        rgba = _apply_squircle_alpha_mask(raw)
    elif png_path.exists():
        rgba = Image.open(png_path).convert("RGBA")
    else:
        rgba = _draw_fallback_soldier_icon(512)

    rgba.save(png_path, format="PNG")
    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    rgba.save(ico_path, format="ICO", sizes=icon_sizes)
    return ico_path, png_path


if __name__ == "__main__":
    ico, png = ensure_icon_files()
    print(f"Generated PNG: {png}")
    print(f"Generated ICO: {ico}")
