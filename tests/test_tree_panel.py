import unittest
from unittest.mock import patch, Mock
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Adjust the import path based on your project structure
from ui.widgets.tree_panel import TreePanel

class TestTreePanel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Initialize the QApplication instance for the test suite."""
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        """Set up the TreePanel instance before each test."""
        self.panel = TreePanel()

    def tearDown(self):
        """Clean up resources after each test."""
        self.panel.deleteLater()

    def test_folder_token_calculation_and_display(self):
        """Test that folder token counts are calculated and displayed correctly."""
        # 1. Define a mock file structure and populate the tree
        # (path, is_dir, is_valid, reason, token_count)
        mock_items = [
            ('/project', True, True, '', 0),
            ('/project/file1.py', False, True, '', 100),
            ('/project/subdir', True, True, '', 0),
            ('/project/subdir/file2.py', False, True, '', 250),
            ('/project/subdir/file3.txt', False, True, '', 50),
        ]
        
        self.panel.populate_tree(mock_items, '/project')

        # 2. Get the tree items for verification
        root_item = self.panel.tree_widget.topLevelItem(0)
        self.assertEqual(root_item.text(0), 'project')
        
        subdir_item = root_item.child(1)
        self.assertEqual(subdir_item.text(0), 'subdir')

        file1_item = root_item.child(0)
        file2_item = subdir_item.child(0)
        file3_item = subdir_item.child(1)

        # 3. Verify initial token display (selected / total)
        # Subdir should have 250 + 50 = 300 tokens total
        # Project root should have 100 + 300 = 400 tokens total
        self.assertEqual(subdir_item.text(1), "0 / 300 tokens")
        self.assertEqual(root_item.text(1), "0 / 400 tokens")
        self.assertEqual(file1_item.text(1), "100 tokens") # Files show only their tokens

        # 4. Programmatically check an item and verify the display updates
        file2_item.setCheckState(0, Qt.CheckState.Checked)
        self.app.processEvents() # Allow signals to be processed

        # Subdir should now show 250 selected tokens
        # Project root should also show 250 selected tokens
        self.assertEqual(subdir_item.text(1), "250 / 300 tokens")
        self.assertEqual(root_item.text(1), "250 / 400 tokens")

        # 5. Check another item and verify the display updates again
        file1_item.setCheckState(0, Qt.CheckState.Checked)
        self.app.processEvents()

        # Subdir is unchanged
        # Project root should now show 250 + 100 = 350 selected tokens
        self.assertEqual(subdir_item.text(1), "250 / 300 tokens")
        self.assertEqual(root_item.text(1), "350 / 400 tokens")

    def test_checkbox_propagation(self):
        """Test that checking/unchecking items propagates correctly up and down the tree."""
        # 1. Define a mock file structure and populate the tree
        mock_items = [
            ('/project', True, True, '', 0),
            ('/project/file1.py', False, True, '', 100),
            ('/project/subdir', True, True, '', 0),
            ('/project/subdir/file2.py', False, True, '', 250),
            ('/project/subdir/nested_dir', True, True, '', 0),
            ('/project/subdir/nested_dir/file3.txt', False, True, '', 50),
        ]
        self.panel.populate_tree(mock_items, '/project')

        # 2. Get tree items for testing
        root_item = self.panel.tree_widget.topLevelItem(0)
        subdir_item = root_item.child(1)
        nested_dir_item = subdir_item.child(1)
        file3_item = nested_dir_item.child(0)

        # 3. Test child-to-parent propagation: checking a deep child checks all parents
        file3_item.setCheckState(0, Qt.CheckState.Checked)
        self.app.processEvents()

        self.assertEqual(file3_item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(nested_dir_item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(subdir_item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(root_item.checkState(0), Qt.CheckState.Checked)

        # 4. Test parent-to-child propagation: unchecking a parent unchecks all children
        root_item.setCheckState(0, Qt.CheckState.Unchecked)
        self.app.processEvents()

        self.assertEqual(root_item.checkState(0), Qt.CheckState.Unchecked)
        self.assertEqual(subdir_item.checkState(0), Qt.CheckState.Unchecked)
        self.assertEqual(nested_dir_item.checkState(0), Qt.CheckState.Unchecked)
        self.assertEqual(file3_item.checkState(0), Qt.CheckState.Unchecked)

        # 5. Test parent-to-child propagation: checking a parent checks all children
        subdir_item.setCheckState(0, Qt.CheckState.Checked)
        self.app.processEvents()

        self.assertEqual(subdir_item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(nested_dir_item.checkState(0), Qt.CheckState.Checked)
        self.assertEqual(file3_item.checkState(0), Qt.CheckState.Checked)


    def test_get_checked_paths_relative(self):
        """Test that get_checked_paths returns correct absolute and relative paths."""
        # 1. Define mock items and root path
        # Use a platform-specific path structure
        root_path = os.path.normpath('/tmp/project')
        file1_path = os.path.join(root_path, 'file1.py')
        src_path = os.path.join(root_path, 'src')
        main_py_path = os.path.join(src_path, 'main.py')

        mock_items = [
            (root_path, True, True, '', 0),
            (file1_path, False, True, '', 10),
            (src_path, True, True, '', 0),
            (main_py_path, False, True, '', 20),
        ]
        self.panel.populate_tree(mock_items, root_path)

        # 2. Get items and check them
        file1_item = self.panel.tree_items[file1_path]
        main_py_item = self.panel.tree_items[main_py_path]
        
        file1_item.setCheckState(0, Qt.CheckState.Checked)
        main_py_item.setCheckState(0, Qt.CheckState.Checked)
        self.app.processEvents() # Allow checkbox propagation logic to run

        # 3. Test get_checked_paths with relative=False (default)
        abs_paths = self.panel.get_checked_paths(return_set=True)
        
        # The parent directories of checked items are also checked automatically
        expected_abs_paths = {
            root_path,
            file1_path,
            src_path,
            main_py_path,
        }
        self.assertEqual(abs_paths, expected_abs_paths)

        # 4. Test get_checked_paths with relative=True
        rel_paths = self.panel.get_checked_paths(return_set=True, relative=True)
        
        expected_rel_paths = {
            '.',
            'file1.py',
            'src',
            os.path.join('src', 'main.py')
        }
        # Normalize for comparison across OS
        expected_rel_paths_norm = {os.path.normpath(p) for p in expected_rel_paths}
        
        self.assertEqual(rel_paths, expected_rel_paths_norm)

    def test_handle_fs_events(self):
        """Test that the tree view correctly handles file system events."""
        # 1. Setup initial tree
        root_path = os.path.normpath('/tmp/project')
        file1_path = os.path.join(root_path, 'file1.py')
        dir_path = os.path.join(root_path, 'src')
        file2_path = os.path.join(dir_path, 'main.py')

        mock_items = [
            (root_path, True, True, '', 0),
            (file1_path, False, True, '', 10),
            (dir_path, True, True, '', 0),
            (file2_path, False, True, '', 20),
        ]
        self.panel.populate_tree(mock_items, root_path)
        self.assertEqual(len(self.panel.tree_items), 4)

        # 2. Test file creation
        new_file_path = os.path.join(dir_path, 'utils.py')
        creation_event = [{'action': 'created', 'src_path': new_file_path, 'dst_path': None}]
        
        with patch('os.path.isdir', return_value=False), \
             patch('builtins.open', unittest.mock.mock_open(read_data='import os')), \
             patch.object(self.panel.tokenizer, 'encode', return_value=list(range(5))):
            self.panel.handle_fs_events(creation_event)
        
        self.assertIn(new_file_path, self.panel.tree_items)
        self.assertEqual(self.panel.tree_items[new_file_path].text(0), 'utils.py')
        self.assertEqual(len(self.panel.tree_items), 5)

        # 3. Test file deletion
        deletion_event = [{'action': 'deleted', 'src_path': file1_path, 'dst_path': None}]
        self.panel.handle_fs_events(deletion_event)
        self.assertNotIn(file1_path, self.panel.tree_items)
        self.assertEqual(len(self.panel.tree_items), 4)

        # 4. Test file rename (move)
        renamed_file_path = os.path.join(dir_path, 'app.py')
        move_event = [{'action': 'moved', 'src_path': file2_path, 'dst_path': renamed_file_path}]
        
        with patch('os.path.isdir', return_value=False):
            self.panel.handle_fs_events(move_event)

        self.assertNotIn(file2_path, self.panel.tree_items)
        self.assertIn(renamed_file_path, self.panel.tree_items)
        self.assertEqual(self.panel.tree_items[renamed_file_path].text(0), 'app.py')
        self.assertEqual(len(self.panel.tree_items), 4)


if __name__ == '__main__':
    unittest.main()
