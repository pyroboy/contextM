import sys
import os
import unittest
from unittest.mock import Mock

from PySide6.QtWidgets import QApplication

# Add project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ui.main_window import MainWindow
from ui.widgets.instructions_panel import InstructionsPanel

class TestInstructionsPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure a QApplication instance exists.
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        """Set up a new MainWindow for each test to ensure isolation."""
        # We test through MainWindow because the critical signal connections are there.
        self.main_window = MainWindow()
        self.instructions_panel = self.main_window.instructions_panel
        self.aggregation_view = self.main_window.aggregation_view

    def test_instructions_text_updates_aggregation_view(self):
        """Test that text in the instructions panel is sent to the aggregation view."""
        # 1. Set some initial file content in the aggregation view
        self.aggregation_view.set_content("some file content", 20)
        
        # 2. Set instructions text
        instructions_text = "This is a system prompt."
        self.instructions_panel.instructions_input.setPlainText(instructions_text)
        self.app.processEvents() # Allow signals to be processed

        # 3. Check if the aggregation view was updated correctly
        aggregated_content = self.aggregation_view.get_content()
        expected_start = f"--- System Prompt ---\n{instructions_text}"
        self.assertTrue(aggregated_content.startswith(expected_start),
                        "Aggregation view should start with the system prompt.")
        self.assertIn("--- File Tree ---\nsome file content", aggregated_content,
                      "Aggregation view should contain the original file content.")

    def test_manage_button_emits_signal(self):
        """Test that the manage templates button emits the correct signal."""
        # Test the panel in isolation to check for signal emission.
        panel = InstructionsPanel()
        mock_slot = Mock()
        panel.manage_templates_requested.connect(mock_slot)
        
        panel.manage_button.click()
        
        mock_slot.assert_called_once()

    def test_template_selection_flow(self):
        """Test that selecting a template updates the instructions text and aggregation view."""
        # 1. Set up a dummy template in the main window's custom instructions
        template_name = "TestTemplate"
        template_content = "This is the content of the test template."
        self.main_window.custom_instructions[template_name] = template_content
        
        # 2. Repopulate the dropdown in the panel with the new template data
        self.instructions_panel.populate_templates(self.main_window.custom_instructions)
        
        # 3. Find the index for our test template
        index = self.instructions_panel.template_dropdown.findData(template_name)
        self.assertGreaterEqual(index, 0, "Test template not found in dropdown.")
        
        # 4. Programmatically select the template, which triggers the signals
        self.instructions_panel.template_dropdown.setCurrentIndex(index)
        self.app.processEvents()
        
        # 5. Check that the instructions panel's text was updated
        self.assertEqual(self.instructions_panel.get_text(), template_content,
                         "Instructions panel text should be updated to template content.")
        
        # 6. Check that this change also propagated to the aggregation view
        expected_start = f"--- System Prompt ---\n{template_content}"
        self.assertTrue(self.aggregation_view.get_content().startswith(expected_start),
                        "Aggregation view should be updated with the template content as a prompt.")

if __name__ == '__main__':
    unittest.main()
