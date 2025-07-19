import pytest
import os
import time
from pathlib import Path
from unittest.mock import patch

# Adjust path to import from root
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from PySide6.QtWidgets import QApplication, QFileDialog
from ui.main_window import MainWindow
from tests.fixtures.repo_gen import create_test_repo
from core import workspace_manager
from PySide6.QtCore import Qt

@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def main_window_e2e(qtbot, tmp_path):
    # Set the testing mode for the workspace manager to use a temp directory
    workspace_manager.set_testing_mode(tmp_path)

    window = MainWindow(test_mode=True, testing_path=tmp_path)
    window.load_initial_data() # Manually load data after test mode is set
    window.show()
    qtbot.addWidget(window)
    qtbot.wait(100)

    try:
        yield window
    finally:
        # Forcefully and explicitly clean up to prevent intermittent test errors.
        if window.file_watcher and window.file_watcher.isRunning():
            window.file_watcher.stop()

        if window.scanner and window.scanner.is_running():
            window.scanner.stop()
            window.scanner.wait_for_completion(1000)

        window.close()
        qtbot.wait(50) # Allow event loop to process final events

        # Reset the testing mode after the test
        workspace_manager.set_testing_mode(None)

@pytest.fixture
def two_repos_for_e2e(tmp_path):
    """Fixture to create two distinct test repositories."""
    repo1_path = tmp_path / "repo1"
    repo2_path = tmp_path / "repo2"
    create_test_repo(repo1_path, {"file1.txt": "content1"})
    create_test_repo(repo2_path, {"file2.py": "content2"})
    return repo1_path, repo2_path

@pytest.fixture
def temp_repo_for_e2e(tmp_path):
    repo_path = tmp_path / "e2e_repo"
    file_specs = {
        "main.py": "# Python code",
        "README.md": "# Project Readme",
        "utils/helpers.js": "// JS code"
    }
    create_test_repo(repo_path, file_specs)
    return repo_path

@patch('pyperclip.copy')
@patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory')
def test_full_user_flow(mock_get_dir, mock_copy, main_window_e2e, temp_repo_for_e2e, qtbot):
    """Simulate a full user workflow from selecting a folder to copying context."""
    main_window = main_window_e2e
    mock_get_dir.return_value = str(temp_repo_for_e2e)

    # 1. Click "Select Folder" button and wait for scan to complete
    with qtbot.waitSignal(main_window.scanner.scan_completed, timeout=5000):
        qtbot.mouseClick(main_window.select_folder_button, Qt.MouseButton.LeftButton)
    
    mock_get_dir.assert_called_once()

    # 2. Check files in the tree, select two
    qtbot.waitUntil(lambda: len(main_window.tree_panel.path_to_item_map) == 3, timeout=1000)
    item1 = main_window.tree_panel.path_to_item_map[str(temp_repo_for_e2e / "main.py")]
    item2 = main_window.tree_panel.path_to_item_map[str(temp_repo_for_e2e / "README.md")]
    item1.setCheckState(Qt.CheckState.Checked)
    item2.setCheckState(Qt.CheckState.Checked)
    qtbot.wait(100) # Allow signals to process

    # 3. Click the aggregate button and assert clipboard content
    qtbot.mouseClick(main_window.instructions_panel.copy_button, Qt.MouseButton.LeftButton)
    qtbot.wait(100)
    mock_copy.assert_called_once()
    clipboard_content = mock_copy.call_args[0][0]
    assert "`main.py`" in clipboard_content
    assert "# Python code" in clipboard_content
    assert "`README.md`" in clipboard_content
    assert "# Project Readme" in clipboard_content
    assert "helpers.js" not in clipboard_content

    # 4. Create a new file and verify the UI detects it
    new_file_path = temp_repo_for_e2e / "new_feature.py"
    with qtbot.waitSignal(main_window.file_changes_panel.request_refresh, timeout=5000):
        new_file_path.write_text("# A new feature")
        # The watcher will detect the change and the file_changes_panel will emit request_refresh

    # 5. Refresh the view and assert the new file is present
    with qtbot.waitSignal(main_window.scanner.scan_completed, timeout=5000):
        qtbot.mouseClick(main_window.file_changes_panel.refresh_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: str(new_file_path) in main_window.tree_panel.path_to_item_map, timeout=1000)
    assert len(main_window.tree_panel.path_to_item_map) == 4


def test_workspace_switching_flow(main_window_e2e, two_repos_for_e2e, qtbot):
    """E2E-01: Test creating and switching between two workspaces."""
    main_window = main_window_e2e
    repo1, repo2 = two_repos_for_e2e

    # 1. Setup Workspace 1
    main_window.workspace_ctl.add_workspace("Workspace 1")
    main_window.workspace_ctl.select_workspace("Workspace 1")
    main_window.scan_ctl.select_folder(str(repo1))
    qtbot.wait(500) # Allow scan to complete
    item1 = main_window.tree_panel.path_to_item_map.get(os.path.normpath(os.path.join(repo1, "file1.txt")))
    assert item1 is not None
    item1.setCheckState(Qt.CheckState.Checked)
    qtbot.wait(100)

    # 2. Setup Workspace 2
    main_window.workspace_ctl.add_workspace("Workspace 2")
    main_window.workspace_ctl.select_workspace("Workspace 2")
    main_window.scan_ctl.select_folder(str(repo2))
    qtbot.wait(500) # Allow scan to complete
    item2 = main_window.tree_panel.path_to_item_map.get(os.path.normpath(os.path.join(repo2, "file2.py")))
    assert item2 is not None
    item2.setCheckState(Qt.CheckState.Checked)
    qtbot.wait(100)

    # 3. Switch back to Workspace 1 and verify state
    main_window.workspace_ctl.select_workspace("Workspace 1")
    qtbot.wait(500) # Allow UI to update and rescan
    assert main_window.folder_path_label.text() == str(repo1)
    assert os.path.normpath(os.path.join(repo1, "file1.txt")) in main_window.tree_panel.path_to_item_map
    assert os.path.normpath(os.path.join(repo2, "file2.py")) not in main_window.tree_panel.path_to_item_map
    item1_reloaded = main_window.tree_panel.path_to_item_map.get(os.path.normpath(os.path.join(repo1, "file1.txt")))
    assert item1_reloaded.checkState() == Qt.CheckState.Checked

    # 4. Switch back to Workspace 2 and verify state
    main_window.workspace_ctl.select_workspace("Workspace 2")
    qtbot.wait(500)
    assert main_window.folder_path_label.text() == str(repo2)
    assert os.path.normpath(os.path.join(repo2, "file2.py")) in main_window.tree_panel.path_to_item_map
    assert os.path.normpath(os.path.join(repo1, "file1.txt")) not in main_window.tree_panel.path_to_item_map
    item2_reloaded = main_window.tree_panel.path_to_item_map.get(os.path.normpath(os.path.join(repo2, "file2.py")))
    assert item2_reloaded.checkState() == Qt.CheckState.Checked
