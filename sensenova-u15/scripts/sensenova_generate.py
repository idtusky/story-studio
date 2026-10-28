#!/usr/bin/env python3
"""SenseNova U1.5 Image Generation Script (Lite / Fast).

Usage:
  # Text-to-Image (default model: sensenova-u1.5-lite)
  python3 sensenova_generate.py image --prompt "一只白色毛绒绒的海豹宝宝漂浮在平静海面上，柔和晨光，写实摄影风格"

  # Specify size (WxH multiples of 32, 512-4096; or auto / 2K / 4K; or a ratio preset)
  python3 sensenova_generate.py image --prompt "..." --size 2720x1536
  python3 sensenova_generate.py image --prompt "..." --ratio 9:16

  # Fast model (quicker iteration, slightly lower quality)
  python3 sensenova_generate.py image --prompt "..." --model sensenova-u1.5-fast

  # Image editing (img2img): pass public URLs or local file paths (up to 5)
  python3 sensenova_generate.py image --prompt "背景换成冰川" --images ./photo.png
  python3 sensenova_generate.py image --prompt "背景换成冰川" --images "https://example.com/photo.png"

Environment:
  SENSENOVA_API_KEY - Required. sk- key from https://platform.sensenova.cn (控制台 → API Keys)
  SENSENOVA_BASE_URL - Optional. Defaults to https://token.sensenova.cn/v1
"""

import argparse
import base64
import json
import os
import re
import socket
import sys
import time
import urllib.request
from pathlib import Path


# ── .env loader ─────────────────────────────────────────────────────────────
_ENV_LOADED = False


