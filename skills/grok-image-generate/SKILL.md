---
name: grok-image-generate
description: Use this skill when the user wants to generate images through a configured Grok-compatible image API, including prompt-to-image requests, returning image URLs or base64 data, and validating Grok URL and API key based configuration.
---

# Grok Image Generate

Use this skill for prompt-to-image generation through a configured Grok-compatible API.

## Files

- `scripts/generate_image.py`: deterministic API caller
- `config/example.json`: configuration template

## Configuration

The script resolves configuration in this order:

1. environment variables
2. `config/local.json`
3. built-in defaults for optional fields only

Required values:

- `GROK_BASE_URL` or `base_url`
- `GROK_API_KEY` or `api_key`

Optional values:

- `GROK_IMAGE_MODEL` or `model`
- `GROK_IMAGE_ENDPOINT` or `image_endpoint`
- `GROK_TIMEOUT_SECONDS` or `timeout_seconds`

Default optional values:

- `model = grok-imagine-1.0`
- `image_endpoint = /v1/images/generations`
- `timeout_seconds = 120`

Do not write secrets into `SKILL.md` or checked-in source files.

## Workflow

1. Confirm the user wants image generation.
2. Collect explicit inputs: `prompt`, `n`, `size`, `response_format`.
3. Run `python scripts/generate_image.py` with those parameters.
4. Return the generated image result in the format requested by the user.
5. If the API fails, report the HTTP status code and a short response preview.

## Validation

Before calling the script:

- prompt must be non-empty
- `n` must be a positive integer
- `response_format` must be one of `url`, `b64_json`, `base64`
- `size` should look like `1024x1024`

## Output

Prefer concise output:

- image URL list when `response_format=url`
- base64 payload when explicitly requested
- clear failure details when upstream returns an error
