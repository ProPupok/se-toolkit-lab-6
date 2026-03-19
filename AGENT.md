# Lab Assistant Agent

A CLI agent that uses tools (`read_file`, `list_files`) to navigate the project wiki and answer questions based on documentation.

## Architecture

```
Question ──▶ LLM ──▶ tool calls? ──yes──▶ execute tools ──▶ back to LLM
                         │
                         no
                         │
                         ▼
                    JSON output
```

### Components

- **`agent.py`** — Main CLI entry point
  - Parses command-line arguments
  - Loads LLM configuration from `.env.agent.secret`
  - Implements agentic loop with tool execution
  - Outputs structured JSON to stdout

- **`.env.agent.secret`** — Environment configuration (gitignored)
  - `LLM_API_KEY` — API key for authentication
  - `LLM_API_BASE` — Base URL of the LLM provider
  - `LLM_MODEL` — Model name to use

- **LLM Provider** — Qwen Code API (OpenAI-compatible endpoint)
  - Model: `qwen3-coder-plus`
  - Supports native function calling

## Tools

The agent has two tools that the LLM can call:

### 1. `read_file`

Read a file from the project repository.

**Parameters:**
- `path` (string) — Relative path from project root

**Returns:** File contents as string, or error message.

**Example:**
```json
{"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}}
```

### 2. `list_files`

List files and directories at a given path.

**Parameters:**
- `path` (string) — Relative directory path from project root

**Returns:** Newline-separated listing of entries.

**Example:**
```json
{"tool": "list_files", "args": {"path": "wiki"}}
```

### Path Security

Both tools enforce path security to prevent directory traversal attacks:

```python
def resolve_path(relative_path: str) -> Path:
    project_root = Path(__file__).parent.resolve()
    full_path = (project_root / relative_path).resolve()
    
    # Reject paths that escape project root
    if not str(full_path).startswith(str(project_root)):
        raise SecurityError(f"Path traversal detected: {relative_path}")
    
    return full_path
```

## Agentic Loop

The agent runs a loop that continues until the LLM provides a final answer:

1. **Send question** to LLM with tool definitions
2. **Parse response:**
   - If `tool_calls` present → execute tools, append results, repeat
   - If text response → extract answer and source, output JSON
3. **Maximum 10 iterations** to prevent infinite loops

### Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question},
    # After tool calls:
    {"role": "assistant", "tool_calls": [...]},
    {"role": "tool", "tool_call_id": "...", "content": result},
]
```

### System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover wiki structure
2. Use `read_file` to read relevant files
3. Include source references in answers
4. Stop when the answer is found

## How to Run

### Prerequisites

1. Set up Qwen Code API on your VM following [wiki/qwen.md](wiki/qwen.md)

2. Configure environment:
   ```bash
   cp .env.agent.example .env.agent.secret
   # Edit .env.agent.secret with your actual values
   ```

3. Fill in `.env.agent.secret`:
   ```
   LLM_API_KEY=your-api-key
   LLM_API_BASE=http://<vm-ip>:<port>/v1
   LLM_MODEL=qwen3-coder-plus
   ```

### Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

**Output:**
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

### Output Format

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `source` | string | Wiki section reference (e.g., `wiki/git-workflow.md#section`) |
| `tool_calls` | array | All tool calls made during the agentic loop |

Each tool call entry contains:
- `tool` — tool name (`read_file` or `list_files`)
- `args` — arguments passed to the tool
- `result` — tool output

### Error Handling

- Missing arguments → prints usage to stderr, exits with code 1
- Missing configuration → prints error to stderr, exits with code 1
- API errors → prints error to stderr, exits with code 1
- Timeout (>60s) → prints error to stderr, exits with code 1
- Max iterations (10) → outputs partial answer

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py tests/test_agent_task2.py -v
```

### Test Coverage

| Test | Question | Verifies |
|------|----------|----------|
| `test_agent_output_structure` | "What is 2+2?" | Basic JSON structure |
| `test_documentation_agent_read_file` | "How do you resolve a merge conflict?" | `read_file` usage, source field |
| `test_documentation_agent_list_files` | "What files are in the wiki?" | `list_files` usage |

## Development

### Dependencies

Uses existing project dependencies from `pyproject.toml`:
- `httpx` — async HTTP client
- `pydantic-settings` — (optional) environment loading

### Code Structure

```
agent.py
├── load_env_file()         — Parse .env.agent.secret
├── get_llm_config()        — Load and validate configuration
├── resolve_path()          — Security: validate file paths
├── tool_read_file()        — Read a file
├── tool_list_files()       — List directory contents
├── execute_tool()          — Dispatch tool calls
├── call_llm()              — Async HTTP request to LLM API
├── run_agentic_loop()      — Main agentic loop
├── extract_source()        — Parse source from answer
└── main()                  — CLI entry point
```

## Tasks Progress

| Task | Description | Status |
|------|-------------|--------|
| 1 | Call an LLM from Code | ✅ Completed |
| 2 | The Documentation Agent | ✅ Implemented |
| 3 | Add Agentic Loop | ⏳ Pending |

## Troubleshooting

### "LLM_API_KEY not set"

Ensure `.env.agent.secret` exists and contains valid credentials:
```bash
cat .env.agent.secret
```

### Connection timeout

Verify your VM is running and the Qwen Code API is accessible:
```bash
curl -H "Authorization: Bearer $LLM_API_KEY" "$LLM_API_BASE/models"
```

### Invalid JSON output

All debug output goes to stderr. Only the final JSON goes to stdout:
```bash
uv run agent.py "question" 2>/dev/null  # stdout only
```

### Tool calls not working

Ensure you're using a model that supports function calling:
- `qwen3-coder-plus` — ✅ supports tool calls
- Check LLM API logs for errors

### Source field is empty

The agent extracts source references from the LLM's answer. Ensure the system prompt instructs the LLM to include wiki file references.
