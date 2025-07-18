# tests/test_selection_manager.py

"""Unit tests for the selection_manager core logic."""

import unittest
from core import selection_manager

class TestSelectionManager(unittest.TestCase):

    def test_load_groups_empty_workspace(self):
        """Test that load_groups returns a default group for an empty workspace dict."""
        workspace = {}
        groups = selection_manager.load_groups(workspace)
        self.assertIn("Default", groups)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups["Default"]["checked_paths"], [])

    def test_load_groups_existing(self):
        """Test loading existing groups."""
        workspace = {
            "selection_groups": {
                "My Group": {"description": "", "checked_paths": ["a.py"]}
            }
        }
        groups = selection_manager.load_groups(workspace)
        self.assertIn("My Group", groups)
        self.assertEqual(groups["My Group"]["checked_paths"], ["a.py"])

    def test_save_new_group(self):
        """Test saving a new group to an empty workspace."""
        workspace = {}
        paths = {"b.txt", "a.py"}
        selection_manager.save_group(workspace, "New Group", "A description", paths)
        
        self.assertIn("selection_groups", workspace)
        self.assertIn("New Group", workspace["selection_groups"])
        saved_group = workspace["selection_groups"]["New Group"]
        self.assertEqual(saved_group["description"], "A description")
        # Paths should be saved as a sorted list
        self.assertEqual(saved_group["checked_paths"], ["a.py", "b.txt"])

    def test_save_update_group(self):
        """Test updating an existing group."""
        workspace = {
            "selection_groups": {
                "My Group": {"description": "Old", "checked_paths": ["a.py"]}
            }
        }
        selection_manager.save_group(workspace, "My Group", "New", {"c.md"})
        saved_group = workspace["selection_groups"]["My Group"]
        self.assertEqual(saved_group["description"], "New")
        self.assertEqual(saved_group["checked_paths"], ["c.md"])

    def test_delete_group(self):
        """Test deleting an existing group."""
        workspace = {
            "selection_groups": {
                "Group A": {},
                "Group B": {}
            }
        }
        selection_manager.delete_group(workspace, "Group A")
        self.assertNotIn("Group A", workspace["selection_groups"])
        self.assertIn("Group B", workspace["selection_groups"])

    def test_delete_non_existent_group(self):
        """Test that deleting a non-existent group does not raise an error."""
        workspace = {"selection_groups": {}}
        try:
            selection_manager.delete_group(workspace, "Ghost Group")
        except KeyError:
            self.fail("delete_group() raised KeyError unexpectedly!")

    def test_cannot_delete_default_group(self):
        """Test that the 'Default' group cannot be deleted."""
        workspace = {
            "selection_groups": {
                "Default": {},
            }
        }
        selection_manager.delete_group(workspace, "Default")
        self.assertIn("Default", workspace["selection_groups"])

if __name__ == '__main__':
    unittest.main()
