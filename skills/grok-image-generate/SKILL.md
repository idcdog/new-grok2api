---
name: grok-image-generate
description: Use this skill when the user wants to generate images through this project's Web Imagine endpoint, save the generated images to a local directory, and use the configured Grok base URL plus function key for access.
---

# Grok Image Generate

Use this skill for prompt-to-image generation through this project's Web Imagine SSE endpoint and save the returned images to local files.

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
- `GROK_FUNCTION_KEY`, `GROK_API_KEY`, `function_key`, or `api_key`

Optional values:

- `GROK_IMAGE_ENDPOINT` or `image_endpoint`
- `GROK_TIMEOUT_SECONDS` or `timeout_seconds`
- `GROK_OUTPUT_DIR` or `output_dir`

Default optional values:

- `image_endpoint = /v1/function/imagine/sse`
- `timeout_seconds = 120`
- `output_dir = <skill-dir>/output`

Do not write secrets into `SKILL.md` or checked-in source files.

## Workflow

1. Confirm the user wants image generation through the same backend path as the Web Imagine page.
2. Collect explicit inputs: `prompt`, optional `aspect_ratio` or `size`, optional image count, and optional output directory.
3. Run `python scripts/generate_image.py` with those parameters.
4. The script must call `GET /v1/function/imagine/sse` with query parameters.
5. Read SSE events until enough `b64_json` image payloads are received.
6. Save the decoded files locally and return the saved file paths.
7. If the API fails, report the HTTP status code and a short response preview.

## Validation

Before calling the script:

- prompt must be non-empty
- `count` must be a positive integer
- `aspect_ratio` should look like `2:3` when provided
- `size` should be one of the project's supported image sizes when provided

## Output

Prefer concise output:

- saved local file path list
- output directory
- clear failure details when upstream returns an error
