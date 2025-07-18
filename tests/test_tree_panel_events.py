import unittest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from ui.widgets.tree_panel import TreePanel

class TestTreePanelEvents(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = TreePanel()
        self.mock_file_tokens_changed = Mock()
        self.panel.file_tokens_changed.connect(self.mock_file_tokens_changed)

        # Create a temporary directory for file system operations
        self.test_dir = tempfile.mkdtemp()
        self.project_dir = os.path.join(self.test_dir, 'project')
        os.makedirs(self.project_dir)

        # Initial file structure
        self.file1_path = os.path.join(self.project_dir, 'file1.py')
        with open(self.file1_path, 'w') as f:
            f.write("import os\nprint('hello')") # 7 tokens with tiktoken

        # Populate the tree to simulate an initial scan
        initial_items = [
            (self.project_dir, True, True, '', 0),
            (self.file1_path, False, True, '', 7),
        ]
        self.panel.populate_tree(initial_items, self.project_dir)
        self.app.processEvents()

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        self.mock_file_tokens_changed.reset_mock()

    def test_file_creation_event(self):
        """Test that a new file is added to the tree and tokens are logged."""
        new_file_path = os.path.join(self.project_dir, 'new_file.txt')
        with open(new_file_path, 'w') as f:
            f.write("A new file with text.") # 6 tokens with tiktoken

        event = {'action': 'created', 'src_path': new_file_path}
        self.panel.handle_fs_events([event])
        self.app.processEvents()

        # Check if item was added to the tree
        self.assertIn(new_file_path, self.panel.tree_items)
        new_item = self.panel.tree_items[new_file_path]
        self.assertEqual(new_item.text(0), 'new_file.txt')
        self.assertEqual(new_item.text(1), '6 tokens')

        # Check if the signal was emitted correctly
        self.mock_file_tokens_changed.assert_called_once_with(new_file_path, 6)

    def test_file_modification_event(self):
        """Test that a modified file's tokens are updated."""
        with open(self.file1_path, 'w') as f:
            f.write("import os\nprint('hello world now with more text')") # 12 tokens with tiktoken

        event = {'action': 'modified', 'src_path': self.file1_path}
        self.panel.handle_fs_events([event])
        self.app.processEvents()

        # Check if the token count in the tree was updated
        item = self.panel.tree_items[self.file1_path]
        self.assertEqual(item.text(1), '12 tokens')

        # Check if the signal was emitted with the correct difference (12 - 7 = 5)
        self.mock_file_tokens_changed.assert_called_once_with(self.file1_path, 5)

    def test_file_deletion_event(self):
        """Test that a deleted file is removed from the tree."""
        os.remove(self.file1_path)

        event = {'action': 'deleted', 'src_path': self.file1_path}
        self.panel.handle_fs_events([event])
        self.app.processEvents()

        # Check if the item was removed from the tree
        self.assertNotIn(self.file1_path, self.panel.tree_items)

if __name__ == '__main__':
    unittest.main()
