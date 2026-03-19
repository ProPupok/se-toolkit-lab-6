# Plan: Task 1 — Call an LLM from Code

## LLM Provider and Model

**Provider:** Qwen Code API (OpenAI-compatible endpoint)

**Model:** `qwen3-coder-plus`

**Rationale:**
- 1000 free requests per day
- Works from Russia without credit card
- Strong tool calling capabilities (needed for Task 2-3)
- OpenAI-compatible API simplifies integration

## Environment Configuration

The agent will read configuration from `.env.agent.secret`:

```
LLM_API_KEY=<api-key>
LLM_API_BASE=http://<vm-ip>:<port>/v1
LLM_MODEL=qwen3-coder-plus
```

## Agent Architecture

### Input
- Single command-line argument: the user's question
- Example: `uv run agent.py "What does REST stand for?"`

### Processing Flow

1. **Parse arguments** — read question from `sys.argv[1]`
2. **Load environment** — read `.env.agent.secret` using `pydantic-settings` or `os.environ`
3. **Call LLM** — use `httpx` async client to send POST request to `{LLM_API_BASE}/chat/completions`
4. **Parse response** — extract `choices[0].message.content` from OpenAI-compatible response
5. **Format output** — build JSON with `answer` and empty `tool_calls` array

### Output
- Single JSON line to stdout:
  ```json
  {"answer": "Representational State Transfer.", "tool_calls": []}
  ```
- All debug/progress output goes to stderr
- Exit code 0 on success

## Error Handling

- Missing command-line argument → print error to stderr, exit code 1
- Missing environment variables → print error to stderr, exit code 1
- LLM API error (timeout, connection error, non-200 response) → print error to stderr, exit code 1
- Response timeout > 60 seconds → print error to stderr, exit code 1

## Dependencies

Use existing project dependencies from `pyproject.toml`:
- `httpx` — async HTTP client for API calls
- `pydantic-settings` — environment variable loading (optional, can use `os.environ`)

## Testing Strategy

Create one regression test in `backend/tests/unit/test_agent.py`:

```python
def test_agent_output_structure():
    """Test that agent.py outputs valid JSON with required fields."""
    result = subprocess.run(
        ["uv", "run", "agent.py", "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=60
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "answer" in output
    assert "tool_calls" in output
    assert isinstance(output["tool_calls"], list)
```

## Files to Create

1. `plans/task-1.md` — this plan
2. `agent.py` — main agent CLI
3. `AGENT.md` — documentation
4. `backend/tests/unit/test_agent.py` — regression test

## Acceptance Criteria Checklist

- [ ] Plan committed before code
- [ ] `agent.py` exists and runs with `uv run`
- [ ] Output is valid JSON with `answer` and `tool_calls`
- [ ] API key stored in `.env.agent.secret`
- [ ] `AGENT.md` documents the solution
- [ ] 1 regression test passes
