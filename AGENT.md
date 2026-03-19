# Lab Assistant Agent

A CLI agent that uses tools (`read_file`, `list_files`, `query_api`) to:
- Navigate the project wiki and read documentation
- Analyze source code
- Query the deployed backend API for real-time data

## Architecture

```
Question ──▶ LLM ──▶ tool call? ──yes──▶ execute tools ──▶ back to LLM
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
  - Loads backend configuration from `.env.docker.secret`
  - Implements agentic loop with tool execution (max 15 iterations)
  - Outputs structured JSON to stdout

- **`.env.agent.secret`** — LLM configuration (gitignored)
  - `LLM_API_KEY` — API key for LLM provider authentication
  - `LLM_API_BASE` — Base URL of the LLM provider (OpenAI-compatible)
  - `LLM_MODEL` — Model name to use

- **`.env.docker.secret`** — Backend configuration (gitignored)
  - `LMS_API_KEY` — API key for backend authentication
  - `AGENT_API_BASE_URL` — Backend API base URL (default: http://localhost:42002)

- **LLM Provider** — Qwen Code API (OpenAI-compatible endpoint)
  - Model: `qwen3-coder-plus`
  - Supports native function calling

## Tools

The agent has three tools that the LLM can call:

### 1. `read_file`

Read a file from the project repository.

**Parameters:**
- `path` (string) — Relative path from project root

**Returns:** File contents as string (truncated to 10,000 chars), or error message.

**Use cases:**
- Wiki documentation questions
- Source code analysis
- Configuration file questions

**Example:**
```json
{"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}}
```

### 2. `list_files`

List files and directories at a given path.

**Parameters:**
- `path` (string) — Relative directory path from project root

**Returns:** Newline-separated listing of entries, or error message.

**Use cases:**
- Exploring directory structure
- Finding relevant files
- Discovering wiki content

**Example:**
```json
{"tool": "list_files", "args": {"path": "wiki"}}
```

### 3. `query_api`

Call the deployed backend API to get real-time data.

**Parameters:**
- `method` (string) — HTTP method (GET, POST, PUT, DELETE)
- `path` (string) — API endpoint path (e.g., `/items/`, `/analytics/completion-rate`)
- `body` (string, optional) — JSON request body for POST/PUT requests

**Returns:** JSON string with `status_code`, `headers`, `body`, and `json` (if applicable).

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` via Bearer token.

**Use cases:**
- Real-time data queries (item count, learner scores)
- HTTP status code questions
- API endpoint behavior testing
- Error diagnosis from live API

**Example:**
```json
{"tool": "query_api", "args": {"method": "GET", "path": "/items/"}}
```

### Path Security

Both `read_file` and `list_files` enforce path security to prevent directory traversal attacks:

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

1. **Initialize messages** with system prompt + user question
2. **Loop** (max 15 iterations):
   - Call LLM with messages + tool definitions
   - Parse response:
     - If `tool_calls` present:
       - Execute each tool
       - Append results as `tool` role messages
       - Continue loop
     - If no tool calls (text response):
       - Extract answer and source
       - Break loop
3. **Output** JSON with `answer`, `source`, `tool_calls`

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

The system prompt guides the LLM to choose the right tool:

- **Use `list_files`/`read_file` for:**
  - Wiki documentation questions
  - Source code analysis
  - Configuration file questions

- **Use `query_api` for:**
  - Real-time data queries
  - HTTP status code questions
  - API endpoint behavior
  - Error diagnosis

The prompt also instructs the LLM to always include source references in answers.

## How to Run

### Prerequisites

1. **Set up LLM API:**
   - Option A: Qwen Code API on your VM (recommended, 1000 free requests/day)
   - Option B: OpenRouter API (free models available)

2. **Configure environment:**
   ```bash
   cp .env.agent.example .env.agent.secret
   # Edit .env.agent.secret with your actual values
   ```

3. **Ensure backend is running:**
   ```bash
   docker-compose up -d
   ```

4. **Fill in `.env.agent.secret`:**
   ```
   LLM_API_KEY=your-llm-api-key
   LLM_API_BASE=http://<vm-ip>:<port>/v1  # or https://openrouter.ai/api/v1
   LLM_MODEL=qwen3-coder-plus
   ```

5. **Verify `.env.docker.secret` has `LMS_API_KEY`:**
   ```
   LMS_API_KEY=your-backend-api-key
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
| `source` | string | Reference to source (wiki file, source code, or API endpoint) |
| `tool_calls` | array | All tool calls made during the agentic loop |

Each tool call entry contains:
- `tool` — tool name (`read_file`, `list_files`, or `query_api`)
- `args` — arguments passed to the tool
- `result` — tool output

### Error Handling

- Missing arguments → prints usage to stderr, exits with code 1
- Missing configuration → prints error to stderr, exits with code 1
- API errors → prints error to stderr, exits with code 1
- Timeout (>60s per LLM call) → prints error to stderr, exits with code 1
- Max iterations (15) reached → outputs partial answer

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py tests/test_agent_task2.py tests/test_agent_task3.py -v
```

### Test Coverage

| Test File | Tests | Verifies |
|-----------|-------|----------|
| `tests/test_agent.py` | 1 | Basic JSON structure |
| `tests/test_agent_task2.py` | 2 | `read_file` and `list_files` usage |
| `tests/test_agent_task3.py` | 2 | `query_api` and framework detection |

### Running the Benchmark

```bash
uv run run_eval.py           # All questions, stop at first failure
uv run run_eval.py --index 5 # Single question (for debugging)
```

The benchmark tests 10 questions across all categories:
- Wiki lookup (read_file)
- Source code analysis (read_file, list_files)
- Data queries (query_api)
- Bug diagnosis (query_api + read_file)
- System reasoning (read_file)

## Development

### Dependencies

Uses existing project dependencies from `pyproject.toml`:
- `httpx` — async HTTP client
- `pydantic-settings` — (optional) environment loading

### Code Structure

```
agent.py
├── load_env_file()         — Parse .env files
├── get_llm_config()        — Load LLM configuration
├── get_backend_config()    — Load backend configuration
├── resolve_path()          — Security: validate file paths
├── tool_read_file()        — Read a file
├── tool_list_files()       — List directory contents
├── tool_query_api()        — Call backend API with auth
├── execute_tool()          — Dispatch tool calls
├── call_llm()              — Async HTTP request to LLM API
├── run_agentic_loop()      — Main agentic loop (max 15 iterations)
├── extract_source()        — Parse source from answer
└── main()                  — CLI entry point
```

## Tasks Progress

| Task | Description | Status |
|------|-------------|--------|
| 1 | Call an LLM from Code | ✅ Completed |
| 2 | The Documentation Agent | ✅ Completed |
| 3 | The System Agent | ✅ Completed |

## Lessons Learned

### Tool Design

1. **Clear descriptions matter:** The LLM relies on tool descriptions to decide when to use each tool. Vague descriptions lead to incorrect tool selection.

2. **Parameter clarity:** Each parameter needs a clear description with examples. For `query_api`, specifying that `path` should start with `/` helps avoid malformed URLs.

3. **Error messages as tool results:** Returning structured error messages (rather than raising exceptions) allows the LLM to understand what went wrong and potentially retry.

### Agentic Loop

1. **Iteration limit is crucial:** Without a limit, the LLM can get stuck in loops (e.g., reading the same file repeatedly). We use 15 iterations as a reasonable balance.

2. **Message format matters:** Using the OpenAI tool message format (`role: "tool"`, `tool_call_id`) is essential for models trained on this pattern.

3. **Handling null content:** When the LLM returns tool calls, the `content` field may be `null` (not missing). Using `msg.get("content") or ""` instead of `msg.get("content", "")` avoids AttributeError.

### Authentication

1. **Separate keys for separate concerns:** `LLM_API_KEY` authenticates with the LLM provider, while `LMS_API_KEY` authenticates with the backend. Keeping them in separate files (`.env.agent.secret` vs `.env.docker.secret`) clarifies their purposes.

2. **Environment variable fallback:** Loading from both environment variables and `.env` files allows flexibility for local development and autochecker evaluation.

### Benchmark Iteration

1. **Start with keyword matching:** The autochecker uses keyword matching for most questions. Ensuring answers contain expected keywords (e.g., "FastAPI", "401", "branch protect") is critical.

2. **Source field extraction:** The `extract_source()` function uses regex patterns to find file references in the LLM's answer. This is a fallback when the LLM doesn't explicitly format the source.

3. **Tool verification:** The autochecker verifies that the correct tools were called. Calling `query_api` for a wiki question fails even if the answer text is correct.

### Performance

1. **Truncate large files:** Reading entire files (e.g., `pyproject.toml` with long dependency lists) can exceed token limits. Truncating to 10,000 characters balances completeness with token efficiency.

2. **Async for LLM calls:** Using `httpx.AsyncClient` for LLM calls allows potential parallelism in future extensions.

3. **Sync for API queries:** The `query_api` tool uses sync `httpx.Client` because it's called within an already async loop, and the overhead is minimal.

## Troubleshooting

### "LLM_API_KEY not set"

Ensure `.env.agent.secret` exists and contains valid credentials:
```bash
cat .env.agent.secret
```

### "LMS_API_KEY not set"

Ensure `.env.docker.secret` exists with the backend API key:
```bash
cat .env.docker.secret | grep LMS_API_KEY
```

### Connection timeout to LLM

Verify your VM is running and the Qwen Code API is accessible:
```bash
curl -H "Authorization: Bearer $LLM_API_KEY" "$LLM_API_BASE/models"
```

### Cannot connect to backend API

Check if Docker containers are running:
```bash
docker-compose ps
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

The agent extracts source references from the LLM's answer. Ensure the system prompt instructs the LLM to include file references.

### Agent times out

- Reduce `MAX_ITERATIONS` if the loop is too long
- Use a faster LLM model
- Check for network latency to the LLM API
