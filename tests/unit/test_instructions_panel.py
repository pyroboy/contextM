import pytest
from unittest.mock import MagicMock, patch
import os

# Adjust path to import from 'ui'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from PySide6.QtWidgets import QApplication
from ui.widgets.instructions_panel import InstructionsPanel

@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def instructions_panel(qtbot):
    mock_main_window = MagicMock()
    panel = InstructionsPanel(mock_main_window)
    qtbot.addWidget(panel)
    return panel

def test_template_dropdown_emits_signal(instructions_panel, qtbot):
    """Verify selecting a template from the dropdown emits the 'template_selected' signal."""
    templates = {"MyTemplate": "Instructions here", "Another": "More text"}
    instructions_panel.update_templates(templates)

    with qtbot.waitSignal(instructions_panel.template_selected, timeout=1000) as blocker:
        instructions_panel.template_dropdown.setCurrentIndex(1) # Select 'MyTemplate'
    
    assert blocker.args == ["MyTemplate"]

def test_text_edit_propagates_changes(instructions_panel, qtbot):
    """Ensure that typing in the text edit emits the 'instructions_changed' signal."""
    initial_text = "Initial instructions."
    instructions_panel.set_instructions(initial_text)
    
    with qtbot.waitSignal(instructions_panel.instructions_changed, timeout=1000) as blocker:
        qtbot.keyClicks(instructions_panel.text_edit, " And some new text.")

    expected_text = initial_text + " And some new text."
    assert blocker.args == [expected_text]
    assert instructions_panel.get_instructions() == expected_text

def test_set_instructions_updates_text_edit(instructions_panel):
    """Test that calling set_instructions correctly updates the text area."""
    new_text = "This is a test."
    instructions_panel.set_instructions(new_text)
    assert instructions_panel.text_edit.toPlainText() == new_text
