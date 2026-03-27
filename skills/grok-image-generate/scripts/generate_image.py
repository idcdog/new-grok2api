#!/usr/bin/env python3
"""Generate images through a configured Grok-compatible API."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "grok-imagine-1.0"
DEFAULT_ENDPOINT = "/v1/images/generations"
DEFAULT_TIMEOUT = 120
VALID_RESPONSE_FORMATS = {"url", "b64_json", "base64"}
SIZE_PATTERN = re.compile(r"^\d+x\d+$")


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
    return {
        "base_url": os.environ.get("GROK_BASE_URL") or config.get("base_url", ""),
        "api_key": os.environ.get("GROK_API_KEY") or config.get("api_key", ""),
        "image_endpoint": os.environ.get("GROK_IMAGE_ENDPOINT")
        or config.get("image_endpoint", DEFAULT_ENDPOINT),
        "model": os.environ.get("GROK_IMAGE_MODEL") or config.get("model", DEFAULT_MODEL),
        "timeout_seconds": int(
            os.environ.get("GROK_TIMEOUT_SECONDS")
            or config.get("timeout_seconds", DEFAULT_TIMEOUT)
        ),
    }


def _join_url(base_url: str, endpoint: str) -> str:
    return f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"


def _preview(text: str, limit: int = 500) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated)"


def _parse_args() -> argparse.Namespace:
    skill_dir = Path(__file__).resolve().parent.parent
    default_config_path = skill_dir / "config" / "local.json"

    parser = argparse.ArgumentParser(description="Generate images with Grok-compatible API")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--size", default="1024x1024")
    parser.add_argument("--response-format", default="url")
    parser.add_argument("--config", default=str(default_config_path))
    return parser.parse_args()


def _validate_args(args: argparse.Namespace) -> None:
    if not args.prompt.strip():
        raise SystemExit("Prompt must not be empty")
    if args.n <= 0:
        raise SystemExit("n must be greater than 0")
    if args.response_format not in VALID_RESPONSE_FORMATS:
        raise SystemExit(
            f"response_format must be one of {sorted(VALID_RESPONSE_FORMATS)}"
        )
    if not SIZE_PATTERN.match(args.size):
        raise SystemExit("size must look like WIDTHxHEIGHT, for example 1024x1024")


def main() -> int:
    args = _parse_args()
    _validate_args(args)

    config_path = Path(args.config).expanduser().resolve()
    config = _read_config(config_path)

    base_url = str(config["base_url"]).strip()
    api_key = str(config["api_key"]).strip()
    image_endpoint = str(config["image_endpoint"]).strip()
    model = str(config["model"]).strip() or DEFAULT_MODEL
    timeout_seconds = int(config["timeout_seconds"])

    if not base_url:
        raise SystemExit("Missing GROK_BASE_URL or config.base_url")
    if not api_key:
        raise SystemExit("Missing GROK_API_KEY or config.api_key")
    if not image_endpoint:
        raise SystemExit("Missing image endpoint")

    url = _join_url(base_url, image_endpoint)
    payload = {
        "model": model,
        "prompt": args.prompt,
        "n": args.n,
        "size": args.size,
        "response_format": args.response_format,
    }
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {_preview(raw)}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Request failed: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Response is not valid JSON: {_preview(raw)}") from exc

    if not isinstance(data, dict):
        raise SystemExit(f"Unexpected response type: {type(data).__name__}")

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
