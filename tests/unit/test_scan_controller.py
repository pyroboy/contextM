import pytest
from unittest.mock import MagicMock, patch
import os
import sys

from PySide6.QtWidgets import QFileDialog

# Adjust path to import from 'ui' and 'core'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ui.controllers.scan_controller import ScanController

def test_select_folder_emits_signal(qtbot):
    """U-01: Test that select_folder emits the folder_selected signal with the correct path."""
    parent = MagicMock()
    controller = ScanController(parent)

    test_path = '/fake/path/to/folder'

    with patch.object(QFileDialog, 'getExistingDirectory', return_value=test_path) as mock_dialog:
        with qtbot.waitSignal(controller.folder_selected, raising=True) as blocker:
            controller.select_folder()

        assert blocker.args == [test_path]
        mock_dialog.assert_called_once()
