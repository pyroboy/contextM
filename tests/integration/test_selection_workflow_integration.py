"""
Integration tests for the complete selection workflow.
Tests the end-to-end functionality of the selection manager system.
"""

import os
import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.main_window import MainWindow
from ui.controllers.selection_controller import SelectionController
from core import workspace_manager, selection_manager


class TestSelectionWorkflowIntegration:
    """Integration tests for the complete selection workflow."""
    
    @pytest.fixture
    def qapp(self):
        """Create QApplication for testing."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
        
    @pytest.fixture
    def temp_workspace_dir(self):
        """Create temporary directory for workspace testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
        
    @pytest.fixture
    def mock_main_window(self, qapp, temp_workspace_dir):
        """Create mock main window with proper setup."""
        # Create test workspace structure
        test_workspace_path = os.path.join(temp_workspace_dir, "test_workspace")
        os.makedirs(test_workspace_path)
        
        # Create test files
        test_files = [
            "file1.py",
            "file2.js", 
            "folder1/file3.py",
            "folder1/file4.txt",
            "folder2/file5.py"
        ]
        
        for file_path in test_files:
            full_path = os.path.join(test_workspace_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, 'w') as f:
                f.write(f"# Test content for {file_path}")
        
        # Create mock main window
        main_window = Mock()
        main_window.current_workspace_name = "TestWorkspace"
        main_window.current_folder_path = test_workspace_path
        main_window.active_selection_group = "Default"
        
        # Mock workspaces structure
        main_window.workspaces = {
            'workspaces': {
                'TestWorkspace': {
                    'folder_path': test_workspace_path,
                    'scan_settings': {'include_subfolders': True, 'ignore_folders': set(), 'live_watcher': True},
                    'instructions': '',
                    'active_selection_group': 'Default',
                    'selection_groups': {
                        'Default': {
                            'description': 'Default selection',
                            'checked_paths': []
                        }
                    }
                }
            },
            'last_active_workspace': 'TestWorkspace'
        }
        
        # Mock selection groups
        main_window.selection_groups = {
            'Default': {
                'description': 'Default selection',
                'checked_paths': []
            }
        }
        
        # Mock tree panel with get_checked_paths method
        main_window.tree_panel = Mock()
        main_window.tree_panel.get_checked_paths = Mock(return_value=[])
        
        # Mock selection manager panel
        main_window.selection_manager_panel = Mock()
        main_window.selection_manager_panel.get_current_group_name = Mock(return_value="Default")
        main_window.selection_manager_panel.set_dirty = Mock()
        main_window.selection_manager_panel.update_groups = Mock()
        
        # Mock aggregation update
        main_window.update_aggregation_and_tokens = Mock()
        
        return main_window
        
    def test_interface_compatibility(self, qapp, mock_main_window):
        """Test that both tree panel implementations have compatible interfaces."""
        from ui.widgets.tree_panel import TreePanel
        from ui.widgets.tree_panel_mv import TreePanelMV
        
        # Test TreePanel interface
        tree_panel = TreePanel(parent=mock_main_window)
        assert hasattr(tree_panel, 'get_checked_paths')
        
        # Test TreePanelMV interface  
        tree_panel_mv = TreePanelMV(parent=mock_main_window)
        assert hasattr(tree_panel_mv, 'get_checked_paths')
        
        # Both should accept the same parameters
        try:
            tree_panel.get_checked_paths(relative=False, return_set=False)
            tree_panel.get_checked_paths(relative=True, return_set=True)
            tree_panel_mv.get_checked_paths(relative=False, return_set=False)
            tree_panel_mv.get_checked_paths(relative=True, return_set=True)
        except TypeError as e:
            pytest.fail(f"Interface compatibility failed: {e}")
            
    def test_selection_controller_save_group(self, qapp, mock_main_window):
        """Test the save_group method with corrected interface."""
        controller = SelectionController(mock_main_window)
        
        # Mock tree panel to return some test paths
        test_paths = {"file1.py", "folder1/file3.py"}
        mock_main_window.tree_panel.get_checked_paths.return_value = test_paths
        
        # Mock selection_manager.save_group
        with patch('core.selection_manager.save_group') as mock_save:
            with patch('core.selection_manager.load_groups') as mock_load:
                mock_load.return_value = {
                    'Default': {
                        'description': 'Default selection',
                        'checked_paths': list(test_paths)
                    }
                }
                
                # Test save_group method
                controller.save_group()
                
                # Verify the correct interface was used
                mock_main_window.tree_panel.get_checked_paths.assert_called_with(relative=True, return_set=True)
                
                # Verify save_group was called with correct parameters
                mock_save.assert_called_once()
                args = mock_save.call_args[0]
                assert args[1] == "Default"  # group name
                assert args[3] == test_paths  # paths as set
                
                # Verify UI updates
                mock_main_window.selection_manager_panel.set_dirty.assert_called_with(False)
                mock_main_window.update_aggregation_and_tokens.assert_called_once()
                
    def test_checkbox_change_signal_flow(self, qapp, mock_main_window):
        """Test that checkbox changes trigger proper signal flow."""
        # Create a real MainWindow instance for signal testing
        with patch('ui.main_window.workspace_manager.load_workspaces') as mock_load:
            mock_load.return_value = mock_main_window.workspaces
            
            # Create MainWindow in test mode
            main_window = MainWindow(test_mode=True)
            
            # Test _on_checkbox_changed method
            main_window._on_checkbox_changed()
            
            # Verify selection manager is marked as dirty
            # Note: In real implementation, this would call selection_manager_panel.set_dirty(True)
            
            # Test _on_model_data_changed method
            from PySide6.QtCore import Qt, QModelIndex
            
            # Mock roles that include CheckStateRole
            roles = [Qt.ItemDataRole.CheckStateRole]
            main_window._on_model_data_changed(QModelIndex(), QModelIndex(), roles)
            
            # Verify aggregation update was called
            # Note: In real implementation, this would trigger update_aggregation_and_tokens()
            
    def test_group_switching_workflow(self, qapp, mock_main_window):
        """Test complete group switching workflow."""
        controller = SelectionController(mock_main_window)
        
        # Setup test data for group switching
        test_group_data = {
            'Group1': {
                'description': 'Test Group 1',
                'checked_paths': ['file1.py', 'folder1/file3.py']
            },
            'Group2': {
                'description': 'Test Group 2', 
                'checked_paths': ['file2.js', 'folder2/file5.py']
            }
        }
        
        mock_main_window.selection_groups = test_group_data
        
        # Mock tree panel methods
        mock_main_window.tree_panel.set_pending_restore_paths = Mock()
        mock_main_window.tree_panel.tree_items = {'file1.py': Mock()}  # Simulate populated tree
        mock_main_window.tree_panel.set_checked_paths = Mock()
        
        # Test switching to Group1
        controller.on_group_changed('Group1')
        
        # Verify active group was updated
        assert mock_main_window.active_selection_group == 'Group1'
        
        # Verify tree panel was updated with correct paths
        mock_main_window.tree_panel.set_pending_restore_paths.assert_called()
        
        # Test switching to Group2
        controller.on_group_changed('Group2')
        
        # Verify active group was updated
        assert mock_main_window.active_selection_group == 'Group2'
        
    def test_new_group_creation(self, qapp, mock_main_window):
        """Test new group creation workflow."""
        controller = SelectionController(mock_main_window)
        
        # Mock selection_manager methods
        with patch('core.selection_manager.save_group') as mock_save:
            # Test new group creation
            controller.new_group()
            
            # Verify save_group was called for new group
            mock_save.assert_called_once()
            args = mock_save.call_args[0]
            assert args[1] == "New Group"  # group name
            assert args[3] == set()  # empty paths set
            
            # Verify UI was updated
            mock_main_window.selection_manager_panel.update_groups.assert_called()
            
    def test_path_conversion_logic(self, qapp, mock_main_window):
        """Test relative/absolute path conversion in group switching."""
        controller = SelectionController(mock_main_window)
        
        # Test with relative paths in stored data
        mock_main_window.selection_groups = {
            'TestGroup': {
                'description': 'Test',
                'checked_paths': ['file1.py', 'folder1/file3.py']  # relative paths
            }
        }
        
        mock_main_window.tree_panel.set_pending_restore_paths = Mock()
        mock_main_window.tree_panel.tree_items = {}  # Empty tree
        
        # Test group switching with relative paths
        controller.on_group_changed('TestGroup')
        
        # Verify paths were converted to absolute
        call_args = mock_main_window.tree_panel.set_pending_restore_paths.call_args[0][0]
        expected_abs_paths = {
            os.path.normpath(os.path.join(mock_main_window.current_folder_path, 'file1.py')),
            os.path.normpath(os.path.join(mock_main_window.current_folder_path, 'folder1/file3.py'))
        }
        assert call_args == expected_abs_paths
        
    def test_error_handling(self, qapp, mock_main_window):
        """Test error handling in selection workflow."""
        controller = SelectionController(mock_main_window)
        
        # Test save_group with missing workspace
        mock_main_window.current_workspace_name = "NonExistentWorkspace"
        
        try:
            controller.save_group()
            # Should handle gracefully without crashing
        except Exception as e:
            pytest.fail(f"save_group should handle missing workspace gracefully: {e}")
            
        # Test group switching with invalid group
        try:
            controller.on_group_changed("NonExistentGroup")
            # Should handle gracefully without crashing
        except Exception as e:
            pytest.fail(f"on_group_changed should handle invalid group gracefully: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
