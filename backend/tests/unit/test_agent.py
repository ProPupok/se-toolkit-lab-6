"""Unit tests for agent.py CLI.

These tests verify that the agent outputs valid JSON with required fields.
Run with: uv run pytest backend/tests/unit/test_agent.py -v
"""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_output_structure():
    """Test that agent.py outputs valid JSON with required fields.
    
    This regression test verifies:
    - agent.py runs successfully (exit code 0)
    - stdout contains valid JSON
    - JSON has 'answer' field (string)
    - JSON has 'tool_calls' field (array)
    """
    # Get the project root directory (parent of backend/)
    project_root = Path(__file__).parent.parent.parent.parent
    agent_path = project_root / "agent.py"
    
    # Run agent with a simple question
    result = subprocess.run(
        [sys.executable, "-m", "uv", "run", str(agent_path), "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root,
    )
    
    # Check exit code
    assert result.returncode == 0, f"Agent failed with stderr: {result.stderr}"
    
    # Parse JSON output
    output = json.loads(result.stdout)
    
    # Verify required fields exist
    assert "answer" in output, "Missing 'answer' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"
    
    # Verify field types
    assert isinstance(output["answer"], str), "'answer' must be a string"
    assert isinstance(output["tool_calls"], list), "'tool_calls' must be an array"
    
    # Verify answer is not empty
    assert len(output["answer"].strip()) > 0, "'answer' cannot be empty"
