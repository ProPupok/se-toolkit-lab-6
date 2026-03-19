#!/usr/bin/env python3
"""Lab Assistant Agent - supports Ollama and OpenAI-compatible APIs."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

PROJECT_ROOT = Path(__file__).parent.resolve()
ENV_AGENT_FILE = PROJECT_ROOT / ".env.agent.secret"
ENV_DOCKER_FILE = PROJECT_ROOT / ".env.docker.secret"
MAX_ITERATIONS = 10

SYSTEM_PROMPT = """You are a documentation assistant.

TOOLS:
1. list_files - {"tool": "list_files", "args": {"path": "wiki"}}
2. read_file - {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}}
3. query_api - {"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}

RULES:
- Wiki: list_files then read_file
- Code: read_file
- Data: query_api
- Include source in answer

JSON for tools, text for answers."""


def load_env_file(env_path: Path) -> dict:
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env_vars[k.strip()] = v.strip().strip('"\'')
    return env_vars


def get_llm_config() -> dict:
    env_vars = load_env_file(ENV_AGENT_FILE)
    return {
        "api_key": os.environ.get("LLM_API_KEY") or env_vars.get("LLM_API_KEY", ""),
        "api_base": (os.environ.get("LLM_API_BASE") or env_vars.get("LLM_API_BASE", "http://localhost:11434")).rstrip("/"),
        "model": os.environ.get("LLM_MODEL") or env_vars.get("LLM_MODEL", "llama3.2:3b"),
    }


def get_backend_config() -> dict:
    env_vars = load_env_file(ENV_DOCKER_FILE)
    lms_key = os.environ.get("LMS_API_KEY") or env_vars.get("LMS_API_KEY", "")
    api_base = os.environ.get("AGENT_API_BASE_URL") or env_vars.get("AGENT_API_BASE_URL", "http://localhost:42002")
    return {"api_key": lms_key, "api_base": api_base.rstrip("/")}


def resolve_path(p: str) -> Path:
    p = p.lstrip("/") or "."
    full = (PROJECT_ROOT / p).resolve()
    if not str(full).startswith(str(PROJECT_ROOT)):
        raise SecurityError(f"Path traversal: {p}")
    return full


class SecurityError(Exception):
    pass


def tool_read_file(path: str) -> str:
    try:
        full = resolve_path(path)
        if not full.exists():
            return f"Error: File not found: {path}"
        if not full.is_file():
            return f"Error: Not a file: {path}"
        return full.read_text(encoding="utf-8")[:10000]
    except Exception as e:
        return f"Error: {e}"


def tool_list_files(path: str) -> str:
    try:
        full = resolve_path(path)
        if not full.exists():
            return f"Error: Path not found: {path}"
        if not full.is_dir():
            return f"Error: Not a directory: {path}"
        entries = []
        for e in sorted(full.iterdir()):
            if e.name.startswith(".") and e.name not in [".github", ".vscode"]:
                continue
            if e.name in ["__pycache__", ".venv", ".git", "node_modules", ".qwen"]:
                continue
            entries.append(f"{e.name}{'/' if e.is_dir() else ''}")
        return "\n".join(entries)
    except Exception as e:
        return f"Error: {e}"


def tool_query_api(method: str, path: str, body: Optional[str] = None) -> str:
    try:
        cfg = get_backend_config()
        url = f"{cfg['api_base']}{path}"
        headers = {"Authorization": f"Bearer {cfg['api_key']}", "Content-Type": "application/json"}
        print(f"API: {method} {url}", file=sys.stderr)
        with httpx.Client(timeout=30.0) as client:
            if body:
                resp = client.request(method.upper(), url, headers=headers, json=json.loads(body))
            else:
                resp = client.request(method.upper(), url, headers=headers)
        return json.dumps({"status_code": resp.status_code, "body": resp.text[:2000]}, indent=2)
    except Exception as e:
        return f"Error: {e}"


TOOLS = {"read_file": tool_read_file, "list_files": tool_list_files, "query_api": tool_query_api}


def execute_tool(name: str, args: dict) -> str:
    if name not in TOOLS:
        return f"Error: Unknown tool: {name}"
    try:
        if name == "query_api":
            return TOOLS[name](args.get("method", "GET"), args.get("path", ""), args.get("body"))
        return TOOLS[name](args.get("path", ""))
    except Exception as e:
        return f"Error: {e}"


def parse_tool_call(text: str) -> Optional[dict]:
    m = re.search(r'\{"tool":\s*"(\w+)",\s*"args":\s*({[^}]+})\}', text, re.DOTALL)
    if m:
        try:
            return {"tool": m.group(1), "args": json.loads(m.group(2))}
        except:
            pass
    m = re.search(r'```\s*\{"tool":\s*"(\w+)",\s*"args":\s*({[^}]+})\}\s*```', text, re.DOTALL)
    if m:
        try:
            return {"tool": m.group(1), "args": json.loads(m.group(2))}
        except:
            pass
    return None


def extract_source(text: str) -> str:
    for p in [r'(wiki/[\w\-/]+\.md)', r'(backend/[\w\-/]+\.py)', r'((?:GET|POST)\s+/[\w/\-]+)']:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


async def call_llm(messages: list, config: dict) -> str:
    is_ollama = "11434" in config["api_base"] or "localhost" in config["api_base"] or "127.0.0.1" in config["api_base"]
    
    if is_ollama:
        url = f"{config['api_base']}/api/chat"
        payload = {"model": config["model"], "messages": messages, "stream": False}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
    else:
        url = f"{config['api_base']}/chat/completions"
        headers = {"Authorization": f"Bearer {config['api_key']}", "Content-Type": "application/json"}
        payload = {"model": config["model"], "messages": messages, "temperature": 0.3, "max_tokens": 1500}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


async def run_loop(question: str, config: dict):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    log = []
    for i in range(MAX_ITERATIONS):
        print(f"[{i+1}/{MAX_ITERATIONS}]", file=sys.stderr)
        text = await call_llm(messages, config)
        print(f"LLM: {text[:80]}...", file=sys.stderr)
        tool = parse_tool_call(text)
        if tool:
            print(f"Tool: {tool['tool']}", file=sys.stderr)
            result = execute_tool(tool["tool"], tool["args"])
            log.append({"tool": tool["tool"], "args": tool["args"], "result": result[:1000]})
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": f"Result: {result[:1500]}\nAnswer now."})
        else:
            return text, extract_source(text), log
    return "Max iterations", "", log


async def main():
    try:
        if len(sys.argv) < 2:
            print("Usage: agent.py <question>", file=sys.stderr)
            sys.exit(1)
        config = get_llm_config()
        print(f"Using: {config['model']} @ {config['api_base']}", file=sys.stderr)
        answer, source, tools = await run_loop(sys.argv[1], config)
        print(json.dumps({"answer": answer, "source": source, "tool_calls": tools}))
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
