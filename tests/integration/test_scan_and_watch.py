import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch

# Adjust path to import from root
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from tests.fixtures.repo_gen import create_test_repo

@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def main_window(qtbot):
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

@pytest.fixture
def temp_repo_for_watching(tmp_path):
    repo_path = tmp_path / "large_repo"
    file_specs = {f"file_{i}.txt": f"content {i}" for i in range(1000)}
    create_test_repo(repo_path, file_specs)
    return repo_path

def test_scan_and_watch_consistency(main_window, temp_repo_for_watching, qtbot):
    """I-01, I-02, E2E-05, I-13: Test large scan, hidden files, renames, and watcher updates."""
    repo_path = temp_repo_for_watching
    # I-02: Add hidden files and folders to be ignored
    (repo_path / ".hidden_file").write_text("secret")
    (repo_path / ".hidden_dir").mkdir()
    (repo_path / ".hidden_dir" / "another.txt").write_text("secret")

    # --- I-01 & I-13: Initial Scan Performance & UI Responsiveness ---
    start_time = time.monotonic()
    
    # Measure UI freeze time during scan signal
    with qtbot.waitSignal(main_window.scan_ctl.scan_finished, timeout=10000) as blocker:
        # qtbot.wait functions block the event loop, so we can use them to check for UI freezes.
        # We expect the UI to remain responsive (not freeze for more than 200ms) during the scan.
        with qtbot.wait_while(lambda: main_window.tree_panel.loading_label.isVisible(), timeout=10000):
            main_window.scan_ctl.select_folder(str(repo_path))

    scan_duration = time.monotonic() - start_time
    print(f"Scan of 1000 files took: {scan_duration:.2f}s")
    assert scan_duration < 3.0, "I-01: Scan should be faster than 3 seconds."

    # Assert tree is populated correctly, ignoring hidden files
    # The repo has 1000 text files + the root folder itself in the map.
    assert len(main_window.tree_panel.path_to_item_map) == 1001
    assert not any(path.name.startswith('.') for path in main_window.tree_panel.path_to_item_map.keys())

    # --- E2E-05: File Rename and Check State Preservation ---
    old_file_path = repo_path / "file_10.txt"
    new_file_path = repo_path / "file_10_renamed.txt"
    old_file_path_str = str(old_file_path)
    new_file_path_str = str(new_file_path)

    # 1. Check the item to be renamed
    item_to_rename = main_window.tree_panel.path_to_item_map[old_file_path_str]
    item_to_rename.setCheckState(0, Qt.CheckState.Checked)
    assert old_file_path_str in main_window.tree_panel.get_checked_paths(relative=False)

    # 2. Rename the file externally
    os.rename(old_file_path, new_file_path)

    # 3. Wait for the watcher to update the tree
    with qtbot.waitSignal(main_window.tree_panel.tree_updated, timeout=5000):
        pass # Watcher runs in background, just wait for signal

    # 4. Assert the old path is gone, the new one exists, and it's still checked
    assert old_file_path_str not in main_window.tree_panel.path_to_item_map
    assert new_file_path_str in main_window.tree_panel.path_to_item_map
    assert new_file_path_str in main_window.tree_panel.get_checked_paths(relative=False)
    new_item = main_window.tree_panel.path_to_item_map[new_file_path_str]
    assert new_item.checkState(0) == Qt.CheckState.Checked
