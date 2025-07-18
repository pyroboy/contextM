# tests/test_edit_selection_group_dialog.py

"""Widget tests for the EditSelectionGroupDialog."""

import pytest
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from ui.dialogs.edit_selection_group_dialog import EditSelectionGroupDialog

# Fixture to create a QApplication instance
@pytest.fixture(scope="session")
def qapp():
    """Creates a QApplication instance for the test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def dialog(qapp):
    """Creates a dialog instance for testing."""
    group_name = "My Group"
    group_data = {"description": "A test group", "checked_paths": ["file1.py"]}
    all_groups = {"My Group": group_data, "Another Group": {}}
    d = EditSelectionGroupDialog(group_name, group_data, all_groups)
    yield d
    d.close()

def test_dialog_initial_state(dialog):
    """Test the initial state of the dialog and its widgets."""
    assert dialog.name_edit.text() == "My Group"
    assert dialog.description_edit.toPlainText() == "A test group"
    assert dialog.path_list.count() == 1
    assert dialog.path_list.item(0).text() == "file1.py"
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    assert ok_button.isEnabled() is True

def test_name_validation_empty(dialog):
    """Test that an empty name disables the OK button."""
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    dialog.name_edit.setText("   ")  # Whitespace only
    assert ok_button.isEnabled() is False
    dialog.name_edit.setText("") # Empty
    assert ok_button.isEnabled() is False

def test_name_validation_duplicate(dialog):
    """Test that a duplicate name disables the OK button."""
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    dialog.name_edit.setText("Another Group")
    assert ok_button.isEnabled() is False
    # Case-insensitive check
    dialog.name_edit.setText("another group")
    assert ok_button.isEnabled() is False

def test_name_validation_valid_change(dialog):
    """Test that a valid new name keeps the OK button enabled."""
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    dialog.name_edit.setText("A New Valid Name")
    assert ok_button.isEnabled() is True

def test_default_group_rename_is_invalid(qapp):
    """Test that renaming the 'Default' group is not allowed."""
    dialog = EditSelectionGroupDialog("Default", {}, {"Default": {}, "Group B": {}})
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    
    # Trying to rename 'Default' to something else
    dialog.name_edit.setText("Not Default")
    assert ok_button.isEnabled() is False

    # Keeping the name as 'Default' should be valid
    dialog.name_edit.setText("Default")
    assert ok_button.isEnabled() is True

def test_get_result(dialog):
    """Test that get_result returns the correct, updated data."""
    dialog.name_edit.setText("Updated Name")
    dialog.description_edit.setPlainText("Updated description.")
    dialog.path_list.addItem("file2.txt")

    result = dialog.get_result()
    assert result["name"] == "Updated Name"
    assert result["description"] == "Updated description."
    assert set(result["checked_paths"]) == {"file1.py", "file2.txt"}
