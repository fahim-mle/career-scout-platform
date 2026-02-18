#!/usr/bin/env python3

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    endpoint = f"{base_url}/api/generate"

    payload = {
        "model": model,
        "prompt": "Reply with one short sentence saying Ollama is ready.",
        "stream": False,
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    print(f"Testing Ollama endpoint: {endpoint}")
    print(f"Using model: {model}")

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON response: {exc}", file=sys.stderr)
        return 1

    response_text = data.get("response", "").strip()
    if not response_text:
        print("No response text returned by Ollama.", file=sys.stderr)
        return 1

    print("\nResponse:")
    print(response_text)

    print("\nMetadata:")
    metadata_fields = [
        "model",
        "created_at",
        "done",
        "done_reason",
        "total_duration",
        "load_duration",
        "prompt_eval_count",
        "eval_count",
    ]
    for field in metadata_fields:
        if field in data:
            print(f"- {field}: {data[field]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
