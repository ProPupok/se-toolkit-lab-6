"""Regression tests for agent.py Task 2: The Documentation Agent.

These tests verify that the agent uses tools correctly to answer questions
based on wiki documentation.

Run with: uv run pytest tests/test_agent_task2.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def run_agent(question: str) -> tuple[int, dict, str]:
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
        timeout=120,  # Longer timeout for agentic loop
        cwd=project_root,
    )
    
    output = json.loads(result.stdout) if result.stdout else {}
    return result.returncode, output, result.stderr


def test_documentation_agent_read_file():
    """Test that agent uses read_file to answer questions about git workflow.
    
    Question: "How do you resolve a merge conflict?"
    
    Verifies:
    - Agent runs successfully (exit code 0)
    - read_file is used in tool_calls
    - source field contains wiki/git-workflow.md reference
    - answer is not empty
    """
    returncode, output, stderr = run_agent("How do you resolve a merge conflict?")
    
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
    
    # Verify source contains wiki reference
    assert "wiki/" in output["source"].lower() or "git" in output["source"].lower(), \
        f"Expected wiki reference in source, got: {output['source']}"


def test_documentation_agent_list_files():
    """Test that agent uses list_files to explore wiki structure.
    
    Question: "What files are in the wiki?"
    
    Verifies:
    - Agent runs successfully (exit code 0)
    - list_files is used in tool_calls
    - answer is not empty
    """
    returncode, output, stderr = run_agent("What files are in the wiki?")
    
    # Check exit code
    assert returncode == 0, f"Agent failed with stderr: {stderr}"
    
    # Verify required fields
    assert "answer" in output, "Missing 'answer' field"
    assert "source" in output, "Missing 'source' field"
    assert "tool_calls" in output, "Missing 'tool_calls' field"
    
    # Verify answer is not empty
    assert len(output["answer"].strip()) > 0, "'answer' cannot be empty"
    
    # Verify list_files was used
    tool_names = [call["tool"] for call in output["tool_calls"]]
    assert "list_files" in tool_names, f"Expected 'list_files' in tool_calls, got: {tool_names}"
