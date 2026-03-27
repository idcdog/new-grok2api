#!/usr/bin/env python3
"""Generate images through the project's Web Imagine SSE endpoint and save them locally."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ENDPOINT = "/v1/function/imagine/sse"
DEFAULT_TIMEOUT = 120
DEFAULT_ASPECT_RATIO = "2:3"
DEFAULT_IMAGE_COUNT = 1
ASPECT_RATIO_PATTERN = re.compile(r"^\d+:\d+$")

SIZE_TO_ASPECT = {
    "1280x720": "16:9",
    "720x1280": "9:16",
    "1792x1024": "3:2",
    "1024x1792": "2:3",
    "1024x1024": "1:1",
}


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"Config file must contain an object: {path}")
    return data


def _read_config(config_path: Path) -> dict[str, Any]:
    config = _load_json(config_path)
    skill_dir = Path(__file__).resolve().parent.parent
    default_output_dir = skill_dir / "output"
    return {
        "base_url": _first_non_empty(
            os.environ.get("GROK_BASE_URL"),
            config.get("base_url", ""),
        ),
        "function_key": _first_non_empty(
            os.environ.get("GROK_FUNCTION_KEY"),
            os.environ.get("GROK_API_KEY"),
            config.get("function_key", ""),
            config.get("api_key", ""),
        ),
        "image_endpoint": _first_non_empty(
            os.environ.get("GROK_IMAGE_ENDPOINT"),
            config.get("image_endpoint", DEFAULT_ENDPOINT),
        ),
        "timeout_seconds": int(
            _first_non_empty(
                os.environ.get("GROK_TIMEOUT_SECONDS"),
                config.get("timeout_seconds", DEFAULT_TIMEOUT),
            )
        ),
        "output_dir": _first_non_empty(
            os.environ.get("GROK_OUTPUT_DIR"),
            config.get("output_dir", str(default_output_dir)),
        ),
    }


def _resolve_output_dir(raw_output_dir: str, config_path: Path) -> Path:
    output_dir = Path(raw_output_dir).expanduser()
    if output_dir.is_absolute():
        return output_dir
    return (config_path.parent / output_dir).resolve()


def _join_url(base_url: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _preview(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _parse_args() -> argparse.Namespace:
    skill_dir = Path(__file__).resolve().parent.parent
    default_config_path = skill_dir / "config" / "local.json"

    parser = argparse.ArgumentParser(
        description="Generate images through the project's Web Imagine SSE endpoint"
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--count", type=int, default=DEFAULT_IMAGE_COUNT)
    parser.add_argument("--aspect-ratio", default="")
    parser.add_argument("--size", default="")
    parser.add_argument("--nsfw", choices=("true", "false"), default="true")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--config", default=str(default_config_path))
    return parser.parse_args()


def _resolve_aspect_ratio(raw_aspect_ratio: str, raw_size: str) -> str:
    aspect_ratio = raw_aspect_ratio.strip()
    if aspect_ratio:
        if not ASPECT_RATIO_PATTERN.match(aspect_ratio):
            raise SystemExit("aspect_ratio must look like WIDTH:HEIGHT, for example 2:3")
        return aspect_ratio

    size = raw_size.strip()
    if not size:
        return DEFAULT_ASPECT_RATIO
    if size not in SIZE_TO_ASPECT:
        raise SystemExit(
            "size must be one of "
            f"{sorted(SIZE_TO_ASPECT)} when used with the Imagine SSE skill"
        )
    return SIZE_TO_ASPECT[size]


def _validate_args(args: argparse.Namespace) -> None:
    if not args.prompt.strip():
        raise SystemExit("Prompt must not be empty")
    if args.count <= 0:
        raise SystemExit("count must be greater than 0")
    _resolve_aspect_ratio(args.aspect_ratio, args.size)


def _guess_ext(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "webp"
    return "jpg"


def _save_image(output_dir: Path, prompt: str, index: int, blob: str) -> Path:
    raw = base64.b64decode(blob)
    ext = _guess_ext(raw)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", prompt.strip()).strip("-").lower() or "image"
    slug = slug[:40].rstrip("-") or "image"
    filename = f"{time.strftime('%Y%m%d-%H%M%S')}-{slug}-{index:02d}.{ext}"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / filename
    target.write_bytes(raw)
    return target


def _parse_sse_data(response: Any):
    data_lines: list[str] = []
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line:
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines = []
                yield payload
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if data_lines:
        yield "\n".join(data_lines)


def main() -> int:
    args = _parse_args()
    _validate_args(args)

    config_path = Path(args.config).expanduser().resolve()
    config = _read_config(config_path)

    base_url = str(config["base_url"]).strip()
    function_key = str(config["function_key"]).strip()
    image_endpoint = str(config["image_endpoint"]).strip()
    timeout_seconds = int(config["timeout_seconds"])
    output_dir = _resolve_output_dir(
        args.output_dir.strip() or str(config["output_dir"]).strip(),
        config_path,
    )
    aspect_ratio = _resolve_aspect_ratio(args.aspect_ratio, args.size)
    nsfw = "true" if args.nsfw == "true" else "false"

    if not base_url:
        raise SystemExit("Missing GROK_BASE_URL or config.base_url")
    if not image_endpoint:
        raise SystemExit("Missing image endpoint")

    query = {
        "prompt": args.prompt,
        "aspect_ratio": aspect_ratio,
        "nsfw": nsfw,
    }
    if function_key:
        query["function_key"] = function_key

    url = f"{_join_url(base_url, image_endpoint)}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(
        url=url,
        headers={"Accept": "text/event-stream"},
        method="GET",
    )

    saved_paths: list[Path] = []
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            for payload_text in _parse_sse_data(response):
                if payload_text == "[DONE]":
                    break
                try:
                    payload = json.loads(payload_text)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue

                if payload.get("type") == "error" or payload.get("error"):
                    message = payload.get("message") or payload.get("error") or "Unknown error"
                    raise SystemExit(f"Imagine SSE error: {_preview(str(message))}")

                blob = payload.get("b64_json")
                if not blob:
                    continue

                saved_paths.append(
                    _save_image(output_dir, args.prompt, len(saved_paths) + 1, blob)
                )
                if len(saved_paths) >= args.count:
                    break
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {_preview(raw)}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed: {exc}") from exc

    if not saved_paths:
        raise SystemExit("No images were produced before the stream ended")

    result = {
        "prompt": args.prompt,
        "aspect_ratio": aspect_ratio,
        "count": len(saved_paths),
        "output_dir": str(output_dir.resolve()),
        "files": [str(path.resolve()) for path in saved_paths],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
