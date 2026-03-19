#!/usr/bin/env python3
"""
Lab Assistant Agent — Task 3: The System Agent

A CLI agent that uses tools (read_file, list_files, query_api) to:
- Navigate the project wiki
- Read source code
- Query the deployed backend API

Usage:
    uv run agent.py "How many items are in the database?"

Output:
    {
      "answer": "...",
      "source": "...",
      "tool_calls": [...]
    }
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx

# Project root directory
PROJECT_ROOT = Path(__file__).parent.resolve()

# Environment file paths
ENV_AGENT_FILE = PROJECT_ROOT / ".env.agent.secret"
ENV_DOCKER_FILE = PROJECT_ROOT / ".env.docker.secret"

# Maximum tool call iterations
MAX_ITERATIONS = 15

# System prompt for the system agent
SYSTEM_PROMPT = """You are a documentation and system assistant for a Learning Management Service project. You have access to three tools:

1. list_files - List files and directories at a given path
2. read_file - Read the contents of a file
3. query_api - Call the deployed backend API to get real-time data

Tool selection guidelines:
- Use list_files/read_file for:
  - Wiki documentation questions (explore wiki/ directory)
  - Source code analysis (backend/, frontend/, docker-compose.yml, etc.)
  - Configuration file questions (.env files, pyproject.toml, Dockerfile)
  
- Use query_api for:
  - Real-time data queries (item count, learner scores, analytics)
  - HTTP status code questions
  - API endpoint behavior testing
  - Error diagnosis from live API

When answering questions:
1. First determine which tool(s) to use based on the question type
2. For wiki questions: start with list_files("wiki"), then read_file
3. For source code questions: use read_file directly on the relevant file
4. For API questions: use query_api with appropriate method and path
5. Always include a source reference in your answer:
   - For wiki: wiki/filename.md or wiki/filename.md#section-name
   - For source code: path/to/file.py
   - For API: METHOD /endpoint/path
6. Be concise and accurate

