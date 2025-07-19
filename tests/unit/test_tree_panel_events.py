# tests/unit/test_tree_panel_events.py

import pytest
import os
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication, QTreeWidgetItem
from PySide6.QtCore import Qt

# Adjust path to import from root
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ui.widgets.tree_panel import TreePanel

@pytest.fixture
def app(qapp):
    """Fixture for the QApplication instance."""
    return qapp

@pytest.fixture
def tree_panel(qtbot, app):
    """Fixture to create a TreePanel instance."""
    panel = TreePanel()
    qtbot.addWidget(panel)
    return panel

def test_delete_event_removes_item_and_empty_parents(tree_panel, qtbot):
    """
    I-10: Test that a 'deleted' event removes the item and any empty parent directories.
    """
    # 1. Setup initial tree structure: /project/src/core/main.py
    root_path = os.path.normpath('/project')
    file_path = os.path.normpath(f'{root_path}/src/core/main.py')
    items = [(file_path, False, True, '', 100)]
    tree_panel.populate_tree(items, root_path)

    # Verify initial state
    assert file_path in tree_panel.tree_items
    assert os.path.normpath(f'{root_path}/src/core') in tree_panel.tree_items
    assert os.path.normpath(f'{root_path}/src') in tree_panel.tree_items
    assert root_path in tree_panel.tree_items

    # 2. Simulate a file deletion event from the watcher
    delete_event = [{'action': 'deleted', 'src_path': file_path}]
    tree_panel.handle_fs_events(delete_event)

    # 3. Assert that the file and all now-empty parent folders are removed
    assert file_path not in tree_panel.tree_items
    assert os.path.normpath(f'{root_path}/src/core') not in tree_panel.tree_items
    assert os.path.normpath(f'{root_path}/src') not in tree_panel.tree_items
    
    # The root project folder should remain
    assert root_path in tree_panel.tree_items
