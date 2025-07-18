import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor

# Adjust the import path based on your project structure
from ui.widgets.file_changes_panel import FileChangesPanel

class TestFileChangesPanel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Initialize the QApplication instance for the test suite."""
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        """Set up the FileChangesPanel instance before each test."""
        self.panel = FileChangesPanel()

    def test_add_change_entry(self):
        """Test adding entries with positive, negative, and zero token differences."""
        # Helper to find an item by file path
        def find_item_by_path(path_str):
            for i in range(self.panel.changes_list.count()):
                item = self.panel.changes_list.item(i)
                if path_str in item.text():
                    return item
            return None

        # 1. Test adding a positive change
        self.panel.add_change_entry("/path/to/file1.py", 150)
        self.assertEqual(self.panel.changes_list.count(), 1)
        item1 = find_item_by_path("/path/to/file1.py")
        self.assertIsNotNone(item1)
        self.assertEqual(item1.text(), "/path/to/file1.py  (+150 tokens)")
        self.assertEqual(item1.foreground().color(), QColor("green"))

        # 2. Test adding a negative change
        self.panel.add_change_entry("/path/to/file2.py", -75)
        self.assertEqual(self.panel.changes_list.count(), 2)
        item2 = find_item_by_path("/path/to/file2.py")
        self.assertIsNotNone(item2)
        self.assertEqual(item2.text(), "/path/to/file2.py  (-75 tokens)")
        self.assertEqual(item2.foreground().color(), QColor("red"))

        # 3. Test adding a zero change (should be ignored)
        self.panel.add_change_entry("/path/to/file3.py", 0)
        self.assertEqual(self.panel.changes_list.count(), 2)

if __name__ == '__main__':
    unittest.main()