Important:
- The wiki is in the 'wiki/' directory
- The backend code is in 'backend/' directory
- The API base URL is configured via environment variables
- Do not make up information - only answer based on what you find"""


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
                env_vars[key.strip()] = value.strip().strip('"').strip("'")
    return env_vars


def is_placeholder_value(value: str) -> bool:
    """Check if a value is a placeholder that should be ignored."""
    if not value:
        return True
    placeholders = [
        "your-llm-api-key-here",
        "your-qwen-api-port",
        "your-api-key",
        "<your-qwen-api-port>",
        "<port>",
    ]
    value_lower = value.lower().strip()
    return any(ph in value_lower for ph in placeholders)


def get_llm_config() -> dict[str, str]:
    """Load LLM configuration from environment or .env.agent.secret.
    
    Environment variables always take precedence over .env file values.
    Placeholder values in .env file are ignored.
    """
    env_vars = load_env_file(ENV_AGENT_FILE)

    # Environment variables take precedence
    api_key = os.environ.get("LLM_API_KEY")
    api_base = os.environ.get("LLM_API_BASE")
    model = os.environ.get("LLM_MODEL")

    # Fall back to .env file only if env vars not set or are placeholders
    if not api_key or is_placeholder_value(api_key):
        api_key = env_vars.get("LLM_API_KEY", "")
    if not api_base or is_placeholder_value(api_base):
        api_base = env_vars.get("LLM_API_BASE", "")
    if not model or is_placeholder_value(model):
        model = env_vars.get("LLM_MODEL", "")

    if not api_key or is_placeholder_value(api_key):
        print("Error: LLM_API_KEY not set or is a placeholder. Please configure .env.agent.secret or set environment variable.", file=sys.stderr)
        sys.exit(1)
    if not api_base or is_placeholder_value(api_base):
        print("Error: LLM_API_BASE not set or is a placeholder. Please configure .env.agent.secret or set environment variable.", file=sys.stderr)
        sys.exit(1)
    if not model or is_placeholder_value(model):
        print("Error: LLM_MODEL not set or is a placeholder. Please configure .env.agent.secret or set environment variable.", file=sys.stderr)
        sys.exit(1)

    return {
        "api_key": api_key,
        "api_base": api_base.rstrip("/"),
        "model": model,
    }


def get_backend_config() -> dict[str, str]:
    """Load backend configuration from environment or .env.docker.secret.
    
    Environment variables always take precedence over .env file values.
    Placeholder values in .env file are ignored.
    """
    env_vars = load_env_file(ENV_DOCKER_FILE)

    # Environment variables take precedence
    lms_api_key = os.environ.get("LMS_API_KEY")
    agent_api_base = os.environ.get("AGENT_API_BASE_URL")

    # Fall back to .env file only if env vars not set or are placeholders
    if not lms_api_key or is_placeholder_value(lms_api_key):
        lms_api_key = env_vars.get("LMS_API_KEY", "")
    if not agent_api_base or is_placeholder_value(agent_api_base):
        agent_api_base = env_vars.get("AGENT_API_BASE_URL", "http://localhost:42002")

    if not lms_api_key or is_placeholder_value(lms_api_key):
        print("Error: LMS_API_KEY not set or is a placeholder. Please configure .env.docker.secret or set environment variable.", file=sys.stderr)
        sys.exit(1)

    return {
        "api_key": lms_api_key,
        "api_base": agent_api_base.rstrip("/"),
    }


def resolve_path(relative_path: str) -> Path:
    """
    Resolve a relative path and ensure it's within the project directory.
    
    Security: Prevents path traversal attacks (../ outside project root).
    """
    if not relative_path:
        relative_path = "."
    
    # Clean the path
    relative_path = relative_path.lstrip("/")
    
    # Construct full path
    full_path = (PROJECT_ROOT / relative_path).resolve()
    
    # Check for path traversal
    if not str(full_path).startswith(str(PROJECT_ROOT)):
        raise SecurityError(f"Path traversal detected: {relative_path}")
    
    return full_path


class SecurityError(Exception):
    """Raised when a path traversal attempt is detected."""
    pass


def tool_read_file(path: str) -> str:
    """
    Read a file from the project repository.
    
    Args:
        path: Relative path from project root
        
    Returns:
        File contents as string, or error message
    """
    try:
        full_path = resolve_path(path)
        
        if not full_path.exists():
            return f"Error: File not found: {path}"
        
        if not full_path.is_file():
            return f"Error: Not a file: {path}"
        
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Truncate very large files
        max_length = 10000
        if len(content) > max_length:
            content = content[:max_length] + "\n... [truncated]"
        
        return content
            
    except SecurityError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


def tool_list_files(path: str) -> str:
    """
    List files and directories at a given path.
    
    Args:
        path: Relative directory path from project root
        
    Returns:
        Newline-separated listing of entries, or error message
    """
    try:
        full_path = resolve_path(path)
        
        if not full_path.exists():
            return f"Error: Path not found: {path}"
        
        if not full_path.is_dir():
            return f"Error: Not a directory: {path}"
        
        entries = []
        for entry in sorted(full_path.iterdir()):
            # Skip hidden files and common ignored directories
            if entry.name.startswith(".") and entry.name not in [".github", ".vscode"]:
                continue
            if entry.name in ["__pycache__", ".venv", ".git", "node_modules", ".qwen"]:
                continue
                
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")
        
        return "\n".join(entries)
        
    except SecurityError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error listing files: {e}"


def tool_query_api(method: str, path: str, body: Optional[str] = None) -> str:
    """
    Call the deployed backend API.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API endpoint path (e.g., /items/, /analytics/completion-rate)
        body: Optional JSON request body for POST/PUT requests
        
    Returns:
        JSON string with status_code and response body, or error message
    """
    try:
        backend_config = get_backend_config()
        url = f"{backend_config['api_base']}{path}"
        
        headers = {
            "Authorization": f"Bearer {backend_config['api_key']}",
            "Content-Type": "application/json",
        }
        
        print(f"Querying API: {method} {url}", file=sys.stderr)
        
        # Prepare request
        kwargs = {"headers": headers, "timeout": 30.0}
        
        if body:
            try:
                kwargs["json"] = json.loads(body)
            except json.JSONDecodeError:
                return f"Error: Invalid JSON body: {body}"
        
        # Make request
        with httpx.Client() as client:
            response = client.request(method.upper(), url, **kwargs)
        
        # Format response
        result = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.text,
        }
        
        try:
            result["json"] = response.json()
        except:
            pass
        
        return json.dumps(result, indent=2)
        
    except httpx.HTTPStatusError as e:
        return json.dumps({
            "status_code": e.response.status_code if e.response else "N/A",
            "error": str(e),
            "body": e.response.text if e.response else "",
        }, indent=2)
    except httpx.RequestError as e:
        return f"Error: Cannot connect to API at {url}: {e}"
    except Exception as e:
        return f"Error querying API: {e}"


# Tool definitions for OpenAI function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository. Use for wiki documentation, source code, and configuration files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py')"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a given path. Use to explore directory structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root (e.g., 'wiki', 'backend/app')"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_api",
            "description": "Call the deployed backend API to get real-time data, test endpoints, or check HTTP status codes. Use for questions about database content, API behavior, or error responses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, PUT, DELETE)",
                        "enum": ["GET", "POST", "PUT", "DELETE"]
                    },
                    "path": {
                        "type": "string",
                        "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate', '/items/1')"
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional JSON request body for POST/PUT requests"
                    }
                },
                "required": ["method", "path"]
            }
        }
    }
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
    "query_api": tool_query_api,
}


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """
    Execute a tool and return the result.
    
    Args:
        tool_name: Name of the tool to execute
        args: Arguments for the tool
        
    Returns:
        Tool result as string
    """
    if tool_name not in TOOL_FUNCTIONS:
        return f"Error: Unknown tool: {tool_name}"
    
    func = TOOL_FUNCTIONS[tool_name]
    
    try:
        if tool_name == "query_api":
            return func(
                args.get("method", "GET"),
                args.get("path", ""),
                args.get("body"),
            )
        else:
            return func(args.get("path", ""))
    except Exception as e:
        return f"Error executing {tool_name}: {e}"


async def call_llm(messages: list[dict], config: dict[str, str]) -> dict:
    """
    Call the LLM API and return the response.
    
    Uses OpenAI-compatible chat completions API with function calling.
    """
    url = f"{config['api_base']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config["model"],
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    print(f"Calling LLM at {url}...", file=sys.stderr)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return data


async def run_agentic_loop(question: str, config: dict[str, str]) -> tuple[str, str, list[dict]]:
    """
    Run the agentic loop to answer a question using tools.
    
    Args:
        question: User's question
        config: LLM configuration
        
    Returns:
        Tuple of (answer, source, tool_calls_log)
    """
    # Initialize messages
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    
    # Track all tool calls for output
    tool_calls_log = []
    
    print(f"Starting agentic loop for question: {question}", file=sys.stderr)
    
    for iteration in range(MAX_ITERATIONS):
        print(f"Iteration {iteration + 1}/{MAX_ITERATIONS}", file=sys.stderr)
        
        # Call LLM
        response = await call_llm(messages, config)
        
        # Get assistant message
        assistant_message = response["choices"][0]["message"]
        
        # Check for tool calls
        tool_calls = assistant_message.get("tool_calls") or []
        
        if not tool_calls:
            # No tool calls - this is the final answer
            answer = assistant_message.get("content") or ""
            
            # Extract source from answer (look for wiki/... or file patterns)
            source = extract_source(answer)
            
            print(f"Final answer found in iteration {iteration + 1}", file=sys.stderr)
            return answer, source, tool_calls_log
        
        # Add assistant message with tool calls to messages
        messages.append(assistant_message)
        
        # Execute each tool call
        for tool_call in tool_calls:
            tool_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            
            print(f"Executing tool: {tool_name}({tool_args})", file=sys.stderr)
            
            # Execute tool
            result = execute_tool(tool_name, tool_args)
            
            # Log tool call
            tool_calls_log.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result,
            })
            
            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result,
            })
    
    # Max iterations reached
    print("Max iterations reached", file=sys.stderr)
    
    # Try to extract an answer from the conversation
    if tool_calls_log:
        last_result = tool_calls_log[-1]["result"]
        answer = f"Found information: {last_result[:500]}..."
        source = "Multiple sources (max iterations reached)"
    else:
        answer = "Unable to find answer within iteration limit"
        source = ""
    
    return answer, source, tool_calls_log


def extract_source(answer: str) -> str:
    """
    Extract source reference from the answer.
    
    Looks for patterns like wiki/filename.md, backend/...py, or API endpoints.
    """
    import re
    
    # Look for wiki file references
    wiki_pattern = r'(wiki/[\w\-/]+\.md(?:#[\w\-]+)?)'
    match = re.search(wiki_pattern, answer)
    if match:
        return match.group(1)
    
    # Look for backend file references
    backend_pattern = r'(backend/[\w\-/]+\.py)'
    match = re.search(backend_pattern, answer)
    if match:
        return match.group(1)
    
    # Look for other file references
    file_pattern = r'((?:docker-compose|Dockerfile|pyproject\.toml|\.env\.\w+))'
    match = re.search(file_pattern, answer)
    if match:
        return match.group(1)
    
    # Look for API endpoint references
    api_pattern = r'((?:GET|POST|PUT|DELETE)\s+/[\w\-/]+)'
    match = re.search(api_pattern, answer)
    if match:
        return match.group(1)
    
    # Default empty source
    return ""


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

    # Run agentic loop
    answer, source, tool_calls_log = await run_agentic_loop(question, config)

    # Build output
    output = {
        "answer": answer,
        "source": source,
        "tool_calls": tool_calls_log,
    }

    # Output valid JSON to stdout
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
