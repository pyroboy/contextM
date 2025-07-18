import pytest
import json
import os
from unittest.mock import patch

# Since tests are run from the root, we need to adjust the path
# to import from the 'core' directory.
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core import workspace_manager

@pytest.fixture
def temp_dir(tmp_path):
    """A fixture to create a temporary directory and cd into it for test isolation."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)

# --- Tests for Workspaces --- #

def test_save_and_load_roundtrip(temp_dir):
    """Test that saving and loading a workspace preserves its data."""
    workspaces_data = {
        "TestWS": {
            "folder_path": str(temp_dir / "project"),
            "scan_settings": {
                "include_subfolders": True,
                "ignore_folders": {".git", "node_modules"}
            },
            "instructions": "Test instructions",
            "checked_paths": {str(temp_dir / "project/file1.py")}
        },
        "last_active_workspace": "TestWS"
    }

    workspace_manager.save_workspaces(workspaces_data)
    loaded_workspaces = workspace_manager.load_workspaces()

    # Assertions
    assert loaded_workspaces["last_active_workspace"] == "TestWS"
    loaded_ws_data = loaded_workspaces["TestWS"]
    original_ws_data = workspaces_data["TestWS"]

    assert loaded_ws_data["folder_path"] == original_ws_data["folder_path"]
    assert loaded_ws_data["instructions"] == original_ws_data["instructions"]
    # Verify set -> list -> set conversion for ignore_folders
    assert loaded_ws_data["scan_settings"]["ignore_folders"] == original_ws_data["scan_settings"]["ignore_folders"]
    # Verify set -> list -> list conversion for checked_paths
    assert sorted(loaded_ws_data["checked_paths"]) == sorted(list(original_ws_data["checked_paths"]))

def test_load_workspaces_file_not_found(temp_dir):
    """Test that a default workspace is created if the file doesn't exist."""
    default_workspaces = workspace_manager.load_workspaces()

    assert "Default" in default_workspaces
    assert default_workspaces["last_active_workspace"] == "Default"
    assert os.path.exists(workspace_manager.WORKSPACE_FILE)

def test_load_workspaces_malformed_json(temp_dir):
    """Test that a default workspace is returned if the JSON is invalid."""
    with open(workspace_manager.WORKSPACE_FILE, 'w') as f:
        f.write("this is not json")

    with patch('builtins.print') as mock_print:
        default_workspaces = workspace_manager.load_workspaces()
        mock_print.assert_any_call(f"Error loading workspaces: Expecting value: line 1 column 1 (char 0). Resetting to default.")

    assert "Default" in default_workspaces
    assert default_workspaces["last_active_workspace"] == "Default"

# --- Tests for Custom Instructions --- #

def test_save_and_load_instructions_roundtrip(temp_dir):
    """Test that saving and loading instructions preserves the data."""
    instructions_data = {
        "MyTemplate": "These are my custom instructions.",
        "AnotherTemplate": "More instructions."
    }

    workspace_manager.save_custom_instructions(instructions_data)
    loaded_instructions = workspace_manager.load_custom_instructions()

    assert loaded_instructions == instructions_data

def test_load_instructions_file_not_found(temp_dir):
    """Test that default instructions are created if the file doesn't exist."""
    default_instructions = workspace_manager.load_custom_instructions()

    assert "Default" in default_instructions
    assert os.path.exists(workspace_manager.CUSTOM_INSTRUCTIONS_FILE)
