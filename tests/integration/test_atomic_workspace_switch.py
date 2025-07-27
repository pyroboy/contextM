"""
Integration tests for atomic workspace switching with complete data validation.

Tests the comprehensive workspace switch flow according to the cohesive plan:
1. Workspace data integrity and validation
2. Atomic workspace loading with error handling
3. Settings application and UI synchronization
4. Missing folder handling and recovery
5. Data consistency across rapid workspace switching
"""

import pytest
import tempfile
import os
import shutil
from unittest.mock import Mock, patch, MagicMock
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from ui.main_window import MainWindow
from core import workspace_manager
from core.workspace_manager import get_default_scan_settings, ensure_complete_scan_settings


class TestAtomicWorkspaceSwitch:
    """Test atomic workspace switching with complete data validation."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def app(self):
        """Create QApplication for testing."""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app
    
    @pytest.fixture
    def main_window(self, app, temp_dir):
        """Create MainWindow with test mode."""
        workspace_manager.set_testing_mode(temp_dir)
        window = MainWindow(test_mode=True, testing_path=temp_dir)
        yield window
        window.close()
    
    @pytest.fixture
    def sample_workspaces(self, temp_dir):
        """Create sample workspaces with different configurations."""
        # Create test folders
        folder1 = os.path.join(temp_dir, "project1")
        folder2 = os.path.join(temp_dir, "project2")
        os.makedirs(folder1, exist_ok=True)
        os.makedirs(folder2, exist_ok=True)
        
        workspaces = {
            "schema_version": 1,
            "workspaces": {
                "Workspace1": {
                    "folder_path": folder1,
                    "scan_settings": {
                        "include_subfolders": True,
                        "ignore_folders": [".git", "__pycache__", "custom_ignore"],
                        "live_watcher": True
                    },
                    "instructions": "Test instructions for workspace 1",
                    "active_selection_group": "Default",
                    "selection_groups": {
                        "Default": {"description": "Default selection", "checked_paths": ["file1.py", "file2.py"]}
                    }
                },
                "Workspace2": {
                    "folder_path": folder2,
                    "scan_settings": {
                        "include_subfolders": False,
                        "ignore_folders": [".git", "node_modules", "dist"],
                        "live_watcher": False
                    },
                    "instructions": "Test instructions for workspace 2",
                    "active_selection_group": "Custom",
                    "selection_groups": {
                        "Default": {"description": "Default selection", "checked_paths": []},
                        "Custom": {"description": "Custom selection", "checked_paths": ["src/main.js"]}
                    }
                },
                "EmptyWorkspace": {
                    "folder_path": None,
                    "scan_settings": get_default_scan_settings(),
                    "instructions": "",
                    "active_selection_group": "Default",
                    "selection_groups": {
                        "Default": {"description": "Default selection", "checked_paths": []}
                    }
                }
            },
            "last_active_workspace": "Workspace1"
        }
        
        workspace_manager.save_workspaces(workspaces, base_path=temp_dir)
        return workspaces, folder1, folder2
    
    def test_workspace_data_integrity_validation(self, main_window, sample_workspaces):
        """Test that workspace data is always complete and consistent."""
        workspaces, folder1, folder2 = sample_workspaces
        main_window.workspaces = workspaces
        
        # Test loading workspace with complete data
        workspace_data = main_window._load_workspace_data("Workspace1")
        
        assert workspace_data is not None
        assert workspace_data["folder_path"] == folder1
        assert "scan_settings" in workspace_data
        assert "include_subfolders" in workspace_data["scan_settings"]
        assert "ignore_folders" in workspace_data["scan_settings"]
        assert "live_watcher" in workspace_data["scan_settings"]
        assert isinstance(workspace_data["scan_settings"]["ignore_folders"], set)
        assert workspace_data["instructions"] == "Test instructions for workspace 1"
        assert workspace_data["active_selection_group"] == "Default"
        assert "selection_groups" in workspace_data
    
    def test_workspace_data_validation_with_incomplete_settings(self, main_window, temp_dir):
        """Test that incomplete scan_settings are auto-completed with defaults."""
        # Create workspace with incomplete scan_settings
        incomplete_workspaces = {
            "schema_version": 1,
            "workspaces": {
                "IncompleteWorkspace": {
                    "folder_path": temp_dir,
                    "scan_settings": {
                        "include_subfolders": True
                        # Missing ignore_folders and live_watcher
                    },
                    "instructions": "Test",
                    "active_selection_group": "Default",
                    "selection_groups": {"Default": {"description": "Default", "checked_paths": []}}
                }
            },
            "last_active_workspace": "IncompleteWorkspace"
        }
        
        main_window.workspaces = incomplete_workspaces
        workspace_data = main_window._load_workspace_data("IncompleteWorkspace")
        
        assert workspace_data is not None
        assert "ignore_folders" in workspace_data["scan_settings"]
        assert "live_watcher" in workspace_data["scan_settings"]
        assert isinstance(workspace_data["scan_settings"]["ignore_folders"], set)
        assert workspace_data["scan_settings"]["live_watcher"] is True  # Default value
    
    def test_atomic_workspace_switch_success(self, main_window, sample_workspaces):
        """Test successful atomic workspace switch loads all data correctly."""
        workspaces, folder1, folder2 = sample_workspaces
        main_window.workspaces = workspaces
        
        # Mock UI components
        main_window.instructions_panel = Mock()
        main_window.selection_manager_panel = Mock()
        main_window.scan_ctl = Mock()
        main_window._update_path_display = Mock()
        main_window._on_workspace_switched = Mock()
        
        # Perform atomic workspace switch
        success = main_window._switch_workspace("Workspace1", initial_load=True)
        
        assert success is True
        assert main_window.current_workspace_name == "Workspace1"
        assert main_window.current_folder_path == folder1
        assert main_window.current_scan_settings["include_subfolders"] is True
        assert "custom_ignore" in main_window.current_scan_settings["ignore_folders"]
        assert main_window.current_scan_settings["live_watcher"] is True
        
        # Verify UI updates were called
        main_window.instructions_panel.set_text.assert_called_with("Test instructions for workspace 1")
        main_window._update_path_display.assert_called()
        main_window._on_workspace_switched.assert_called_with("Workspace1")
        main_window.scan_ctl.start.assert_called()
    
    def test_workspace_switch_with_different_settings(self, main_window, sample_workspaces):
        """Test switching between workspaces with different scan settings."""
        workspaces, folder1, folder2 = sample_workspaces
        main_window.workspaces = workspaces
        
        # Mock UI components
        main_window.instructions_panel = Mock()
        main_window.selection_manager_panel = Mock()
        main_window.scan_ctl = Mock()
        main_window._update_path_display = Mock()
        main_window._on_workspace_switched = Mock()
        
        # Switch to Workspace1
        success1 = main_window._switch_workspace("Workspace1", initial_load=True)
        assert success1 is True
        assert main_window.current_scan_settings["include_subfolders"] is True
        assert main_window.current_scan_settings["live_watcher"] is True
        assert "custom_ignore" in main_window.current_scan_settings["ignore_folders"]
        
        # Switch to Workspace2 with different settings
        success2 = main_window._switch_workspace("Workspace2")
        assert success2 is True
        assert main_window.current_scan_settings["include_subfolders"] is False
        assert main_window.current_scan_settings["live_watcher"] is False
        assert "node_modules" in main_window.current_scan_settings["ignore_folders"]
        assert "dist" in main_window.current_scan_settings["ignore_folders"]
        assert main_window.active_selection_group == "Custom"
    
    def test_workspace_switch_to_nonexistent_workspace(self, main_window, sample_workspaces):
        """Test switching to non-existent workspace fails gracefully."""
        workspaces, folder1, folder2 = sample_workspaces
        main_window.workspaces = workspaces
        
        # Try to switch to non-existent workspace
        success = main_window._switch_workspace("NonExistentWorkspace")
        
        assert success is False
        # Current workspace should remain unchanged
        assert main_window.current_workspace_name != "NonExistentWorkspace"
    
    def test_default_workspace_creation(self, main_window):
        """Test that Default workspace is created when missing."""
        # Start with empty workspaces
        main_window.workspaces = {"schema_version": 1, "workspaces": {}}
        
        # Mock UI components
        main_window.instructions_panel = Mock()
        main_window.selection_manager_panel = Mock()
        main_window._update_path_display = Mock()
        main_window._on_workspace_switched = Mock()
        
        # Switch to Default workspace (should create it)
        success = main_window._switch_workspace("Default", initial_load=True)
        
        assert success is True
        assert "Default" in main_window.workspaces["workspaces"]
        assert main_window.workspaces["workspaces"]["Default"]["folder_path"] is None
        assert main_window.workspaces["workspaces"]["Default"]["scan_settings"] == get_default_scan_settings()
    
    def test_missing_folder_handling(self, main_window, temp_dir):
        """Test handling of workspace with missing/invalid folder path."""
        # Create workspace with non-existent folder
        missing_folder = os.path.join(temp_dir, "missing_folder")
        workspaces = {
            "schema_version": 1,
            "workspaces": {
                "MissingFolderWorkspace": {
                    "folder_path": missing_folder,
                    "scan_settings": get_default_scan_settings(),
                    "instructions": "Test with missing folder",
                    "active_selection_group": "Default",
                    "selection_groups": {"Default": {"description": "Default", "checked_paths": []}}
                }
            }
        }
        
        main_window.workspaces = workspaces
        
        # Mock UI components and dialog
        main_window.instructions_panel = Mock()
        main_window.selection_manager_panel = Mock()
        main_window.scan_ctl = Mock()
        main_window._update_path_display = Mock()
        main_window._on_workspace_switched = Mock()
        
        with patch('PySide6.QtWidgets.QMessageBox') as mock_msgbox:
            mock_msgbox.return_value.exec.return_value = mock_msgbox.StandardButton.No
            
            # Switch to workspace with missing folder
            success = main_window._switch_workspace("MissingFolderWorkspace", initial_load=True)
            
            assert success is True  # Switch succeeds but folder validation fails
            assert main_window.current_folder_path == missing_folder
            # Scan should not be started due to missing folder
            main_window.scan_ctl.start.assert_not_called()
    
    def test_rapid_workspace_switching_data_consistency(self, main_window, sample_workspaces):
        """Test rapid workspace switching maintains data consistency."""
        workspaces, folder1, folder2 = sample_workspaces
        main_window.workspaces = workspaces
        
        # Mock UI components
        main_window.instructions_panel = Mock()
        main_window.selection_manager_panel = Mock()
        main_window.scan_ctl = Mock()
        main_window._update_path_display = Mock()
        main_window._on_workspace_switched = Mock()
        
        # Rapid switching between workspaces
        workspaces_to_test = ["Workspace1", "Workspace2", "EmptyWorkspace", "Workspace1"]
        
        for i, workspace_name in enumerate(workspaces_to_test):
            initial_load = (i == 0)  # Only first switch is initial load
            success = main_window._switch_workspace(workspace_name, initial_load=initial_load)
            
            assert success is True
            assert main_window.current_workspace_name == workspace_name
            
            # Verify data consistency for each workspace
            if workspace_name == "Workspace1":
                assert main_window.current_folder_path == folder1
                assert main_window.current_scan_settings["include_subfolders"] is True
                assert "custom_ignore" in main_window.current_scan_settings["ignore_folders"]
            elif workspace_name == "Workspace2":
                assert main_window.current_folder_path == folder2
                assert main_window.current_scan_settings["include_subfolders"] is False
                assert "node_modules" in main_window.current_scan_settings["ignore_folders"]
            elif workspace_name == "EmptyWorkspace":
                assert main_window.current_folder_path is None
                assert main_window.current_scan_settings == get_default_scan_settings()
    
    def test_workspace_state_persistence_across_switches(self, main_window, sample_workspaces):
        """Test that workspace state is properly saved and restored across switches."""
        workspaces, folder1, folder2 = sample_workspaces
        main_window.workspaces = workspaces
        
        # Mock UI components
        main_window.instructions_panel = Mock()
        main_window.instructions_panel.get_text.return_value = "Modified instructions"
        main_window.selection_manager_panel = Mock()
        main_window.tree_panel = Mock()
        main_window.tree_panel.get_checked_paths.return_value = ["modified_file.py"]
        main_window.scan_ctl = Mock()
        main_window._update_path_display = Mock()
        main_window._on_workspace_switched = Mock()
        
        # Switch to Workspace1 and modify state
        main_window._switch_workspace("Workspace1", initial_load=True)
        main_window.selection_groups = {"Default": {"description": "Default", "checked_paths": ["modified_file.py"]}}
        main_window.active_selection_group = "Default"
        
        # Switch to Workspace2 (should save Workspace1 state)
        main_window._switch_workspace("Workspace2")
        
        # Switch back to Workspace1 (should restore original state)
        main_window._switch_workspace("Workspace1")
        
        # Verify original state was restored
        assert main_window.current_folder_path == folder1
        assert main_window.current_scan_settings["include_subfolders"] is True
        assert "custom_ignore" in main_window.current_scan_settings["ignore_folders"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
