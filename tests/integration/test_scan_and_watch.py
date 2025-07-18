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
    window = MainWindow()
    window.show()
    qtbot.addWidget(window)
    # Allow time for the window to initialize
    qtbot.wait(100)
    return window

@pytest.fixture
def temp_repo_for_watching(tmp_path):
    repo_path = tmp_path / "large_repo"
    file_specs = [ (f"file_{i}.txt", f"content {i}") for i in range(1000) ]
    create_test_repo(repo_path, file_specs)
    return repo_path

def test_scan_and_watch_consistency(main_window, temp_repo_for_watching, qtbot):
    """
    Test creating 1000 files, scanning, then deleting 500 
    and asserting the tree view stays consistent via the watcher.
    """
    # 1. Simulate selecting the folder to trigger the initial scan
    with qtbot.waitSignal(main_window.tree_panel.scan_completed, timeout=5000):
        main_window.workspace_manager.update_workspace_folder(str(temp_repo_for_watching))
    
    # Give the UI a moment to settle
    qtbot.wait(200)

    # 2. Assert that all 1000 files are initially in the tree
    assert len(main_window.tree_panel.path_to_item_map) == 1000
    root_item = main_window.tree_panel.tree.topLevelItem(0)
    assert root_item.childCount() == 1000

    # 3. Delete 500 files externally
    files_to_delete = list(main_window.tree_panel.path_to_item_map.keys())[:500]
    for file_path in files_to_delete:
        os.remove(file_path)

    # 4. Wait for the watcher to detect changes and update the tree
    # The watcher should emit a 'files_changed' signal which the main window
    # connects to its 'on_files_changed' slot.
    # We wait for the tree's update signal as the final confirmation.
    with qtbot.waitSignal(main_window.tree_panel.tree_updated, timeout=5000):
        # The watcher runs in a background thread, so we just need to wait.
        pass

    # 5. Assert that the tree now contains only 500 files
    assert len(main_window.tree_panel.path_to_item_map) == 500
    assert root_item.childCount() == 500
