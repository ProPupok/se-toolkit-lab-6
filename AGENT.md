# Lab Assistant Agent

A CLI agent that answers questions using an LLM via OpenAI-compatible API.

## Architecture

```
User question → agent.py → LLM API → JSON answer
```

### Components

- **`agent.py`** — Main CLI entry point
  - Parses command-line arguments
  - Loads LLM configuration from `.env.agent.secret`
  - Calls LLM via HTTP async request
  - Outputs structured JSON to stdout

- **`.env.agent.secret`** — Environment configuration (gitignored)
  - `LLM_API_KEY` — API key for authentication
  - `LLM_API_BASE` — Base URL of the LLM provider
  - `LLM_MODEL` — Model name to use

- **LLM Provider** — Qwen Code API (OpenAI-compatible endpoint)
  - Model: `qwen3-coder-plus`
  - 1000 free requests per day
  - Works from Russia without credit card

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
uv run agent.py "What does REST stand for?"
```

**Output:**
```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Output Format

- `answer` (string) — The LLM's response to the question
- `tool_calls` (array) — Empty for Task 1, will be populated in Task 2

### Error Handling

- Missing arguments → prints usage to stderr, exits with code 1
- Missing configuration → prints error to stderr, exits with code 1
- API errors → prints error to stderr, exits with code 1
- Timeout (>60s) → prints error to stderr, exits with code 1

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

## Development

### Dependencies

Uses existing project dependencies from `pyproject.toml`:
- `httpx` — async HTTP client
- `pydantic-settings` — (optional) environment loading

### Code Structure

```
agent.py
├── load_env_file()      — Parse .env.agent.secret
├── get_llm_config()     — Load and validate configuration
├── call_llm()           — Async HTTP request to LLM API
└── main()               — CLI entry point
```

## Tasks Progress

| Task | Description | Status |
|------|-------------|--------|
| 1 | Call an LLM from Code | ✅ Implemented |
| 2 | Add Tool Calling | ⏳ Pending |
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
