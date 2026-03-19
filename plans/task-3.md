# Plan: Task 3 — The System Agent

## Overview

Add a `query_api` tool to enable the agent to query the deployed backend API. This allows answering questions about:
- Static system facts (framework, ports, status codes)
- Data-dependent queries (item count, scores, analytics)

## LLM Provider and Model

**Provider:** Qwen Code API
**Model:** `qwen3-coder-plus`

## New Tool: `query_api`

### Schema

```json
{
  "name": "query_api",
  "description": "Call the deployed backend API to get real-time data",
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
        "description": "API endpoint path (e.g., /items/, /analytics/completion-rate)"
      },
      "body": {
        "type": "string",
        "description": "Optional JSON request body for POST/PUT requests"
      }
    },
    "required": ["method", "path"]
  }
}
```

### Implementation

```python
def tool_query_api(method: str, path: str, body: Optional[str] = None) -> str:
    """
    Call the deployed backend API.
    
    - Uses AGENT_API_BASE_URL from environment (default: http://localhost:42002)
    - Authenticates with LMS_API_KEY from .env.docker.secret
    - Returns JSON with status_code and response body
    """
```

## Environment Variables

The agent reads configuration from two files:

| Variable | Purpose | Source File |
|----------|---------|-------------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for query_api auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for query_api (optional) | `.env.agent.secret` or default |

### Loading Strategy

```python
def get_backend_config() -> dict[str, str]:
    """Load backend configuration from .env.docker.secret."""
    env_vars = load_env_file(Path(__file__).parent / ".env.docker.secret")
    
    lms_api_key = os.environ.get("LMS_API_KEY") or env_vars.get("LMS_API_KEY")
    agent_api_base = os.environ.get(
        "AGENT_API_BASE_URL",
        "http://localhost:42002"
    )
    
    return {
        "api_key": lms_api_key,
        "api_base": agent_api_base.rstrip("/"),
    }
```

## System Prompt Update

The system prompt should guide the LLM to choose the right tool:

```
You are a documentation and system assistant. You have access to three tools:

1. list_files - List files in a directory
2. read_file - Read a file's contents
3. query_api - Call the deployed backend API

Tool selection guidelines:
- Use list_files/read_file for:
  - Wiki documentation questions
  - Source code analysis
  - Configuration file questions
  
- Use query_api for:
  - Real-time data queries (item count, learner scores)
  - HTTP status code questions
  - API endpoint behavior
  - Analytics data

Always include source references:
- For wiki: wiki/filename.md#section
- For source code: path/to/file.py:function
- For API: endpoint path (e.g., GET /items/)
```

## Agentic Loop

The loop remains the same as Task 2, but now handles three tools:

```
Question ──▶ LLM ──▶ tool call? ──yes──▶ execute tool ──▶ back to LLM
                         │
                         no
                         │
                         ▼
                    JSON output
```

## Authentication

The `query_api` tool authenticates with the backend using `LMS_API_KEY`:

```python
headers = {
    "Authorization": f"Bearer {config['api_key']}",
    "Content-Type": "application/json",
}
```

## Benchmark Questions

The agent must pass 10 questions in `run_eval.py`:

| # | Question Type | Expected Tool | Keywords |
|---|---------------|---------------|----------|
| 0 | Wiki lookup | read_file | branch, protect |
| 1 | Wiki lookup | read_file | ssh, key |
| 2 | Source code | read_file | FastAPI |
| 3 | Source code | list_files | items, interactions, analytics |
| 4 | Data query | query_api | number > 0 |
| 5 | API behavior | query_api | 401, 403 |
| 6 | Bug diagnosis | query_api + read_file | ZeroDivisionError |
| 7 | Bug diagnosis | query_api + read_file | TypeError, NoneType |
| 8 | System reasoning | read_file | 4+ hops |
| 9 | Pipeline reasoning | read_file | external_id, idempotency |

## Iteration Strategy

1. **First run:** Execute `run_eval.py` to see baseline score
2. **Analyze failures:** For each failing question:
   - Check if correct tool was called
   - Check if answer contains expected keywords
   - Adjust system prompt or tool descriptions
3. **Common fixes:**
   - Tool not called → improve tool description
   - Wrong arguments → clarify parameter descriptions
   - Answer missing keywords → adjust system prompt
   - API errors → fix authentication or URL

## Files to Create/Update

1. `plans/task-3.md` — this plan
2. `agent.py` — add query_api tool
3. `.env.docker.secret` — ensure LMS_API_KEY is set
4. `AGENT.md` — update documentation
5. `tests/test_agent_task3.py` — 2 regression tests

## Acceptance Criteria Checklist

- [ ] Plan committed before code
- [ ] `query_api` tool defined with schema
- [ ] Authentication with LMS_API_KEY
- [ ] Agent reads all config from environment
- [ ] Static system questions answered correctly
- [ ] Data-dependent questions answered correctly
- [ ] `run_eval.py` passes all 10 questions
- [ ] `AGENT.md` documents architecture (200+ words)
- [ ] 2 regression tests pass
- [ ] Autochecker benchmark passes

## Initial Benchmark Score

*To be filled after first run of run_eval.py*

## Iteration Log

*To be filled during debugging*
