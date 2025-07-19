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
    """Fixture for a clean MainWindow instance with robust teardown."""
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

@pytest.fixture
def workspaces_with_groups(tmp_path):
    """Fixture for two workspaces with distinct files, settings, and selection groups."""
    ws1_path = tmp_path / "ws1"
    create_test_repo(ws1_path, [("a.py", ""), ("b.txt", ""), ("c.log", "")])
    
    ws2_path = tmp_path / "ws2"
    create_test_repo(ws2_path, [("x.js", ""), ("y.css", ""), ("z.tmp", "")])

    return {
        "WS1": {
            "folder_path": str(ws1_path),
            "scan_settings": {"ignore_folders": set(), "ignore_patterns": {"*.log"}},
            "selection_groups": {
                "Default": {"description": "", "checked_paths": [str(ws1_path / "a.py")]},
                "GroupB": {"description": "", "checked_paths": [str(ws1_path / "b.txt")]}
            }
        },
        "WS2": {
            "folder_path": str(ws2_path),
            "scan_settings": {"ignore_folders": set(), "ignore_patterns": {"*.tmp"}},
            "selection_groups": {
                "Default": {"description": "", "checked_paths": [str(ws2_path / "x.js"), str(ws2_path / "y.css")]}
            }
        },
        "last_active_workspace": "WS1"
    }

@patch('core.watcher.FileWatcherThread')
def test_watcher_restarts_with_correct_filters(MockFileWatcher, main_window_for_switch, two_workspaces, qtbot):
    """I-06: Test that switching workspaces restarts the watcher with the new ignore rules."""
    main_window = main_window_for_switch
    main_window.workspaces = two_workspaces

    # 1. Initial load of WS1, which triggers a scan and starts the watcher
    with qtbot.waitSignal(main_window.scan_ctl.scan_finished, timeout=5000):
        main_window.workspace_ctl.switch("WS1")
    
    MockFileWatcher.assert_called_with(str(two_workspaces["WS1"]["folder_path"]), two_workspaces["WS1"]["scan_settings"]["ignore_patterns"])
    watcher_instance = MockFileWatcher.return_value
    watcher_instance.start.assert_called_once()

    # 2. Switch to WS2
    with qtbot.waitSignal(main_window.scan_ctl.scan_finished, timeout=5000):
        main_window.workspace_ctl.switch("WS2")

    # Assert the old watcher was stopped and a new one was started with WS2's settings
    watcher_instance.stop.assert_called_once()
    MockFileWatcher.assert_called_with(str(two_workspaces["WS2"]["folder_path"]), two_workspaces["WS2"]["scan_settings"]["ignore_patterns"])
    assert watcher_instance.start.call_count == 2

@patch('core.watcher.FileWatcherThread')
def test_workspace_and_group_switching_updates_ui(MockFileWatcher, main_window_for_switch, workspaces_with_groups, qtbot):
    """I-07, I-12: Test that UI elements update correctly on workspace and group switching."""
    main_window = main_window_for_switch
    main_window.workspaces = workspaces_with_groups
    
    # 1. Load WS1 and verify initial state
    with qtbot.waitSignal(main_window.scan_ctl.scan_finished, timeout=5000):
        main_window.workspace_ctl.switch("WS1")

    ws1_data = workspaces_with_groups["WS1"]
    assert main_window.current_folder_path == ws1_data["folder_path"]
    
    # Verify tree is populated and default group paths are checked
    expected_checked = {os.path.normpath(p) for p in ws1_data["selection_groups"]["Default"]["checked_paths"]}
    assert {os.path.normpath(p) for p in main_window.tree_panel.get_checked_paths(relative=False)} == expected_checked

    # 2. Switch selection group to GroupB in WS1
    main_window.sel_ctl.on_group_changed("GroupB")
    qtbot.wait(100) # This is a synchronous UI update, a small wait is fine
    
    expected_checked = {os.path.normpath(p) for p in ws1_data["selection_groups"]["GroupB"]["checked_paths"]}
    assert {os.path.normpath(p) for p in main_window.tree_panel.get_checked_paths(relative=False)} == expected_checked

    # 3. Switch to WS2 and verify state
    with qtbot.waitSignal(main_window.scan_ctl.scan_finished, timeout=5000):
        main_window.workspace_ctl.switch("WS2")

    ws2_data = workspaces_with_groups["WS2"]
    assert main_window.current_folder_path == ws2_data["folder_path"]
    
    # Verify tree updates and checks paths from WS2's default group
    expected_checked = {os.path.normpath(p) for p in ws2_data["selection_groups"]["Default"]["checked_paths"]}
    assert {os.path.normpath(p) for p in main_window.tree_panel.get_checked_paths(relative=False)} == expected_checked
