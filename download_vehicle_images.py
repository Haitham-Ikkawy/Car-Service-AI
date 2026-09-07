#!/usr/bin/env python3
"""
Vehicle Image Downloader for Car Service AI
============================================

Downloads official manufacturer vehicle images, converts to WebP,
and updates the project's image files.

Usage:
    python download_vehicle_images.py                    # Download all models with sourceUrl
    python download_vehicle_images.py --brand Toyota     # Download only Toyota models
    python download_vehicle_images.py --model "CR-V"     # Download only Honda CR-V
    python download_vehicle_images.py --list             # List all models and their status
    python download_vehicle_images.py --validate         # Validate existing images
    python download_vehicle_images.py --convert          # Convert existing JPG to WebP
    python download_vehicle_images.py --missing          # Download only missing images

Requirements:
    pip install Pillow requests

The script reads vehicle-images-manifest.json for source URLs.
Edit that file to add official manufacturer image URLs, then run this script.
"""

import json
import os
import sys
import time
import hashlib
import argparse
from pathlib import Path
from urllib.parse import urlparse, unquote

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

# ─── Configuration ───────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
MANIFEST_PATH = PROJECT_ROOT / "vehicle-images-manifest.json"
VEHICLES_DIR = PROJECT_ROOT / "image" / "vehicles"
LOGOS_DIR = PROJECT_ROOT / "image" / "car_logos"
TARGET_FORMAT = "webp"
QUALITY = 85
MAX_WIDTH = 800
MAX_HEIGHT = 600
TIMEOUT = 30

# ─── Colors ──────────────────────────────────────────────────────
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def colored(text, color):
    return f"{color}{text}{Colors.RESET}"

# ─── Helpers ─────────────────────────────────────────────────────
def model_to_filename(model):
    """Convert model name to filename slug."""
    return model.lower().replace(" ", "-").replace("/", "-")

def brand_to_dirname(brand):
    """Convert brand name to directory name."""
    return brand.lower().replace(" ", "-")

def get_image_path(brand, model):
    """Get the target image path for a model."""
    dirname = brand_to_dirname(brand)
    filename = model_to_filename(model)
    return VEHICLES_DIR / dirname / f"{filename}.{TARGET_FORMAT}"

def get_jpg_path(brand, model):
    """Get the legacy JPG path for a model."""
    dirname = brand_to_dirname(brand)
    filename = model_to_filename(model)
    return VEHICLES_DIR / dirname / f"{filename}.jpg"

def load_manifest():
    """Load the vehicle images manifest."""
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_manifest(data):
    """Save the vehicle images manifest."""
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def download_file(url, dest_path):
    """Download a file from URL to destination path."""
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": urlparse(url).scheme + "://" + urlparse(url).hostname + "/",
    }

    if HAS_REQUESTS:
        resp = requests.get(url, headers=headers, timeout=TIMEOUT, stream=True)
        resp.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    else:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            with open(dest_path, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)

    return dest_path

def convert_to_webp(src_path, dest_path, quality=QUALITY):
    """Convert an image to WebP format."""
    if not HAS_PILLOW:
        print(colored("  Pillow not installed. Install with: pip install Pillow", Colors.YELLOW))
        return False

    src_path = Path(src_path)
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        img = Image.open(src_path)

        # Resize if too large
        if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
            img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)

        # Convert to RGB if necessary (WebP doesn't support palette mode with alpha in some cases)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        img.save(str(dest_path), "WEBP", quality=quality, method=6)
        return True
    except Exception as e:
        print(colored(f"  Convert error: {e}", Colors.RED))
        return False

def optimize_webp(webp_path, quality=QUALITY):
    """Re-compress an existing WebP file for optimal size."""
    if not HAS_PILLOW:
        return False

    webp_path = Path(webp_path)
    try:
        img = Image.open(webp_path)
        if img.width > MAX_WIDTH or img.height > MAX_HEIGHT:
            img.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        img.save(str(webp_path), "WEBP", quality=quality, method=6)
        return True
    except Exception:
        return False

