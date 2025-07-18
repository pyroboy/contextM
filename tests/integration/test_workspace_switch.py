import pytest
import os
from unittest.mock import patch, MagicMock

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
def main_window_for_switch(qtbot):
    # Use a fresh main window for this test
    window = MainWindow()
    window.show()
    qtbot.addWidget(window)
    qtbot.wait(100)
    return window

@pytest.fixture
def two_workspaces(tmp_path):
    # Workspace 1: Ignores .log files
    ws1_path = tmp_path / "ws1"
    create_test_repo(ws1_path, [("file.py", ""), ("data.log", "")])
    
    # Workspace 2: Ignores .tmp files
    ws2_path = tmp_path / "ws2"
    create_test_repo(ws2_path, [("script.js", ""), ("temp.tmp", "")])

    workspaces_data = {
        "WS1": {
            "folder_path": str(ws1_path),
            "scan_settings": {"ignore_folders": set(), "ignore_patterns": {"*.log"}},
            "instructions": "", "checked_paths": set()
        },
        "WS2": {
            "folder_path": str(ws2_path),
            "scan_settings": {"ignore_folders": set(), "ignore_patterns": {"*.tmp"}},
            "instructions": "", "checked_paths": set()
        },
        "last_active_workspace": "WS1"
    }
    return workspaces_data

@patch('core.watcher.FileWatcherThread')
def test_watcher_restarts_with_correct_filters(MockFileWatcher, main_window_for_switch, two_workspaces, qtbot):
    """
    Test that switching workspaces restarts the watcher with the new ignore rules.
    """
    main_window = main_window_for_switch
    main_window.workspace_manager.workspaces = two_workspaces
    main_window.workspace_manager.current_workspace_name = "WS1"
    main_window.workspace_manager.load_workspace("WS1")

    # 1. Initial load of WS1
    main_window.start_file_watcher() 
    qtbot.wait(100)
    MockFileWatcher.assert_called_with(str(two_workspaces["WS1"]["folder_path"]), two_workspaces["WS1"]["scan_settings"]["ignore_patterns"])
    watcher_instance = MockFileWatcher.return_value
    watcher_instance.start.assert_called_once()

    # 2. Switch to WS2
    main_window.workspace_manager.load_workspace("WS2")
    main_window.start_file_watcher() # This would be triggered by the workspace change signal
    qtbot.wait(100)

    # Assert the old watcher was stopped and a new one was started with WS2's settings
    watcher_instance.stop.assert_called_once()
    watcher_instance.wait.assert_called_once()
    MockFileWatcher.assert_called_with(str(two_workspaces["WS2"]["folder_path"]), two_workspaces["WS2"]["scan_settings"]["ignore_patterns"])
    # The mock is the same object, so start would have been called twice now
    assert watcher_instance.start.call_count == 2
