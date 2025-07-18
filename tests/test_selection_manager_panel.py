# tests/test_selection_manager_panel.py

"""Widget tests for the SelectionManagerPanel."""

import pytest
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication
from ui.widgets.selection_manager import SelectionManagerPanel

# Fixture for QApplication
@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app

# Fixture for the panel
@pytest.fixture
def panel(qapp):
    p = SelectionManagerPanel()
    yield p
    p.close()

@pytest.fixture
def populated_panel(panel):
    groups = {
        "Default": {"description": "", "checked_paths": []},
        "My Group": {"description": "Test", "checked_paths": ["a.py"]}
    }
    panel.update_groups(groups, "Default")
    return panel

def test_initial_state(panel):
    """Test the panel's initial state upon creation."""
    assert panel.group_combo.count() == 0
    assert panel.save_button.isEnabled() is False
    assert panel.edit_button.isEnabled() is False
    assert panel.delete_button.isEnabled() is False

def test_update_groups(populated_panel):
    """Test that the panel correctly populates with a group list."""
    panel = populated_panel
    assert panel.group_combo.count() == 2
    assert panel.group_combo.currentText() == "Default"
    assert panel.group_combo.itemText(1) == "My Group"

def test_button_state_for_default_group(populated_panel):
    """Test button states when the 'Default' group is selected."""
    panel = populated_panel
    panel.group_combo.setCurrentText("Default")
    assert panel.save_button.isEnabled() is False  # Not dirty
    assert panel.edit_button.isEnabled() is True   # Default is editable
    assert panel.delete_button.isEnabled() is False # Default cannot be deleted

def test_button_state_for_custom_group(populated_panel):
    """Test button states when a custom group is selected."""
    panel = populated_panel
    panel.group_combo.setCurrentText("My Group")
    assert panel.save_button.isEnabled() is False # Not dirty
    assert panel.edit_button.isEnabled() is True
    assert panel.delete_button.isEnabled() is True

def test_dirty_state(populated_panel):
    """Test the dirty state indicator and save button enablement."""
    panel = populated_panel
    panel.group_combo.setCurrentText("My Group")
    panel.set_dirty(True)
    assert panel.group_combo.currentText() == "My Group*"
    assert panel.save_button.isEnabled() is True
    panel.set_dirty(False)
    assert panel.group_combo.currentText() == "My Group"
    assert panel.save_button.isEnabled() is False

def test_signal_emissions(qtbot, populated_panel):
    """Test that UI interactions emit the correct signals."""
    panel = populated_panel
    panel.group_combo.setCurrentText("My Group")

    with qtbot.waitSignal(panel.group_changed, timeout=1000) as blocker:
        panel.group_combo.setCurrentText("Default")
    assert blocker.args == ["Default"]

    with qtbot.waitSignal(panel.save_requested, timeout=1000):
        panel.set_dirty(True)
        qtbot.mouseClick(panel.save_button, qtbot.app.mouseButtons().LeftButton)

    with qtbot.waitSignal(panel.new_requested, timeout=1000):
        qtbot.mouseClick(panel.new_button, qtbot.app.mouseButtons().LeftButton)

    with qtbot.waitSignal(panel.edit_requested, timeout=1000) as blocker:
        qtbot.mouseClick(panel.edit_button, qtbot.app.mouseButtons().LeftButton)
    assert blocker.args == ["Default"]

    # Delete is disabled for Default, so switch to My Group
    panel.group_combo.setCurrentText("My Group")
    with qtbot.waitSignal(panel.delete_requested, timeout=1000) as blocker:
        qtbot.mouseClick(panel.delete_button, qtbot.app.mouseButtons().LeftButton)
    assert blocker.args == ["My Group"]