# ─── Commands ────────────────────────────────────────────────────
def cmd_list():
    """List all models and their status."""
    manifest = load_manifest()
    total = 0
    with_url = 0
    downloaded = 0
    missing = 0

    print(colored("\n  Vehicle Image Status", Colors.BOLD))
    print(colored("  " + "=" * 60, Colors.DIM))

    for brand_name, brand_data in manifest["brands"].items():
        brand_dir = brand_to_dirname(brand_name)
        models = brand_data.get("models", {})
        brand_total = len(models)
        brand_downloaded = 0

        for model_name, model_data in models.items():
            total += 1
            webp_path = get_image_path(brand_name, model_name)
            jpg_path = get_jpg_path(brand_name, model_name)
            has_webp = webp_path.exists()
            has_jpg = jpg_path.exists()
            has_url = bool(model_data.get("sourceUrl"))

            if has_url:
                with_url += 1
            if has_webp or has_jpg:
                downloaded += 1
                brand_downloaded += 1
            else:
                missing += 1

        status = colored(f"{brand_downloaded}/{brand_total}", Colors.GREEN if brand_downloaded == brand_total else Colors.YELLOW)
        url_status = ""
        models_with_url = sum(1 for m in models.values() if m.get("sourceUrl"))
        if models_with_url > 0:
            url_status = colored(f" [{models_with_url} URLs]", Colors.CYAN)
        print(f"  {brand_name:<20} {status}{url_status}")

    print(colored("\n  " + "=" * 60, Colors.DIM))
    print(f"  Total models: {total}")
    print(f"  Downloaded:   {colored(str(downloaded), Colors.GREEN)}")
    print(f"  Missing:      {colored(str(missing), Colors.RED)}")
    print(f"  With URLs:    {colored(str(with_url), Colors.CYAN)}")
    print()

def cmd_download(brand_filter=None, model_filter=None, missing_only=False):
    """Download images from manifest URLs."""
    manifest = load_manifest()
    downloaded = 0
    failed = 0
    skipped = 0

    for brand_name, brand_data in manifest["brands"].items():
        if brand_filter and brand_filter.lower() not in brand_name.lower():
            continue

        models = brand_data.get("models", {})
        for model_name, model_data in models.items():
            if model_filter and model_filter.lower() not in model_name.lower():
                continue

            source_url = model_data.get("sourceUrl", "")
            if not source_url:
                skipped += 1
                continue

            webp_path = get_image_path(brand_name, model_name)
            if missing_only and webp_path.exists():
                skipped += 1
                continue

            print(colored(f"\n  Downloading: {brand_name} {model_name}", Colors.BOLD))
            print(f"  Source: {colored(source_url, Colors.DIM)}")

            try:
                # Download to temp file
                temp_path = webp_path.with_suffix(".tmp")
                download_file(source_url, temp_path)

                # Convert to WebP
                if HAS_PILLOW:
                    if convert_to_webp(temp_path, webp_path):
                        temp_path.unlink(missing_ok=True)
                        size_kb = webp_path.stat().st_size / 1024
                        print(colored(f"  Saved: {webp_path.relative_to(PROJECT_ROOT)} ({size_kb:.0f} KB)", Colors.GREEN))
                        model_data["imageSource"] = model_data.get("imageSource") or "Official"
                        downloaded += 1
                    else:
                        temp_path.unlink(missing_ok=True)
                        failed += 1
                else:
                    # No Pillow - save as original format
                    final_path = webp_path.with_suffix(temp_path.suffix)
                    temp_path.rename(final_path)
                    size_kb = final_path.stat().st_size / 1024
                    print(colored(f"  Saved: {final_path.relative_to(PROJECT_ROOT)} ({size_kb:.0f} KB) [no WebP conversion]", Colors.YELLOW))
                    downloaded += 1

                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                print(colored(f"  Failed: {e}", Colors.RED))
                failed += 1

    save_manifest(manifest)
    print(colored("\n  " + "=" * 60, Colors.DIM))
    print(f"  Downloaded: {colored(str(downloaded), Colors.GREEN)}")
    print(f"  Failed:     {colored(str(failed), Colors.RED)}")
    print(f"  Skipped:    {colored(str(skipped), Colors.DIM)}")
    print()

