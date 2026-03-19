"""Regression tests for agent.py Task 3: The System Agent.

These tests verify that the agent uses query_api and other tools correctly.

Run with: uv run pytest tests/test_agent_task3.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def run_agent(question: str, timeout: int = 120) -> tuple[int, dict, str]:
    """
    Run the agent with a question and parse the output.
    
    Returns:
        Tuple of (returncode, output_dict, stderr)
    """
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"
    
    result = subprocess.run(
        [sys.executable, "-m", "uv", "run", str(agent_path), question],
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=project_root,
    )
    
    output = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, output, result.stderr


def test_system_agent_read_file_for_framework():
    """Test that agent uses read_file to identify the backend framework.
    
    Question: "What Python web framework does the backend use?"
    
    Verifies:
    - Agent runs successfully (exit code 0)
    - read_file is used in tool_calls
    - answer mentions FastAPI
    """
    returncode, output, stderr = run_agent("What Python web framework does the backend use?")
    
    # Check exit code
    assert returncode == 0, f"Agent failed with stderr: {stderr}"
    
    # Verify required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "source" in output, "Missing 'source' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    
    # Verify answer is not empty
    assert len(output["answer"].strip()) > 0, "'answer' cannot be empty"
    
    # Verify read_file was used
    tool_names = [call["tool"] for call in output["tool_calls"]]
    assert "read_file" in tool_names, f"Expected 'read_file' in tool_calls, got: {tool_names}"
    
    # Verify answer mentions FastAPI (case-insensitive)
    assert "fastapi" in output["answer"].lower(), \
        f"Expected 'FastAPI' in answer, got: {output['answer']}"


def test_system_agent_query_api_for_items():
    """Test that agent uses query_api to get data from the backend.
    
    Question: "How many items are in the database?"
    
    Verifies:
    - Agent runs successfully (exit code 0)
    - query_api is used in tool_calls
    - answer contains a number > 0
    """
    returncode, output, stderr = run_agent("How many items are in the database?")
    
    # Check exit code
    assert returncode == 0, f"Agent failed with stderr: {stderr}"
    
    # Verify required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "source" in output, "Missing 'source' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    
    # Verify answer is not empty
    assert len(output["answer"].strip()) > 0, "'answer' cannot be empty"
    
    # Verify query_api was used
    tool_names = [call["tool"] for call in output["tool_calls"]]
    assert "query_api" in tool_names, f"Expected 'query_api' in tool_calls, got: {tool_names}"
    
    # Verify answer contains a number (the item count)
    import re
    numbers = re.findall(r'\d+', output["answer"])
    assert len(numbers) > 0, f"Expected a number in answer, got: {output['answer']}"
