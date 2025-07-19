import pytest
from unittest.mock import MagicMock, patch
import os

# Adjust path to import from 'ui' and 'core'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from PySide6.QtWidgets import QApplication, QTreeWidgetItem
from PySide6.QtCore import Qt
from unittest.mock import mock_open

from ui.widgets.tree_panel import TreePanel

# Required for any Qt-based tests
@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def tree_panel(qtbot):
    panel = TreePanel()
    qtbot.addWidget(panel)
    return panel

def test_add_and_remove_items(tree_panel, qtbot, tmp_path):
    """U-03: Test adding deeply nested items and removing them."""
    root_path = tmp_path
    # Create a nested structure
    (root_path / "src" / "app" / "components").mkdir(parents=True)
    (root_path / "src" / "app" / "utils").mkdir(parents=True)
    (root_path / "src" / "assets" / "deep" / "nested").mkdir(parents=True)
    (root_path / "file1.py").touch()
    (root_path / "src" / "app" / "components" / "button.js").touch()
    (root_path / "src" / "app" / "utils" / "helpers.py").touch()
    (root_path / "src" / "assets" / "logo.svg").touch()
    (root_path / "src" / "assets" / "deep" / "nested" / "icon.png").touch()

    items = [
        (str(root_path / "file1.py"), False, True, '', 50),
        (str(root_path / "src" / "app" / "components" / "button.js"), False, True, '', 120),
        (str(root_path / "src" / "app" / "utils" / "helpers.py"), False, True, '', 80),
        (str(root_path / "src" / "assets" / "logo.svg"), False, True, '', 10),
        (str(root_path / "src" / "assets" / "deep" / "nested" / "icon.png"), False, True, '', 5)
    ]

    tree_panel.populate_tree(items, str(root_path))

    # Assert root item is correct
    # Assert root item is correct
    root_item = tree_panel.tree_items[str(root_path).replace('\\', '/')]
    assert root_item.text(0) == os.path.basename(str(root_path))
    assert root_item.childCount() > 0

    # Assert deep structure
    src_item = tree_panel.tree_items[str(root_path / "src").replace('\\', '/')]
    app_item = tree_panel.tree_items[str(root_path / "src" / "app").replace('\\', '/')]
    assets_item = tree_panel.tree_items[str(root_path / "src" / "assets").replace('\\', '/')]
    deep_item = tree_panel.tree_items[str(root_path / "src" / "assets" / "deep").replace('\\', '/')]
    nested_item = tree_panel.tree_items[str(root_path / "src" / "assets" / "deep" / "nested").replace('\\', '/')]
    assert nested_item.childCount() == 1  # icon.png

    # Test removing a nested item
    path_to_remove = str(root_path / "src" / "app" / "utils" / "helpers.py")
    tree_panel.handle_fs_events([{'action': 'deleted', 'src_path': path_to_remove}])
    
    # Assert item is gone from map and tree
    assert str(path_to_remove).replace('\\', '/') not in tree_panel.tree_items
    assert app_item.childCount() == 1  # only components left
    assert app_item.child(0).text(0) == 'components'

def test_selection_preservation(tree_panel, qtbot, tmp_path):
    """Check that checked items remain checked after an update."""
    root_path = tmp_path
    (root_path / "file1.py").touch()
    (root_path / "file2.py").touch()

    initial_items = [
        (str(root_path / "file1.py"), False, True, '', 10),
        (str(root_path / "file2.py"), False, True, '', 10),
    ]
    tree_panel.populate_tree(initial_items, str(root_path))

    # Check file1.py
    item_to_check = tree_panel.tree_items[str(root_path / "file1.py").replace('\\', '/')]
    item_to_check.setCheckState(0, Qt.CheckState.Checked)

    # Simulate adding a new file
    new_file_path = root_path / "file3.py"
    new_file_path.touch()
    add_event = [{'action': 'created', 'src_path': str(new_file_path)}]
    
    with patch.object(tree_panel.tokenizer, 'encode', return_value=[0]*10):
        tree_panel.handle_fs_events(add_event)

    qtbot.wait(50) # allow signals to process

    # Assert that file1.py is still checked
    item_after_update = tree_panel.tree_items[str(root_path / "file1.py").replace('\\', '/')]
    assert item_after_update.checkState(0) == Qt.CheckState.Checked
    # Assert that the new file is in the tree
    assert str(new_file_path).replace('\\', '/') in tree_panel.tree_items

