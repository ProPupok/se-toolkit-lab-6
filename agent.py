#!/usr/bin/env python3
"""
Lab Assistant Agent — Task 2: The Documentation Agent

A CLI agent that uses tools (read_file, list_files) to navigate the project wiki
and answer questions based on documentation.

Usage:
    uv run agent.py "How do you resolve a merge conflict?"

Output:
    {
      "answer": "...",
      "source": "wiki/git-workflow.md#resolving-merge-conflicts",
      "tool_calls": [...]
    }
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

# Environment file path (relative to project root)
ENV_FILE = Path(__file__).parent / ".env.agent.secret"

# Maximum tool call iterations
MAX_ITERATIONS = 10

# System prompt for the documentation agent
SYSTEM_PROMPT = """You are a documentation assistant. You have access to two tools:

1. list_files - List files and directories at a given path
2. read_file - Read the contents of a file

When answering questions about the project:
1. First explore the wiki structure with list_files (start with "wiki" directory)
2. Read relevant files with read_file to find the answer
3. Always include a source reference in your answer (e.g., wiki/git-workflow.md#section-name)
4. Be concise and accurate

The wiki is in the 'wiki/' directory relative to the project root.
When you find the answer, respond with a text message (no tool calls) that includes:
- The answer to the question
- A source reference (file path + section anchor if applicable)

Do not make up information. Only answer based on what you find in the wiki files."""


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


def resolve_path(relative_path: str) -> Path:
    """
    Resolve a relative path and ensure it's within the project directory.
    
    Security: Prevents path traversal attacks (../ outside project root).
    """
    project_root = Path(__file__).parent.resolve()
    
    # Handle empty path
    if not relative_path:
        relative_path = "."
    
    # Construct full path
    full_path = (project_root / relative_path).resolve()
    
    # Check for path traversal
    if not str(full_path).startswith(str(project_root)):
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
            return f.read()
            
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
            if entry.name in ["__pycache__", ".venv", ".git", "node_modules"]:
                continue
                
            suffix = "/" if entry.is_dir() else ""
            entries.append(f"{entry.name}{suffix}")
        
        return "\n".join(entries)
        
    except SecurityError as e:
        return f"Security error: {e}"
    except Exception as e:
        return f"Error listing files: {e}"


# Tool definitions for OpenAI function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the project repository",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root"
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
            "description": "List files and directories at a given path",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative directory path from project root"
                    }
                },
                "required": ["path"]
            }
        }
    }
]

# Map tool names to functions
TOOL_FUNCTIONS = {
    "read_file": tool_read_file,
    "list_files": tool_list_files,
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
        # Extract path argument
        path = args.get("path", "")
        return func(path)
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
        "max_tokens": 1500,
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
        tool_calls = assistant_message.get("tool_calls", [])
        
        if not tool_calls:
            # No tool calls - this is the final answer
            answer = assistant_message.get("content", "")
            
            # Extract source from answer (look for wiki/... pattern)
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
    
    Looks for patterns like wiki/filename.md or wiki/filename.md#section
    """
    import re
    
    # Look for wiki file references
    pattern = r'(wiki/[\w\-/]+\.md(?:#[\w\-]+)?)'
    match = re.search(pattern, answer)
    
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
