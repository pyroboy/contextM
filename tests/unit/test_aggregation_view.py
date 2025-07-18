import pytest
from unittest.mock import MagicMock, patch
import os

# Adjust path to import from 'ui'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from PySide6.QtWidgets import QApplication
from ui.widgets.aggregation_view import AggregationView

@pytest.fixture
def app(qapp):
    return qapp

@pytest.fixture
def aggregation_view(qtbot):
    view = AggregationView()
    qtbot.addWidget(view)
    return view

@patch('core.token_estimator.estimate_tokens')
def test_set_content_updates_token_label(mock_estimate_tokens, aggregation_view):
    """Verify that updating content recalculates and displays the token count."""
    mock_estimate_tokens.return_value = 42
    test_content = "This is some content."
    
    aggregation_view.set_content(test_content)
    
    assert "42" in aggregation_view.token_count_label.text()
    assert test_content in aggregation_view.text_edit.toPlainText()
    mock_estimate_tokens.assert_called_once_with(test_content)

@patch('pyperclip.copy')
def test_copy_button_calls_pyperclip(mock_copy, aggregation_view, qtbot):
    """Ensure the copy button puts the content of the text edit onto the clipboard."""
    test_content = "Content to be copied."
    aggregation_view.set_content(test_content)
    
    qtbot.mouseClick(aggregation_view.copy_button, Qt.MouseButton.LeftButton)
    
    mock_copy.assert_called_once_with(test_content)

def test_clear_content(aggregation_view):
    """Test that clear_content resets the view."""
    aggregation_view.set_content("Some initial text")
    
    aggregation_view.clear_content()
    
    assert aggregation_view.text_edit.toPlainText() == ""
    assert "0" in aggregation_view.token_count_label.text()
