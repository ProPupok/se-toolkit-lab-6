#!/usr/bin/env python3
"""Agent with Ollama support."""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

PROJECT_ROOT = Path(__file__).parent.resolve()
ENV_AGENT_FILE = PROJECT_ROOT / ".env.agent.secret"
ENV_DOCKER_FILE = PROJECT_ROOT / ".env.docker.secret"
MAX_ITERATIONS = 15

SYSTEM_PROMPT = """You are a documentation and system assistant. You have access to three tools:
1. list_files - List files in a directory
2. read_file - Read a file's contents  
3. query_api - Call the deployed backend API

Use tools to find answers. Always include source references."""


def load_env_file(env_path: Path) -> dict[str, str]:
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def get_llm_config() -> dict[str, str]:
    env_vars = load_env_file(ENV_AGENT_FILE)
    api_key = os.environ.get("LLM_API_KEY") or env_vars.get("LLM_API_KEY", "")
    api_base = os.environ.get("LLM_API_BASE") or env_vars.get("LLM_API_BASE", "http://localhost:11434")
    model = os.environ.get("LLM_MODEL") or env_vars.get("LLM_MODEL", "llama3.2:3b")
    return {"api_key": api_key, "api_base": api_base.rstrip("/"), "model": model}


def tool_read_file(path: str) -> str:
    try:
        full_path = (PROJECT_ROOT / path.lstrip("/")).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT)):
            return "Error: Path traversal detected"
        if not full_path.exists() or not full_path.is_file():
            return f"Error: File not found: {path}"
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()[:10000]
    except Exception as e:
        return f"Error: {e}"


def tool_list_files(path: str) -> str:
    try:
        full_path = (PROJECT_ROOT / path.lstrip("/")).resolve()
        if not str(full_path).startswith(str(PROJECT_ROOT)):
            return "Error: Path traversal detected"
        if not full_path.exists() or not full_path.is_dir():
            return f"Error: Directory not found: {path}"
        entries = [f.name + ("/" if f.is_dir() else "") for f in full_path.iterdir() if not f.name.startswith(".")]
        return "\n".join(sorted(entries))
    except Exception as e:
        return f"Error: {e}"


def tool_query_api(method: str, path: str, body: Optional[str] = None) -> str:
    try:
        env_vars = load_env_file(ENV_DOCKER_FILE)
        lms_key = os.environ.get("LMS_API_KEY") or env_vars.get("LMS_API_KEY", "")
        api_base = os.environ.get("AGENT_API_BASE_URL") or env_vars.get("AGENT_API_BASE_URL", "http://localhost:42002")
        url = f"{api_base.rstrip('/')}{path}"
        headers = {"Authorization": f"Bearer {lms_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=30.0) as client:
            if body:
                resp = client.request(method.upper(), url, headers=headers, json=json.loads(body))
            else:
                resp = client.request(method.upper(), url, headers=headers)
        return json.dumps({"status_code": resp.status_code, "body": resp.text}, indent=2)
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "list_files", "description": "List files in directory", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "query_api", "description": "Call backend API", "parameters": {"type": "object", "properties": {"method": {"type": "string"}, "path": {"type": "string"}, "body": {"type": "string"}}, "required": ["method", "path"]}}},
]

TOOL_FUNCTIONS = {"read_file": tool_read_file, "list_files": tool_list_files, "query_api": tool_query_api}


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool: {tool_name}"
    try:
        if tool_name == "query_api":
            return TOOL_FUNCTIONS[tool_name](args.get("method", "GET"), args.get("path", ""), args.get("body"))
        return TOOL_FUNCTIONS[tool_name](args.get("path", ""))
    except Exception as e:
        return f"Error: {e}"


async def call_llm_ollama(messages: list[dict], config: dict[str, str]) -> dict:
    """Call Ollama API."""
    url = f"{config['api_base']}/api/chat"
    payload = {
        "model": config["model"],
        "messages": messages,
        "stream": False,
    }
    print(f"Calling Ollama at {url}...", file=sys.stderr)
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
    return {"choices": [{"message": {"content": data.get("message", {}).get("content", ""), "tool_calls": []}}]}


async def run_agentic_loop(question: str, config: dict[str, str]) -> tuple[str, str, list[dict]]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": question}]
    tool_calls_log = []
    
    for iteration in range(MAX_ITERATIONS):
        print(f"Iteration {iteration + 1}/{MAX_ITERATIONS}", file=sys.stderr)
        response = await call_llm_ollama(messages, config)
        assistant_message = response["choices"][0]["message"]
        tool_calls = assistant_message.get("tool_calls") or []
        
        if not tool_calls:
            answer = assistant_message.get("content") or ""
            source = ""
            import re
            m = re.search(r'(wiki/[\w\-/]+\.md|backend/[\w\-/]+\.py)', answer)
            if m:
                source = m.group(1)
            return answer, source, tool_calls_log
        
        messages.append(assistant_message)
        for tool_call in tool_calls:
            tool_id = tool_call.get("id", str(len(tool_calls_log)))
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            result = execute_tool(tool_name, tool_args)
            tool_calls_log.append({"tool": tool_name, "args": tool_args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tool_id, "content": result})
    
    return "Max iterations reached", "", tool_calls_log


async def main():
    if len(sys.argv) < 2:
        print("Usage: uv run ollama_agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)
    question = sys.argv[1]
    config = get_llm_config()
    print(f"Using model: {config['model']}", file=sys.stderr)
    answer, source, tool_calls_log = await run_agentic_loop(question, config)
    output = {"answer": answer, "source": source, "tool_calls": tool_calls_log}
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