def cmd_convert():
    """Convert existing JPG images to WebP."""
    if not HAS_PILLOW:
        print(colored("  Pillow is required for conversion. Install with: pip install Pillow", Colors.RED))
        return

    converted = 0
    for jpg_path in VEHICLES_DIR.rglob("*.jpg"):
        webp_path = jpg_path.with_suffix(".webp")
        if webp_path.exists():
            continue

        print(colored(f"  Converting: {jpg_path.relative_to(PROJECT_ROOT)}", Colors.CYAN))
        if convert_to_webp(jpg_path, webp_path):
            size_before = jpg_path.stat().st_size / 1024
            size_after = webp_path.stat().st_size / 1024
            savings = (1 - size_after / size_before) * 100 if size_before > 0 else 0
            print(colored(f"  -> {webp_path.name} ({size_after:.0f} KB, {savings:.0f}% smaller)", Colors.GREEN))
            converted += 1
        else:
            print(colored(f"  Failed to convert {jpg_path.name}", Colors.RED))

    print(colored(f"\n  Converted {converted} images to WebP", Colors.GREEN))

def cmd_validate():
    """Validate existing images."""
    if not HAS_PILLOW:
        print(colored("  Pillow is required for validation. Install with: pip install Pillow", Colors.RED))
        return

    manifest = load_manifest()
    valid = 0
    invalid = 0
    empty = 0

    for brand_name, brand_data in manifest["brands"].items():
        for model_name in brand_data.get("models", {}):
            webp_path = get_image_path(brand_name, model_name)
            jpg_path = get_jpg_path(brand_name, model_name)

            img_path = webp_path if webp_path.exists() else (jpg_path if jpg_path.exists() else None)

            if img_path is None:
                empty += 1
                continue

            try:
                with Image.open(img_path) as img:
                    if img.width < 100 or img.height < 60:
                        print(colored(f"  SMALL: {brand_name} {model_name} ({img.width}x{img.height})", Colors.YELLOW))
                        invalid += 1
                    else:
                        valid += 1
            except Exception as e:
                print(colored(f"  CORRUPT: {brand_name} {model_name}: {e}", Colors.RED))
                invalid += 1

    print(colored("\n  Validation Results:", Colors.BOLD))
    print(f"  Valid:   {colored(str(valid), Colors.GREEN)}")
    print(f"  Invalid: {colored(str(invalid), Colors.RED)}")
    print(f"  Missing: {colored(str(empty), Colors.YELLOW)}")
    print()

# ─── Main ────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Vehicle Image Downloader for Car Service AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python download_vehicle_images.py --list             Show all models and status
  python download_vehicle_images.py --download         Download all models with URLs
  python download_vehicle_images.py --download --brand Toyota   Download Toyota only
  python download_vehicle_images.py --download --model "CR-V"   Download Honda CR-V only
  python download_vehicle_images.py --convert          Convert JPGs to WebP
  python download_vehicle_images.py --validate         Check image integrity
  python download_vehicle_images.py --missing          Download only missing images
        """
    )
    parser.add_argument("--list", action="store_true", help="List all models and status")
    parser.add_argument("--download", action="store_true", help="Download images from manifest URLs")
    parser.add_argument("--convert", action="store_true", help="Convert existing JPG to WebP")
    parser.add_argument("--validate", action="store_true", help="Validate existing images")
    parser.add_argument("--missing", action="store_true", help="Download only missing images")
    parser.add_argument("--brand", type=str, help="Filter by brand name")
    parser.add_argument("--model", type=str, help="Filter by model name")

    args = parser.parse_args()

    if not any([args.list, args.download, args.convert, args.validate]):
        parser.print_help()
        return

    print(colored("\n  Car Service AI - Vehicle Image Manager", Colors.BOLD))
    print(colored("  " + "=" * 60, Colors.DIM))

    if args.list:
        cmd_list()
    if args.download:
        cmd_download(args.brand, args.model, args.missing)
    if args.convert:
        cmd_convert()
    if args.validate:
        cmd_validate()

if __name__ == "__main__":
    main()