def test_checkbox_propagation(tree_panel, tmp_path, qtbot):
    """U-04, U-05: Test checkbox propagation up and down the tree including subfolders."""
    root_path = tmp_path
    # Create a nested structure
    (root_path / "src" / "utils").mkdir(parents=True)
    (root_path / "src" / "api").mkdir(parents=True)
    (root_path / "docs").mkdir()
    (root_path / "src" / "utils" / "helpers.py").touch()
    (root_path / "src" / "api" / "client.py").touch()
    (root_path / "docs" / "guide.md").touch()

    items = [
        (str(root_path / "src" / "utils" / "helpers.py"), False, True, '', 100),
        (str(root_path / "src" / "api" / "client.py"), False, True, '', 200),
        (str(root_path / "docs" / "guide.md"), False, True, '', 300),
    ]
    tree_panel.populate_tree(items, str(root_path))

    # --- Grab item references ---
    helpers_item = tree_panel.tree_items[str(root_path / "src" / "utils" / "helpers.py").replace('\\', '/')]
    client_item = tree_panel.tree_items[str(root_path / "src" / "api" / "client.py").replace('\\', '/')]
    guide_item = tree_panel.tree_items[str(root_path / "docs" / "guide.md").replace('\\', '/')]

    utils_item = helpers_item.parent()
    api_item = client_item.parent()
    src_item = utils_item.parent()
    docs_item = guide_item.parent()

    # --- 1. Check one file (helpers.py), expect parent folders to become checked ---
    with qtbot.waitSignal(tree_panel.item_checked_changed, timeout=1000):
        helpers_item.setCheckState(0, Qt.CheckState.Checked)

    assert helpers_item.checkState(0) == Qt.CheckState.Checked
    assert utils_item.checkState(0) == Qt.CheckState.Checked
    assert src_item.checkState(0) == Qt.CheckState.Checked

    # --- 2. Check another file (client.py), expect 'api' folder to be checked ---
    with qtbot.waitSignal(tree_panel.item_checked_changed, timeout=1000):
        client_item.setCheckState(0, Qt.CheckState.Checked)

    assert client_item.checkState(0) == Qt.CheckState.Checked
    assert api_item.checkState(0) == Qt.CheckState.Checked
    assert src_item.checkState(0) == Qt.CheckState.Checked

    # --- 3. Uncheck 'utils', expect helpers to be unchecked, and src remains checked ---
    with qtbot.waitSignal(tree_panel.item_checked_changed, timeout=1000):
        utils_item.setCheckState(0, Qt.CheckState.Unchecked)

    assert helpers_item.checkState(0) == Qt.CheckState.Unchecked
    assert utils_item.checkState(0) == Qt.CheckState.Unchecked
    assert src_item.checkState(0) == Qt.CheckState.Checked # Because client.py is still checked

    # --- 4. Check docs folder, its child (guide.md) should be checked ---
    with qtbot.waitSignal(tree_panel.item_checked_changed, timeout=1000):
        docs_item.setCheckState(0, Qt.CheckState.Checked)

    assert guide_item.checkState(0) == Qt.CheckState.Checked
    assert docs_item.checkState(0) == Qt.CheckState.Checked

    # --- 5. Uncheck src (top folder), expect all nested children to be unchecked ---
    with qtbot.waitSignal(tree_panel.item_checked_changed, timeout=1000):
        src_item.setCheckState(0, Qt.CheckState.Unchecked)

    assert src_item.checkState(0) == Qt.CheckState.Unchecked
    assert api_item.checkState(0) == Qt.CheckState.Unchecked
    assert client_item.checkState(0) == Qt.CheckState.Unchecked
    assert utils_item.checkState(0) == Qt.CheckState.Unchecked
    assert helpers_item.checkState(0) == Qt.CheckState.Unchecked

    # --- 6. Check src (top folder), expect all nested children to be checked ---
    with qtbot.waitSignal(tree_panel.item_checked_changed, timeout=1000):
        src_item.setCheckState(0, Qt.CheckState.Checked)

    assert src_item.checkState(0) == Qt.CheckState.Checked
    assert api_item.checkState(0) == Qt.CheckState.Checked
    assert client_item.checkState(0) == Qt.CheckState.Checked
    assert utils_item.checkState(0) == Qt.CheckState.Checked
    assert helpers_item.checkState(0) == Qt.CheckState.Checked

