# tests/integration/test_truncation_message.py

import pytest
import os
from unittest.mock import patch

# Adjust path to import from root
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ui.main_window import MainWindow
from tests.fixtures.repo_gen import create_test_repo

@pytest.fixture
def main_window(qtbot):
    """Fixture for a clean MainWindow instance with robust teardown."""
    # Use test_mode to prevent auto-loading and scanning on startup
    window = MainWindow(test_mode=True)
    window.show()
    qtbot.addWidget(window)
    qtbot.wait(100)

    try:
        yield window
    finally:
        # Explicitly stop threads and close window for stable tests
        if window.file_watcher and window.file_watcher.isRunning():
            window.file_watcher.stop()
        if window.scanner and window.scanner.is_running():
            window.scanner.stop()
            window.scanner.wait_for_completion(1000)
        window.close()
        qtbot.wait(50)

@patch('core.directory_scanner.MAX_FILE_SIZE_KB', 1) # Patch to 1 KB for testing
def test_large_file_shows_truncation_message(main_window, tmp_path, qtbot):
    """
    I-11: Test that selecting a file larger than MAX_FILE_SIZE_KB shows a truncation message.
    """
    # 1. Create a test repo with a file larger than the patched limit (1KB)
    repo_path = tmp_path / "test_repo"
    large_file_content = 'a' * 1500 # > 1KB
    create_test_repo(repo_path, [("large_file.txt", large_file_content)])

    # 2. Scan the folder and wait for the signal that it's complete
    with qtbot.waitSignal(main_window.scan_ctl.scan_finished, timeout=5000):
        main_window.scan_ctl.select_folder(str(repo_path))

    # 3. Check the large file in the tree
    large_file_path = os.path.join(repo_path, "large_file.txt")
    item = main_window.tree_panel.path_to_item_map.get(os.path.normpath(large_file_path))
    assert item is not None, "Large file not found in tree."
    item.setCheckState(0, pytest.Qt.CheckState.Checked)
    qtbot.wait(100) # Allow signals to process

    # 4. Verify the aggregation view shows the truncation message
    aggregated_content = main_window.aggregation_view.get_content()
    expected_truncation_msg = f"... (truncated at 1KB)"
    
    assert large_file_content[:1024] in aggregated_content
    assert expected_truncation_msg in aggregated_content
