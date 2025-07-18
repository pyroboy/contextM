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

@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def main_window_e2e(qtbot):
    window = MainWindow()
    window.show()
    qtbot.addWidget(window)
    qtbot.wait(100)
    return window

@pytest.fixture
def temp_repo_for_e2e(tmp_path):
    repo_path = tmp_path / "e2e_repo"
    file_specs = [
        ("main.py", "# Python code"),
        ("README.md", "# Project Readme"),
        ("utils/helpers.js", "// JS code")
    ]
    create_test_repo(repo_path, file_specs)
    return repo_path

@patch('pyperclip.copy')
@patch('PySide6.QtWidgets.QFileDialog.getExistingDirectory')
def test_full_user_flow(mock_get_dir, mock_copy, main_window_e2e, temp_repo_for_e2e, qtbot):
    """Simulate a full user workflow from selecting a folder to copying context."""
    main_window = main_window_e2e
    mock_get_dir.return_value = str(temp_repo_for_e2e)

    # 1. Click "Select Folder" button
    qtbot.mouseClick(main_window.select_folder_button, Qt.MouseButton.LeftButton)
    qtbot.wait(100) # Allow dialog mock to be called
    mock_get_dir.assert_called_once()

    # Wait for the initial scan to complete
    with qtbot.waitSignal(main_window.tree_panel.scan_completed, timeout=5000):
        pass # The signal is triggered by the folder selection

    # 2. Check two files in the tree
    assert len(main_window.tree_panel.path_to_item_map) == 3
    item1 = main_window.tree_panel.path_to_item_map[str(temp_repo_for_e2e / "main.py")]
    item2 = main_window.tree_panel.path_to_item_map[str(temp_repo_for_e2e / "README.md")]
    item1.setCheckState(0, Qt.CheckState.Checked)
    item2.setCheckState(0, Qt.CheckState.Checked)
    qtbot.wait(100) # Allow signals to process

    # 3. Click the aggregate button and assert clipboard content
    qtbot.mouseClick(main_window.aggregation_panel.aggregate_button, Qt.MouseButton.LeftButton)
    qtbot.wait(100)
    mock_copy.assert_called_once()
    clipboard_content = mock_copy.call_args[0][0]
    assert "`main.py`" in clipboard_content
    assert "# Python code" in clipboard_content
    assert "`README.md`" in clipboard_content
    assert "# Project Readme" in clipboard_content
    assert "helpers.js" not in clipboard_content

    # 4. Create a new file externally and assert UI updates
    new_file_path = temp_repo_for_e2e / "new_feature.py"
    with qtbot.waitSignal(main_window.tree_panel.tree_updated, timeout=5000):
        new_file_path.write_text("# A new feature")
        # The watcher will detect the change and trigger the update

    # Assert status bar message appears
    assert f"File system change detected: created {new_file_path}" in main_window.status_bar.currentMessage()
    # Assert new file is in the tree
    assert str(new_file_path) in main_window.tree_panel.path_to_item_map
    assert len(main_window.tree_panel.path_to_item_map) == 4
