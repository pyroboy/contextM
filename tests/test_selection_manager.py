import pytest
from unittest.mock import MagicMock
from core import selection_manager

@pytest.fixture

def workspace_mock():
    return {
        "selection_groups": {
            "Default": {"description": "Default selection", "checked_paths": []},
            "My Group": {"description": "Test group", "checked_paths": ["/path/to/file"]}
        },
        "active_selection_group": "Default"
    }

def test_checking_unchecking_updates_dirty_state(tree_panel, workspace_mock):
    tree_panel.populate_tree([
        ("/path/to/file", False, True, '', 0),
        ("/path/to/another_file", False, True, '', 0)
    ])

    item = tree_panel.tree_items["/path/to/file"]
    item.setCheckState(0, Qt.CheckState.Checked)
    assert tree_panel.tree_widget.item(0).checkState(0) == Qt.CheckState.Checked


def test_group_switch_saves_restores_selection(tree_panel, workspace_mock):
    selection_manager.save_group(workspace_mock, 'Test Group', '', {'/path/to/another_file'})
    
    panel = SelectionManagerPanel(workspace_mock)
    
    panel.update_groups(list(workspace_mock['selection_groups'].keys()), 'Default')
    assert workspace_mock['active_selection_group'] == 'Default'

    panel.group_combo.setCurrentText('Test Group')
    panel.set_dirty(True)
    assert panel.get_current_group_name(with_dirty_marker=True) == 'Test Group*'



def test_selection_persistence_across_restarts(tree_panel, workspace_mock):
    # Simulating a selection before saving
    tree_panel.populate_tree([
        ("/path/to/file", False, True, '', 0),
        ("/path/to/another_file", False, True, '', 0)
    ])

    selected_paths = {"/path/to/file"}
    selection_manager.save_group(workspace_mock, 'Persistent Group', '', selected_paths)

    # Simulate restart
    saved_data = selection_manager.load_groups(workspace_mock)
    assert 'Persistent Group' in saved_data
    assert saved_data['Persistent Group']['checked_paths'] == ["/path/to/file"]
    
def test_cache_synchronization(tree_panel, workspace_mock):
    # Initially populate with some items
    event_batch = [
        {'action': 'created', 'src_path': '/path/to/new_file'}
    ]
    
    tree_panel.populate_tree([
        "/path/to/file", False, True, '', 0
    ])

    with patch('tree_panel.set_checked_paths', return_value=True) as mock_method:
        tree_panel.update_from_fs_events(event_batch)
        mock_method.assert_called_once()

    # Validate cache synchronicity
    assert '/path/to/new_file' in tree_panel.tree_items


def test_checkbox_states_correctly_calculated(tree_panel, workspace_mock):
    tree_panel.populate_tree([
        "/folder", True, True, '', 0
    ])
    file1 = tree_panel.tree_items["/folder/file1.py"]
    file2 = tree_panel.tree_items["/folder/file2.py"]

    file1.setCheckState(0, Qt.CheckState.Checked)
    file2.setCheckState(0, Qt.CheckState.Checked)

    # Validate correct calculation by checking a parent
    folder_item = tree_panel.tree_items["/folder"]
    assert folder_item.checkState(0) == Qt.CheckState.Checked

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
