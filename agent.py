#!/usr/bin/env python3
"""
Lab Assistant Agent — Task 1: Call an LLM from Code

A CLI program that takes a question as input, sends it to an LLM via
OpenAI-compatible API, and returns a structured JSON answer.

Usage:
    uv run agent.py "What does REST stand for?"

Output:
    {"answer": "Representational State Transfer.", "tool_calls": []}
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx

# Environment file path (relative to project root)
ENV_FILE = Path(__file__).parent / ".env.agent.secret"


def load_env_file(env_path: Path) -> dict[str, str]:
    """Load environment variables from a .env file."""
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def get_llm_config() -> dict[str, str]:
    """Load LLM configuration from environment or .env.agent.secret."""
    # Load from .env.agent.secret first
    env_vars = load_env_file(ENV_FILE)

    api_key = os.environ.get("LLM_API_KEY") or env_vars.get("LLM_API_KEY")
    api_base = os.environ.get("LLM_API_BASE") or env_vars.get("LLM_API_BASE")
    model = os.environ.get("LLM_MODEL") or env_vars.get("LLM_MODEL")

    if not api_key:
        print("Error: LLM_API_KEY not set. Please configure .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not set. Please configure .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not set. Please configure .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return {
        "api_key": api_key,
        "api_base": api_base.rstrip("/"),
        "model": model,
    }


async def call_llm(question: str, config: dict[str, str]) -> str:
    """
    Call the LLM API and return the answer.

    Uses OpenAI-compatible chat completions API.
    """
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant. Answer questions concisely and accurately.",
            },
            {"role": "user", "content": question},
        ],
        "temperature": 0.7,
        "max_tokens": 500,
    }

    print(f"Calling LLM at {url}...", file=sys.stderr)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    # Extract answer from OpenAI-compatible response
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        print(f"Error: Unexpected API response format: {data}", file=sys.stderr)
        sys.exit(1)

    return answer


async def main() -> None:
    """Main entry point."""
    # Parse command-line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    # Load configuration
    config = get_llm_config()
    print(f"Using model: {config['model']}", file=sys.stderr)

    # Call LLM
    answer = await call_llm(question, config)

    # Build output
    output = {
        "answer": answer,
        "tool_calls": [],
    }

    # Output valid JSON to stdout
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
