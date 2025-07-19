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

    workspace_manager.save_workspaces(workspaces_data, base_path=temp_dir)
    loaded_workspaces = workspace_manager.load_workspaces(base_path=temp_dir)

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
    default_workspaces = workspace_manager.load_workspaces(base_path=temp_dir)
    workspace_file = temp_dir / workspace_manager.WORKSPACE_FILE

    assert "Default" in default_workspaces
    assert default_workspaces["last_active_workspace"] == "Default"
    assert workspace_file.exists()

def test_load_workspaces_malformed_json(temp_dir):
    """Test that a default workspace is returned if the JSON is invalid."""
    workspace_file = temp_dir / workspace_manager.WORKSPACE_FILE
    with open(workspace_file, 'w') as f:
        f.write("this is not json")

    with patch('builtins.print') as mock_print:
        default_workspaces = workspace_manager.load_workspaces(base_path=temp_dir)
        mock_print.assert_any_call(f"Could not load primary workspace file '{workspace_file}': Expecting value: line 1 column 1 (char 0)")

    assert "Default" in default_workspaces
    assert default_workspaces["last_active_workspace"] == "Default"

def test_checksum_verification_success(temp_dir):
    """Test that a correctly saved file passes checksum verification."""
    workspaces_data = {
        "TestWS": {"folder_path": "path/a"},
        "last_active_workspace": "TestWS"
    }
    workspace_manager.save_workspaces(workspaces_data, base_path=temp_dir)
    loaded = workspace_manager.load_workspaces(base_path=temp_dir)
    assert loaded["last_active_workspace"] == "TestWS"

def test_checksum_mismatch_triggers_fallback(temp_dir):
    """Test that a tampered file fails checksum and triggers fallback to default."""
    workspace_file = temp_dir / workspace_manager.WORKSPACE_FILE
    workspace_manager.save_workspaces({"TestWS": {}, "last_active_workspace": "TestWS"}, base_path=temp_dir)

    with open(workspace_file, 'r+') as f:
        content = json.load(f)
        content['workspaces']['TestWS']['folder_path'] = 'path/b'
        f.seek(0)
        json.dump(content, f, indent=4)
        f.truncate()

    with patch('builtins.print') as mock_print:
        loaded = workspace_manager.load_workspaces(base_path=temp_dir)
        mock_print.assert_any_call(f"Could not load primary workspace file '{workspace_file}': Checksum mismatch.")
    
    assert loaded['last_active_workspace'] == 'Default'

def test_restore_from_backup_on_corruption(temp_dir):
    """Test that the system restores from the .bak file if the main file is corrupt."""
    workspace_file = temp_dir / workspace_manager.WORKSPACE_FILE
    backup_file = workspace_file.with_suffix('.json.bak')
    original_data = {"GoodWS": {}, "last_active_workspace": "GoodWS"}
    
    # 1. Creates workspaces.json and then .bak
    workspace_manager.save_workspaces(original_data, base_path=temp_dir)
    workspace_manager.save_workspaces(original_data, base_path=temp_dir)

    # 2. Corrupt the main file
    with open(workspace_file, 'w') as f:
        f.write("this is not json")

    # 3. Load should now trigger restore from backup
    with patch('builtins.print') as mock_print:
        loaded = workspace_manager.load_workspaces(base_path=temp_dir)
        mock_print.assert_any_call(f"Attempting to restore from backup: {backup_file}")

    assert loaded['last_active_workspace'] == 'GoodWS'

def test_full_workspace_data_roundtrip(temp_dir):
    """Test that all new workspace fields are persisted correctly."""
    full_data = {
        "FullWS": {
            "folder_path": "path/c",
            "scan_settings": {"live_watcher": False},
            "selection_groups": {"Group1": ["file1", "file2"]},
            "active_selection_group": "Group1",
            "use_local_templates": True,
            "local_custom_instructions": {"Local1": "local text"}
        },
        "last_active_workspace": "FullWS"
    }
    workspace_manager.save_workspaces(full_data, base_path=temp_dir)
    loaded = workspace_manager.load_workspaces(base_path=temp_dir)

    assert loaded['FullWS']['scan_settings']['live_watcher'] is False
    assert loaded['FullWS']['selection_groups'] == {"Group1": ["file1", "file2"]}
    assert loaded['FullWS']['active_selection_group'] == "Group1"
    assert loaded['FullWS']['use_local_templates'] is True
    assert loaded['FullWS']['local_custom_instructions'] == {"Local1": "local text"}

def test_auto_backup_creation_and_pruning(temp_dir):
    """Test that timestamped backups are created and old ones are pruned."""
    for i in range(12):
        workspace_manager.save_workspaces({"last_active_workspace": f"WS{i}"}, base_path=temp_dir)
    
    backup_dir = temp_dir / 'backups'
    assert backup_dir.is_dir()
    # The name of the backup file is based on the name of the workspace file
    backup_files = list(backup_dir.glob(f'{workspace_manager.WORKSPACE_FILE}.*.bak'))
    assert len(backup_files) == 10

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
