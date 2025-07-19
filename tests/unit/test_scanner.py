import pytest
from unittest.mock import MagicMock, patch
import os
import time

# Adjust path to import from 'core'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core.directory_scanner import DirectoryScanner
from tests.fixtures.repo_gen import create_test_repo

@pytest.fixture
def temp_repo(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    # Create a dummy structure
    (repo_path / "file1.py").write_text("print('hello')")
    (repo_path / "folder1").mkdir()
    (repo_path / "folder1" / "file2.txt").write_text("world")
    return repo_path

def test_scanner_emits_correct_items(temp_repo, monkeypatch):
    """U-02, I-03, I-04: Verify scanner emits items correctly, handling batches, large files, and ignored folders."""
    # Setup a more complex repo within the fixture
    (temp_repo / "folder_to_ignore").mkdir()
    (temp_repo / "folder_to_ignore" / "ignored_file.txt").write_text("ignored")
    
    oversized_file = temp_repo / "oversized.log"
    # Mock MAX_FILE_SIZE_KB from the scanner's perspective
    monkeypatch.setattr("core.directory_scanner.MAX_FILE_SIZE_KB", 1)
    monkeypatch.setattr("core.directory_scanner.MAX_FILE_SIZE_BYTES", 1024)
    oversized_file.write_text("A" * 2048) # 2KB file

    # Mock batch size to test batching logic
    monkeypatch.setattr("core.directory_scanner.SCAN_BATCH_SIZE", 2)

    settings = {'include_subfolders': True, 'ignore_folders': {"folder_to_ignore"}}
    scanner = DirectoryScanner(str(temp_repo), settings)

    mock_slot = MagicMock()
    scanner.items_discovered.connect(mock_slot)

    scanner.run() # run directly in the main thread for testing

    assert mock_slot.call_count >= 2 # Root emit + at least one batch

    # Collect all emitted items from all calls (except the root dir emit)
    all_emitted_items = []
    for call in mock_slot.call_args_list:
        all_emitted_items.extend(call.args[0])

        # Remove the root item that is emitted first
        emitted_paths = {item[0] for item in all_emitted_items}
        emitted_paths.remove(str(temp_repo))

        # Assert ignored folder and its contents are NOT present
        assert str(temp_repo / "folder_to_ignore") not in emitted_paths
        assert str(temp_repo / "folder_to_ignore" / "ignored_file.txt") not in emitted_paths

        # Assert oversized file is present and marked invalid
        oversized_item = next((item for item in all_emitted_items if item[0] == str(oversized_file)), None)
        assert oversized_item is not None
        assert oversized_item[2] is False # is_valid
        assert "Exceeds size limit" in oversized_item[3] # reason

        # Assert normal files are present and valid
        file1_item = next((item for item in all_emitted_items if item[0] == str(temp_repo / "file1.py")), None)
        assert file1_item is not None
        assert file1_item[2] is True # is_valid

        # Check batching was respected
        # First call is root, subsequent calls are batches.
        # With batch size 2, we expect calls for [root], [item1, item2], [item3, item4], etc.
        assert len(mock_emit.call_args_list[1][0][0]) <= 2

def test_scanner_stops_on_request(temp_repo):
    """Verify the scanner thread terminates when stop() is called."""
    settings = {'include_subfolders': True, 'ignore_folders': set()}
    scanner = DirectoryScanner(str(temp_repo), settings)
    scanner.start()
    assert scanner.isRunning()
    
    scanner.stop()
    scanner.wait(1000) # Wait for thread to finish
    
    assert not scanner.isRunning()

def test_scanner_error_on_unreadable_root(tmp_path):
    """Test that the 'error_signal' is emitted for a bad path."""
    bad_path = tmp_path / "non_existent_directory"
    bad_path_str = str(bad_path)
    scanner = DirectoryScanner(bad_path_str, MagicMock())

    mock_slot = MagicMock()
    scanner.error_signal.connect(mock_slot)

    scanner.run()

    mock_slot.assert_called_once_with(bad_path_str, "Selected path is not a valid directory.")