def _load_dotenv() -> None:
    """Load .env from the current dir or parent dirs, then the skill's own dir, one time only."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    cwd = Path.cwd()
    search = [cwd, *cwd.parents, Path(__file__).resolve().parents[1]]
    for candidate in search:
        env_path = candidate / ".env"
        if env_path.is_file():
            break
    else:
        return

    try:
        text = env_path.read_text(encoding="utf-8")
    except Exception:
        return

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^(export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*["\']?(.*?)["\']?\s*$', line)
        if m:
            key, val = m.group(2), m.group(3)
            os.environ.setdefault(key, val)

    print(f"[dotenv] Loaded from {env_path.resolve()}")


# ── Config ──────────────────────────────────────────────────────────────
_load_dotenv()
BASE_URL = os.environ.get("SENSENOVA_BASE_URL", "https://gpt.net.dstyun.com/proxy/sensenova/v1")
API_KEY = os.environ.get("SENSENOVA_API_KEY", "")
DEFAULT_MODEL = "sensenova-u1.5-lite"
MODELS = ["sensenova-u1.5-lite", "sensenova-u1.5-fast"]

# 官方建议分辨率（2K 档 + 4K 档），来自 platform.sensenova.cn/docs
RATIO_PRESETS = {
    "1:1": "2048x2048",
    "16:9": "2720x1536",
    "9:16": "1536x2720",
    "2:3": "1664x2496",
    "3:2": "2496x1664",
}
SIZE_CONSTANTS = {"2K": "2048x2048", "4K": "4096x4096"}
MIME_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp"}


def _headers():
    if not API_KEY:
        print("ERROR: SENSENOVA_API_KEY environment variable is not set.", file=sys.stderr)
        print("Create a key at https://platform.sensenova.cn (控制台 → API Keys), then:", file=sys.stderr)
        print('  export SENSENOVA_API_KEY="sk-xxxxxx"  # or add to .env', file=sys.stderr)
        sys.exit(1)
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _request(path, body):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        print(f"HTTP {e.code}: {error_body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except socket.timeout:
        print("Network error: request timed out.", file=sys.stderr)
        sys.exit(1)


def _download(url, dest_dir, filename=None):
    """Download a file from URL to dest_dir, return local path."""
    if filename:
        dest = Path(dest_dir) / filename
    else:
        name = url.split("/")[-1].split("?")[0]
        if not name:
            name = f"sensenova_output_{int(time.time())}"
        dest = Path(dest_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading to {dest} ...")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return str(dest)


def _to_data_url(source):
    """Turn a local file path into a data:image/...;base64,... URL. URLs pass through."""
    if re.match(r"^https?://", source):
        return source
    path = Path(source).expanduser()
    if not path.is_file():
        print(f"ERROR: Image file not found: {source}", file=sys.stderr)
        sys.exit(1)
    mime = MIME_BY_EXT.get(path.suffix.lower())
    if not mime:
        magic = path.read_bytes()[:12]
        if magic.startswith(b"\x89PNG"):
            mime = "image/png"
        elif magic.startswith(b"\xff\xd8"):
            mime = "image/jpeg"
        elif magic.startswith(b"RIFF") and magic[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            print(f"ERROR: Unsupported image type: {source} (png/jpeg/webp only)", file=sys.stderr)
            sys.exit(1)
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def _validate_size(size):
    """Return a size string safe for the API: auto / 2K / 4K / WxH (32-multiple, 512-4096, ≤3:1)."""
    if size in ("auto", "2K", "4K"):
        return size
    m = re.match(r"^(\d+)[xX](\d+)$", size)
    if not m:
        print(f"ERROR: Invalid size '{size}'. Use auto / 2K / 4K / WIDTHxHEIGHT.", file=sys.stderr)
        sys.exit(1)
    w, h = int(m.group(1)), int(m.group(2))

    def clamp(v):
        v = max(512, min(4096, v))
        return int(round(v / 32)) * 32

    if w % 32 or h % 32 or not (512 <= w <= 4096) or not (512 <= h <= 4096):
        fixed = f"{clamp(w)}x{clamp(h)}"
        print(f"WARNING: size must be multiples of 32 within 512-4096; "
              f"auto-adjusting {size} -> {fixed}.", file=sys.stderr)
        w, h = clamp(w), clamp(h)

    if max(w, h) / min(w, h) > 3:
        print(f"ERROR: Aspect ratio {w}x{h} exceeds the max 3:1 (or 1:3).", file=sys.stderr)
        sys.exit(1)
    return f"{w}x{h}"


# ── Image Generation / Editing ──────────────────────────────────────────
def generate_image(prompt, model=None, size=None, ratio=None, images=None,
                   output_format="png", response_format="b64_json", watermark=False,
                   prompt_extend=True, output_dir="/tmp", filename=None, save_local=True):
    """Generate or edit an image via SenseNova U1.5.

    Text-only prompt  -> POST /images/generations
    With --images     -> POST /images/edits (first image is the primary; up to 5)

    size defaults to 2048x2048 for generation, auto (adapts to the primary
    image) for editing. response_format defaults to b64_json here (API
    default) so the image never depends on the 24-hour temporary URL;
    'url' mode downloads immediately.
    """
    model = model or DEFAULT_MODEL
    if model not in MODELS:
        print(f"WARNING: unknown model '{model}', using {DEFAULT_MODEL}.", file=sys.stderr)
        model = DEFAULT_MODEL

    if size is None:
        size = "auto" if images else "2048x2048"

    if ratio:
        if ratio not in RATIO_PRESETS:
            print(f"ERROR: --ratio must be one of {list(RATIO_PRESETS)}.", file=sys.stderr)
            sys.exit(1)
        if size not in ("auto", "2048x2048"):
            print(f"NOTE: --ratio overrides --size ({size} -> {RATIO_PRESETS[ratio]}).", file=sys.stderr)
        size = RATIO_PRESETS[ratio]
    size = _validate_size(size)

    is_edit = bool(images)
    body = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "output_format": output_format,
        "response_format": response_format,
        "watermark": watermark,
        "prompt_extend": prompt_extend,
    }

    if is_edit:
        urls = [_to_data_url(s) for s in (images if isinstance(images, list) else [images])]
        if len(urls) > 5:
            print("ERROR: At most 5 reference images are supported.", file=sys.stderr)
            sys.exit(1)
        body["images"] = [{"image_url": u} for u in urls]
        print(f"{'Editing' if len(urls) == 1 else 'Compositing'} image "
              f"(model={model}, refs={len(urls)}, size={size}) ...")
    else:
        print(f"Generating image (model={model}, size={size}) ...")

    result = _request("/images/edits" if is_edit else "/images/generations", body)

    if not result.get("data"):
        print("ERROR: No image data in response.", file=sys.stderr)
        print(json.dumps(result, indent=2, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    item = result["data"][0]
    b64_data = item.get("b64_json")
    image_url = item.get("url")

    if save_local:
        if b64_data:
            ext = {"jpeg": "jpg"}.get(output_format, output_format)
            dest = Path(output_dir) / (filename or f"sensenova_{int(time.time())}.{ext}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(base64.b64decode(b64_data))
            local_path = str(dest)
            print(f"Saved image to {local_path}")
        elif image_url:
            local_path = _download(image_url, output_dir, filename)
        else:
            print("ERROR: No image URL or base64 data in response.", file=sys.stderr)
            sys.exit(1)
        output = {"local_path": local_path, "model": model, "size": result.get("size", size)}
        if image_url:
            output["url"] = image_url
    else:
        output = {"model": model, "size": result.get("size", size)}
        if image_url:
            output["url"] = image_url

    usage = result.get("usage") or {}
    if usage:
        output["usage"] = {k: usage[k] for k in
                           ("input_tokens", "output_tokens", "total_tokens", "images_count")
                           if k in usage}

    print(json.dumps(output, ensure_ascii=False))
    return output


# ── CLI ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="SenseNova U1.5 Image Generator")
    sub = parser.add_subparsers(dest="command", required=True)

    img = sub.add_parser("image", help="Generate or edit an image")
    img.add_argument("--prompt", "-p", required=True,
                     help="Image description / edit instruction")
    img.add_argument("--model", "-m", default=DEFAULT_MODEL,
                     help=f"Model: {DEFAULT_MODEL} (quality) or sensenova-u1.5-fast (speed)")
    img.add_argument("--size", "-s", default=None,
                     help="auto / 2K / 4K / WIDTHxHEIGHT (32-multiple, 512-4096, ≤3:1). "
                          "Default: 2048x2048 for generation, auto (adapts to primary "
                          "image) for editing. Ignored when --ratio is given.")
    img.add_argument("--ratio", "-r", choices=sorted(RATIO_PRESETS), default=None,
                     help="Aspect ratio preset (2K tier), overrides --size")
    img.add_argument("--images", "-i", nargs="+", default=None,
                     help="Reference image(s) for editing: public URL(s) or local file "
                          "path(s), max 5; first one is the primary image")
    img.add_argument("--output-format", choices=["png", "jpeg", "webp"], default="png",
                     help="Image file format (default: png)")
    img.add_argument("--response-format", choices=["b64_json", "url"], default="b64_json",
                     help="b64_json (default, most reliable) or url (24h temporary link, "
                          "auto-downloaded)")
    img.add_argument("--watermark", action="store_true",
                     help="Add SenseNova logo watermark (default: no watermark, free in beta)")
    img.add_argument("--no-extend", action="store_true",
                     help="Disable prompt auto-polish (prompt_extend=false)")
    img.add_argument("--output-dir", "-o", default="/tmp",
                     help="Directory to save generated files (default: /tmp)")
    img.add_argument("--filename", "-f", default=None,
                     help="Save as output-dir/filename (auto-creates subdirs)")
    img.add_argument("--no-save", action="store_true",
                     help="Don't download, only return URL (requires --response-format url)")

    args = parser.parse_args()

    if args.command == "image":
        generate_image(
            prompt=args.prompt,
            model=args.model,
            size=args.size,
            ratio=args.ratio,
            images=args.images,
            output_format=args.output_format,
            response_format=args.response_format,
            watermark=args.watermark,
            prompt_extend=not args.no_extend,
            output_dir=args.output_dir,
            filename=args.filename,
            save_local=not args.no_save,
        )


if __name__ == "__main__":
    main()