def test_checkbox_propagation_simple(tree_panel, tmp_path, qtbot):
    """U-04, U-05: Test checkbox propagation up and down the tree including subfolders."""
    root_path = tmp_path
    (root_path / "src" / "app").mkdir(parents=True)
    (root_path / "src" / "app" / "main.py").touch()
    (root_path / "README.md").touch()

    items = [
        (str(root_path / "src" / "app" / "main.py"), False, True, '', 10),
        (str(root_path / "README.md"), False, True, '', 10),
    ]
    tree_panel.populate_tree(items, str(root_path))

    # Get items for easy access
    src_item = tree_panel.tree_items[str(root_path / "src").replace('\\', '/')]
    app_item = tree_panel.tree_items[str(root_path / "src" / "app").replace('\\', '/')]
    main_py_item = tree_panel.tree_items[str(root_path / "src" / "app" / "main.py").replace('\\', '/')]

    # 1. Check a file, ensure parent folders are checked
    main_py_item.setCheckState(0, Qt.CheckState.Checked)
    qtbot.wait(50)
    assert app_item.checkState(0) == Qt.CheckState.Checked
    assert src_item.checkState(0) == Qt.CheckState.Checked

    # 2. Uncheck the file, ensure parent folders are unchecked
    main_py_item.setCheckState(0, Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert app_item.checkState(0) == Qt.CheckState.Unchecked
    assert src_item.checkState(0) == Qt.CheckState.Unchecked

    # 3. Check a folder, all children should be checked
    src_item.setCheckState(0, Qt.CheckState.Checked)
    qtbot.wait(50)
    assert app_item.checkState(0) == Qt.CheckState.Checked
    assert main_py_item.checkState(0) == Qt.CheckState.Checked

    # 4. Uncheck a folder, all children should be unchecked
    src_item.setCheckState(0, Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert app_item.checkState(0) == Qt.CheckState.Unchecked
    assert main_py_item.checkState(0) == Qt.CheckState.Unchecked

def test_token_label_update(tree_panel, qtbot, tmp_path):
    """Verify the total token count label updates when items are checked/unchecked."""
    root_path = tmp_path
    (root_path / "file1.py").touch()
    (root_path / "file2.py").touch()
    file_paths = [str(root_path / "file1.py"), str(root_path / "file2.py")]
    tree_panel.populate_tree([(p, False, True, '', 100) for p in file_paths], str(root_path))

    item1 = tree_panel.tree_items[str(root_path / "file1.py").replace('\\', '/')]
    item2 = tree_panel.tree_items[str(root_path / "file2.py").replace('\\', '/')]

    # Check one item
    item1.setCheckState(0, Qt.CheckState.Checked)
    qtbot.wait(50)  # Allow signals to process
    assert '100' in tree_panel.token_count_label.text()

    # Check another item
    item2.setCheckState(0, Qt.CheckState.Checked)
    qtbot.wait(50)
    assert '200' in tree_panel.token_count_label.text()

    # Uncheck the first item
    item1.setCheckState(0, Qt.CheckState.Unchecked)
    qtbot.wait(50)
    assert '100' in tree_panel.token_count_label.text()




