# Plan: Task 2 — The Documentation Agent

## Overview

Build an agentic loop that allows the LLM to call tools (`read_file`, `list_files`) to navigate the project wiki and find answers.

## LLM Provider and Model

**Provider:** Qwen Code API (OpenAI-compatible endpoint)
**Model:** `qwen3-coder-plus`

This model supports function calling (tool calls) natively with the OpenAI-compatible API.

## Tool Definitions

### 1. `read_file`

Read a file from the project repository.

**Parameters:**
- `path` (string) — relative path from project root

**Returns:** File contents as string, or error message if file doesn't exist.

**Security:**
- Resolve path and ensure it's within project directory
- Reject paths with `../` traversal outside project root

**Schema (OpenAI function calling):**
```json
{
  "name": "read_file",
  "description": "Read a file from the project repository",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Relative path from project root"}
    },
    "required": ["path"]
  }
}
```

### 2. `list_files`

List files and directories at a given path.

**Parameters:**
- `path` (string) — relative directory path from project root

**Returns:** Newline-separated listing of entries.

**Security:**
- Resolve path and ensure it's within project directory
- Reject paths that escape project root

**Schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories at a given path",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {"type": "string", "description": "Relative directory path from project root"}
    },
    "required": ["path"]
  }
}
```

## Agentic Loop

```
Question ──▶ LLM ──▶ tool calls? ──yes──▶ execute tools ──▶ back to LLM
                         │
                         no
                         │
                         ▼
                    JSON output
```

### Algorithm

1. **Initialize messages** with system prompt + user question
2. **Loop** (max 10 iterations):
   - Call LLM with messages + tool definitions
   - Parse response:
     - If `tool_calls` present:
       - Execute each tool
       - Append tool results as `tool` role messages
       - Continue loop
     - If no tool calls (text response):
       - Extract answer
       - Extract source (wiki file reference)
       - Break loop
3. **Output** JSON with `answer`, `source`, `tool_calls`

### Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "content": None, "tool_calls": [...]},
    {"role": "tool", "content": result, "tool_call_id": "..."},
]
```

## System Prompt

The system prompt should instruct the LLM to:

1. Use `list_files` to discover wiki files
2. Use `read_file` to read relevant files
3. Include source reference (file path + section anchor) in the answer
4. Call tools one at a time or in parallel when appropriate
5. Stop when the answer is found

Example:
```
You are a documentation assistant. You have access to two tools:
- list_files: List files in a directory
- read_file: Read a file's contents

When answering questions:
1. First explore the wiki structure with list_files
2. Read relevant files with read_file
3. Always include a source reference (e.g., wiki/git-workflow.md#section-name)
4. Be concise and accurate

The wiki is in the 'wiki/' directory relative to the project root.
```

## Path Security

```python
def resolve_path(relative_path: str) -> Path:
    """Resolve path and ensure it's within project root."""
    project_root = Path(__file__).parent
    full_path = (project_root / relative_path).resolve()
    
    # Check for path traversal
    if not str(full_path).startswith(str(project_root)):
        raise SecurityError(f"Path traversal detected: {relative_path}")
    
    return full_path
```

## Output Format

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

## Error Handling

- File not found → return error message as tool result
- Path traversal attempt → return security error
- LLM API error → print to stderr, exit code 1
- Max iterations (10) reached → output partial answer

## Testing Strategy

Create 2 regression tests in `tests/test_agent_task2.py`:

1. **Test read_file usage:**
   - Question: "How do you resolve a merge conflict?"
   - Verify: `read_file` in tool_calls, `wiki/git-workflow.md` in source

2. **Test list_files usage:**
   - Question: "What files are in the wiki?"
   - Verify: `list_files` in tool_calls

## Files to Create/Update

1. `plans/task-2.md` — this plan
2. `agent.py` — update with tools and agentic loop
3. `AGENT.md` — update documentation
4. `tests/test_agent_task2.py` — 2 regression tests

## Acceptance Criteria Checklist

- [ ] Plan committed before code
- [ ] `read_file` and `list_files` tools defined
- [ ] Agentic loop executes tool calls
- [ ] `tool_calls` populated in output
- [ ] `source` field identifies wiki section
- [ ] Path security prevents traversal
- [ ] `AGENT.md` documents tools and loop
- [ ] 2 regression tests pass
