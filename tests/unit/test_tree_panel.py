import pytest
from unittest.mock import MagicMock, patch
import os

# Adjust path to import from 'ui' and 'core'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from PySide6.QtWidgets import QApplication
from ui.widgets.tree_panel import TreePanel

# Required for any Qt-based tests
@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def tree_panel(qtbot):
    # Mock the parent window and its methods if needed
    mock_main_window = MagicMock()
    panel = TreePanel(mock_main_window)
    qtbot.addWidget(panel)
    return panel

def test_add_and_remove_items(tree_panel, qtbot):
    """Test adding top-level and nested items, then removing them."""
    root_path = '/user/project'
    file_paths = [
        f'{root_path}/file1.py',
        f'{root_path}/subdir/file2.js',
        f'{root_path}/file3.py'
    ]

    with qtbot.waitSignal(tree_panel.scan_completed, timeout=1000):
        tree_panel.update_tree(file_paths, root_path)

    assert tree_panel.tree.topLevelItemCount() == 1
    root_item = tree_panel.tree.topLevelItem(0)
    assert root_item.text(0) == 'project'
    assert root_item.childCount() == 2 # file1.py, subdir

    # Test removing an item
    tree_panel.remove_item(f'{root_path}/file1.py')
    assert root_item.childCount() == 1
    assert root_item.child(0).text(0) == 'subdir'

def test_selection_preservation(tree_panel, qtbot):
    """Check that checked items remain checked after an update."""
    root_path = '/user/project'
    initial_paths = [f'{root_path}/file1.py', f'{root_path}/file2.py']
    tree_panel.update_tree(initial_paths, root_path)

    # Check file1.py
    item_to_check = tree_panel.path_to_item_map[f'{root_path}/file1.py']
    item_to_check.setCheckState(0, Qt.CheckState.Checked)

    # Update tree with a new file
    updated_paths = initial_paths + [f'{root_path}/file3.py']
    tree_panel.update_tree(updated_paths, root_path)

    # Assert that file1.py is still checked
    item_after_update = tree_panel.path_to_item_map[f'{root_path}/file1.py']
    assert item_after_update.checkState(0) == Qt.CheckState.Checked

@patch('core.token_estimator.estimate_tokens')
def test_token_label_update(mock_estimate_tokens, tree_panel, qtbot):
    """Verify the total token count label updates when items are checked/unchecked."""
    mock_estimate_tokens.return_value = 100
    root_path = '/user/project'
    file_paths = [f'{root_path}/file1.py', f'{root_path}/file2.py']
    
    # Mock file contents for token estimation
    with patch('builtins.open', mock_open(read_data='print("hello")')):
        tree_panel.update_tree(file_paths, root_path)

    item1 = tree_panel.path_to_item_map[f'{root_path}/file1.py']
    item2 = tree_panel.path_to_item_map[f'{root_path}/file2.py']

    # Check one item
    item1.setCheckState(0, Qt.CheckState.Checked)
    qtbot.wait(50) # Allow signals to process
    assert '100' in tree_panel.token_count_label.text()

    # Check another item
    item2.setCheckState(0, Qt.CheckState.Checked)
    qtbot.wait(50)
    assert '200' in tree_panel.token_count_label.text()

    # Uncheck the first item
    item1.setCheckState(0, Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert '100' in tree_panel.token_count_label.text()
