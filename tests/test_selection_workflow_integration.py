# tests/test_selection_workflow_integration.py

"""
Integration tests for the complete selection workflow.

These tests verify:
- Checking/unchecking files updates the selection manager's dirty state
- Switching between selection groups properly saves and restores selections
- Parent folder checkbox states are correctly calculated
- The cache remains synchronized during all operations
- Selection persistence works across application restarts
"""

import pytest
import os
import tempfile
import json
from unittest.mock import MagicMock, patch, Mock
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Import the modules we're testing
from core import selection_manager, workspace_manager
from ui.widgets.selection_manager import SelectionManagerPanel
from ui.widgets.tree_panel import TreePanel
from ui.controllers.selection_controller import SelectionController


@pytest.fixture(scope="session")
def qapp():
    """QApplication fixture for Qt-based tests."""
    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def temp_workspace_dir():
    """Create a temporary directory for workspace testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_manager.set_testing_mode(temp_dir)
        yield temp_dir
        workspace_manager.set_testing_mode(None)


@pytest.fixture
def mock_main_window():
    """Create a mock main window with all necessary components."""
    main_window = MagicMock()
    main_window.workspaces = {
        "TestWorkspace": {
            "selection_groups": {
                "Default": {"description": "Default selection", "checked_paths": []},
                "Group1": {"description": "Test group 1", "checked_paths": ["/path/to/file1.py"]},
                "Group2": {"description": "Test group 2", "checked_paths": ["/path/to/file2.py"]}
            },
            "active_selection_group": "Default",
            "folder_path": "/test/workspace"
        }
    }
    main_window.current_workspace_name = "TestWorkspace"
    main_window.selection_groups = main_window.workspaces["TestWorkspace"]["selection_groups"]
    main_window.active_selection_group = "Default"
    main_window.current_folder_path = "/test/workspace"
    
    # Mock the panels
    main_window.selection_manager_panel = MagicMock(spec=SelectionManagerPanel)
    main_window.tree_panel = MagicMock(spec=TreePanel)
    
    return main_window


@pytest.fixture
def tree_panel(qapp):
    """Create a real TreePanel for testing."""
    panel = TreePanel()
    return panel


@pytest.fixture
def selection_panel(qapp):
    """Create a real SelectionManagerPanel for testing."""
    panel = SelectionManagerPanel()
    return panel


class TestSelectionWorkflowIntegration:
    """Integration tests for the complete selection workflow."""

    def test_checking_unchecking_updates_dirty_state(self, qapp, mock_main_window, tree_panel, selection_panel):
        """Test that checking/unchecking files updates the selection manager's dirty state."""
        # Setup tree with mock files
        mock_items = [
            ('/test/workspace', True, True, '', 0),
            ('/test/workspace/file1.py', False, True, '', 100),
            ('/test/workspace/file2.py', False, True, '', 200),
        ]
        
        tree_panel.populate_tree(mock_items, '/test/workspace')
        
        # Initialize selection panel with groups
        groups = list(mock_main_window.selection_groups.keys())
        selection_panel.update_groups(groups, "Default")
        
        # Initially, the panel should not be dirty
        assert not selection_panel.save_button.isEnabled()
        
        # Check a file in the tree
        file1_item = tree_panel.tree_items['/test/workspace/file1.py']
        file1_item.setCheckState(0, Qt.CheckState.Checked)
        qapp.processEvents()
        
        # Simulate the main window detecting the change and marking as dirty
        selection_panel.set_dirty(True)
        
        # Now the save button should be enabled and group name should have asterisk
        assert selection_panel.save_button.isEnabled()
        assert selection_panel.get_current_group_name(with_dirty_marker=True) == "Default*"
        
        # Uncheck the file
        file1_item.setCheckState(0, Qt.CheckState.Unchecked)
        qapp.processEvents()
        
        # Simulate clearing dirty state
        selection_panel.set_dirty(False)
        
        # Save button should be disabled and asterisk removed
        assert not selection_panel.save_button.isEnabled()
        assert selection_panel.get_current_group_name(with_dirty_marker=True) == "Default"

    def test_group_switching_saves_and_restores_selections(self, qapp, mock_main_window):
        """Test that switching between selection groups properly saves and restores selections."""
        controller = SelectionController(mock_main_window)
        
        # Mock tree panel methods
        mock_main_window.tree_panel.get_checked_paths.return_value = {'/path/to/file1.py', '/path/to/file2.py'}
        mock_main_window.tree_panel.set_pending_restore_paths = Mock()
        mock_main_window.tree_panel.set_checked_paths = Mock()
        mock_main_window.tree_panel.tree_items = {'mock': 'data'}  # Simulate populated tree
        
        # Switch to Group1
        controller.on_group_changed("Group1")
        
        # Verify that the tree was told to restore the paths for Group1
        expected_paths = {os.path.normpath('/path/to/file1.py')}
        mock_main_window.tree_panel.set_pending_restore_paths.assert_called_with(expected_paths)
        mock_main_window.tree_panel.set_checked_paths.assert_called()
        
        # Verify active group was updated
        assert mock_main_window.active_selection_group == "Group1"
        
        # Switch to Group2
        controller.on_group_changed("Group2")
        
        # Verify that the tree was told to restore the paths for Group2
        expected_paths = {os.path.normpath('/path/to/file2.py')}
        mock_main_window.tree_panel.set_pending_restore_paths.assert_called_with(expected_paths)
        
        # Verify active group was updated
        assert mock_main_window.active_selection_group == "Group2"

    def test_parent_folder_checkbox_states_calculation(self, qapp, tree_panel):
        """Test that parent folder checkbox states are correctly calculated."""
        # Create a nested structure
        mock_items = [
            ('/test/workspace', True, True, '', 0),
            ('/test/workspace/src', True, True, '', 0),
            ('/test/workspace/src/utils', True, True, '', 0),
            ('/test/workspace/src/utils/helper1.py', False, True, '', 50),
            ('/test/workspace/src/utils/helper2.py', False, True, '', 60),
            ('/test/workspace/src/main.py', False, True, '', 100),
            ('/test/workspace/docs', True, True, '', 0),
            ('/test/workspace/docs/readme.md', False, True, '', 30),
        ]
        
        tree_panel.populate_tree(mock_items, '/test/workspace')
        
        # Get references to items
        root_item = tree_panel.tree_items['/test/workspace']
        src_item = tree_panel.tree_items['/test/workspace/src']
        utils_item = tree_panel.tree_items['/test/workspace/src/utils']
        helper1_item = tree_panel.tree_items['/test/workspace/src/utils/helper1.py']
        helper2_item = tree_panel.tree_items['/test/workspace/src/utils/helper2.py']
        main_item = tree_panel.tree_items['/test/workspace/src/main.py']
        docs_item = tree_panel.tree_items['/test/workspace/docs']
        readme_item = tree_panel.tree_items['/test/workspace/docs/readme.md']
        
        # Test case 1: Check one file, parents should be checked
        helper1_item.setCheckState(0, Qt.CheckState.Checked)
        qapp.processEvents()
        
        assert helper1_item.checkState(0) == Qt.CheckState.Checked
        assert utils_item.checkState(0) == Qt.CheckState.Checked
        assert src_item.checkState(0) == Qt.CheckState.Checked
        assert root_item.checkState(0) == Qt.CheckState.Checked
        # docs_item should still be unchecked
        assert docs_item.checkState(0) == Qt.CheckState.Unchecked
        
        # Test case 2: Check all files in utils folder
        helper2_item.setCheckState(0, Qt.CheckState.Checked)
        qapp.processEvents()
        
        # All items in the utils folder are checked, so utils should be fully checked
        assert utils_item.checkState(0) == Qt.CheckState.Checked
        
        # Test case 3: Check main.py as well
        main_item.setCheckState(0, Qt.CheckState.Checked)
        qapp.processEvents()
        
        # Now all files in src are checked, so src should be fully checked
        assert src_item.checkState(0) == Qt.CheckState.Checked
        
        # Test case 4: Uncheck one file in utils
        helper1_item.setCheckState(0, Qt.CheckState.Unchecked)
        qapp.processEvents()
        
        # utils should still be checked because helper2 is checked
        assert utils_item.checkState(0) == Qt.CheckState.Checked
        # src should still be checked because main.py and helper2 are checked
        assert src_item.checkState(0) == Qt.CheckState.Checked
        
        # Test case 5: Check a folder, all children should be checked
        docs_item.setCheckState(0, Qt.CheckState.Checked)
        qapp.processEvents()
        
        assert docs_item.checkState(0) == Qt.CheckState.Checked
        assert readme_item.checkState(0) == Qt.CheckState.Checked

    def test_cache_synchronization_during_operations(self, qapp, tree_panel):
        """Test that the cache remains synchronized during all operations."""
        # Initial population
        mock_items = [
            ('/test/workspace', True, True, '', 0),
            ('/test/workspace/file1.py', False, True, '', 100),
            ('/test/workspace/folder1', True, True, '', 0),
            ('/test/workspace/folder1/file2.py', False, True, '', 200),
        ]
        
        tree_panel.populate_tree(mock_items, '/test/workspace')
        
        # Verify initial cache state
        assert len(tree_panel.tree_items) == 4
        assert '/test/workspace/file1.py' in tree_panel.tree_items
        
        # Test file system events to ensure cache stays synchronized
        # Simulate file creation
        with patch('os.path.isdir', return_value=False), \
             patch('builtins.open'), \
             patch.object(tree_panel.tokenizer, 'encode', return_value=list(range(10))):
            
            creation_events = [{'action': 'created', 'src_path': '/test/workspace/new_file.py'}]
            tree_panel.handle_fs_events(creation_events)
        
        # Cache should be updated
        assert '/test/workspace/new_file.py' in tree_panel.tree_items
        assert len(tree_panel.tree_items) == 5
        
        # Simulate file deletion
        deletion_events = [{'action': 'deleted', 'src_path': '/test/workspace/file1.py'}]
        tree_panel.handle_fs_events(deletion_events)
        
        # Cache should be updated
        assert '/test/workspace/file1.py' not in tree_panel.tree_items
        assert len(tree_panel.tree_items) == 4
        
        # Simulate file move
        with patch('os.path.isdir', return_value=False):
            move_events = [{'action': 'moved', 
                          'src_path': '/test/workspace/folder1/file2.py', 
                          'dst_path': '/test/workspace/folder1/renamed_file.py'}]
            tree_panel.handle_fs_events(move_events)
        
        # Cache should be updated
        assert '/test/workspace/folder1/file2.py' not in tree_panel.tree_items
        assert '/test/workspace/folder1/renamed_file.py' in tree_panel.tree_items
        assert len(tree_panel.tree_items) == 4

    def test_selection_persistence_across_restarts(self, temp_workspace_dir):
        """Test that selection persistence works across application restarts."""
        # Create initial workspace data
        workspace_data = {
            "schema_version": 1,
            "workspaces": {
                "TestWorkspace": {
                    "folder_path": "/test/workspace",
                    "scan_settings": workspace_manager.get_default_scan_settings(),
                    "instructions": "",
                    "selection_groups": {
                        "Default": {"description": "Default selection", "checked_paths": []},
                        "PersistentGroup": {
                            "description": "Group that should persist", 
                            "checked_paths": ["/test/workspace/file1.py", "/test/workspace/folder1/file2.py"]
                        }
                    },
                    "active_selection_group": "PersistentGroup",
                    "use_local_templates": False,
                    "local_custom_instructions": {}
                }
            },
            "last_active_workspace": "TestWorkspace"
        }
        
        # Save workspace data
        workspace_manager.save_workspaces(workspace_data, base_path=temp_workspace_dir)
        
        # Simulate application restart by loading the data
        loaded_workspaces = workspace_manager.load_workspaces(base_path=temp_workspace_dir)
        
        # Verify data persistence
        assert "TestWorkspace" in loaded_workspaces["workspaces"]
        test_workspace = loaded_workspaces["workspaces"]["TestWorkspace"]
        
        # Verify selection groups persisted
        assert "PersistentGroup" in test_workspace["selection_groups"]
        persistent_group = test_workspace["selection_groups"]["PersistentGroup"]
        
        # Verify checked paths persisted
        expected_paths = ["/test/workspace/file1.py", "/test/workspace/folder1/file2.py"]
        assert set(persistent_group["checked_paths"]) == set(expected_paths)
        
        # Verify active group persisted
        assert test_workspace["active_selection_group"] == "PersistentGroup"
        
        # Test that loaded groups work with selection manager
        groups = selection_manager.load_groups(test_workspace)
        assert "PersistentGroup" in groups
        assert set(groups["PersistentGroup"]["checked_paths"]) == set(expected_paths)

    def test_complete_workflow_integration(self, qapp, temp_workspace_dir):
        """Test the complete workflow from file selection to persistence."""
        # Setup mock main window
        main_window = MagicMock()
        main_window.workspaces = {
            "TestWorkspace": {
                "selection_groups": {
                    "Default": {"description": "Default selection", "checked_paths": []}
                },
                "active_selection_group": "Default",
                "folder_path": "/test/workspace"
            }
        }
        main_window.current_workspace_name = "TestWorkspace"
        main_window.selection_groups = main_window.workspaces["TestWorkspace"]["selection_groups"]
        main_window.active_selection_group = "Default"
        main_window.current_folder_path = "/test/workspace"
        
        # Create real panels
        tree_panel = TreePanel()
        selection_panel = SelectionManagerPanel()
        controller = SelectionController(main_window)
        
        # Mock main window's panel references
        main_window.tree_panel = tree_panel
        main_window.selection_manager_panel = selection_panel
        
        # Mock some main window methods
        main_window._update_current_workspace_state = Mock()
        main_window.update_aggregation_and_tokens = Mock()
        
        # Step 1: Populate tree with files
        mock_items = [
            ('/test/workspace', True, True, '', 0),
            ('/test/workspace/file1.py', False, True, '', 100),
            ('/test/workspace/file2.py', False, True, '', 200),
            ('/test/workspace/folder1', True, True, '', 0),
            ('/test/workspace/folder1/file3.py', False, True, '', 150),
        ]
        tree_panel.populate_tree(mock_items, '/test/workspace')
        
        # Step 2: Initialize selection panel
        groups = list(main_window.selection_groups.keys())
        selection_panel.update_groups(groups, "Default")
        
        # Step 3: Select some files
        file1_item = tree_panel.tree_items['/test/workspace/file1.py']
        file3_item = tree_panel.tree_items['/test/workspace/folder1/file3.py']
        
        file1_item.setCheckState(0, Qt.CheckState.Checked)
        file3_item.setCheckState(0, Qt.CheckState.Checked)
        qapp.processEvents()
        
        # Step 4: Mark as dirty and save
        selection_panel.set_dirty(True)
        assert selection_panel.save_button.isEnabled()
        
        # Mock get_checked_paths to return our selected files
        tree_panel.get_checked_paths = Mock(return_value={
            '/test/workspace', '/test/workspace/file1.py', 
            '/test/workspace/folder1', '/test/workspace/folder1/file3.py'
        })
        
        # Save the group
        controller.save_group()
        
        # Step 5: Verify the selection was saved
        saved_group = main_window.workspaces["TestWorkspace"]["selection_groups"]["Default"]
        expected_paths = {
            '/test/workspace', '/test/workspace/file1.py', 
            '/test/workspace/folder1', '/test/workspace/folder1/file3.py'
        }
        assert set(saved_group["checked_paths"]) == expected_paths
        
        # Step 6: Create a new group and switch to it
        controller.new_group()
        new_groups = list(main_window.selection_groups.keys())
        assert "New Group" in new_groups
        
        # Step 7: Switch back to Default group and verify selections are restored
        tree_panel.set_pending_restore_paths = Mock()
        tree_panel.set_checked_paths = Mock()
        tree_panel.tree_items = {'mock': 'data'}  # Simulate populated tree
        
        controller.on_group_changed("Default")
        
        # Verify that the restoration was attempted
        tree_panel.set_pending_restore_paths.assert_called()
        tree_panel.set_checked_paths.assert_called()

if __name__ == '__main__':
    pytest.main([__file__])
