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
        """U-06: Test saving a new group and ensure groups are sorted alphabetically."""
        workspace = {}
        
        # Save groups in a non-alphabetical order
        selection_manager.save_group(workspace, "Zephyr", "", {"z.py"})
        selection_manager.save_group(workspace, "Alpha", "", {"a.py"})
        selection_manager.save_group(workspace, "Beta", "", {"b.py"})

        self.assertIn("selection_groups", workspace)
        groups = workspace["selection_groups"]
        
        # Assert that the keys (group names) are in alphabetical order
        self.assertEqual(list(groups.keys()), ["Alpha", "Beta", "Zephyr"])
        
        # Assert that the paths within a group are also sorted
        self.assertEqual(groups["Alpha"]["checked_paths"], ["a.py"])

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

    def test_delete_group_switches_to_default(self):
        """U-07: Test that deleting the active group switches the UI to Default."""
        # Setup mock main_window and its components
        main_window = MagicMock()
        main_window.workspaces = {
            "MyWorkspace": {
                "selection_groups": {
                    "GroupA": {"checked_paths": []},
                    "GroupB": {"checked_paths": []}
                }
            }
        }
        main_window.current_workspace_name = "MyWorkspace"
        main_window.selection_groups = main_window.workspaces["MyWorkspace"]["selection_groups"]
        main_window.active_selection_group = "GroupA"
        main_window.selection_manager_panel = MagicMock()

        # Initialize the controller with the mock window
        from ui.controllers.selection_controller import SelectionController
        controller = SelectionController(main_window)

        # Delete the active group
        controller.delete_group("GroupA")

        # Assert that the panel was updated to switch to the 'Default' group
        main_window.selection_manager_panel.update_groups.assert_called_once()
        call_args = main_window.selection_manager_panel.update_groups.call_args[0]
        self.assertIn("Default", call_args[0])
        self.assertNotIn("GroupA", call_args[0])
        self.assertEqual(call_args[1], "Default") # Assert new active group is 'Default'
        workspace = {
            "selection_groups": {
                "Default": {},
            }
        }
        selection_manager.delete_group(workspace, "Default")
        self.assertIn("Default", workspace["selection_groups"])

if __name__ == '__main__':
    unittest.main()
