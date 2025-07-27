# --- File: workspace_dialog.py (Modified) ---
import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QLineEdit,
    QPushButton, QLabel, QMessageBox, QDialogButtonBox, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal

class WorkspaceManagerDialog(QDialog):
    # Signal emitted when a workspace is selected for switching
    workspace_selected = Signal(str)
    # Signal emitted when workspaces have been modified (added/deleted)
    # We can reuse this, or be more specific:
    workspace_added = Signal(str) # NEW: Emit the name of the added workspace
    workspace_deleted = Signal(str) # NEW: Emit the name of the deleted workspace
    # Keep a general updated signal? Optional.
    # workspaces_updated = Signal()


    def __init__(self, workspaces, current_workspace, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Workspace Manager")
        self.setMinimumWidth(400)
        self.setModal(True)

        self.workspaces_data = workspaces # Reference to the main window's dict
        self.current_workspace_name = current_workspace
        self.selected_workspace_on_close = None

        # --- Layouts ---
        main_layout = QVBoxLayout(self)
        list_layout = QHBoxLayout() # Layout for list and delete button
        new_ws_layout = QHBoxLayout()

        # --- Widgets ---
        self.workspace_list = QListWidget()
        self.workspace_list.itemDoubleClicked.connect(self.handle_selection_and_close)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Delete the selected workspace")
        self.delete_button.clicked.connect(self.delete_workspace)
        self.delete_button.setEnabled(False) # Disabled initially

        list_layout.addWidget(self.workspace_list, 1) # List takes more space
        list_layout.addWidget(self.delete_button)

        self.new_ws_input = QLineEdit()
        self.new_ws_input.setPlaceholderText("New workspace name")
        self.add_button = QPushButton("+")
        self.add_button.setToolTip("Add new workspace")
        self.add_button.clicked.connect(self.add_workspace)

        new_ws_layout.addWidget(self.new_ws_input, 1)
        new_ws_layout.addWidget(self.add_button)

        # Standard Button Box (Select / Close)
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.select_button = self.button_box.addButton("Select", QDialogButtonBox.ButtonRole.AcceptRole)
        self.select_button.setEnabled(False)
        self.select_button.clicked.connect(self.handle_selection_and_close)
        self.button_box.rejected.connect(self.reject)

        # --- Populate List ---
        self.populate_list()
        self.workspace_list.currentItemChanged.connect(self.update_button_states)

        # --- Assemble Layout ---
        main_layout.addLayout(list_layout)
        main_layout.addLayout(new_ws_layout)
        main_layout.addWidget(self.button_box)

        self.update_button_states() # Initial state

    def showEvent(self, event):
        """Debug workspace listing when dialog is shown."""
        super().showEvent(event)
        workspaces = self.workspaces_data.get('workspaces', {})
        print(f"[WORKSPACE_DIALOG] 🔍 Current workspaces: {list(workspaces.keys())}")
        print(f"[WORKSPACE_DIALOG] 📈 Data structure: {type(self.workspaces_data)}")
        print(f"[WORKSPACE_DIALOG] 🏇 Current workspace: {self.current_workspace_name}")

    def populate_list(self):
        """Show workspaces with their folder paths."""
        self.workspace_list.clear()
        
        # Ensure we have the correct structure
        workspaces = self.workspaces_data.get('workspaces', {})
        if not workspaces:
            # Create default if no workspaces
            self.workspaces_data['workspaces'] = {'Default': {}}
            workspaces = {'Default': {}}
        
        # Get workspace names (excluding reserved keys)
        workspace_names = [name for name in workspaces.keys() 
                          if name not in ['last_active_workspace']]
        
        if not workspace_names:
            # Always ensure Default exists
            workspace_names = ['Default']
        
        # Sort workspaces: Default first, then alphabetically
        sorted_names = sorted(workspace_names, key=lambda x: (x != 'Default', x.lower()))
        
        # Add items to list with folder info
        for name in sorted_names:
            ws_data = workspaces.get(name, {})
            folder_path = ws_data.get('folder_path', 'No folder')
            
            # Create item with folder info
            display_text = f"{name}"
            if folder_path and folder_path != 'No folder':
                # Show just the folder name for brevity
                import os
                folder_name = os.path.basename(folder_path) or folder_path
                display_text += f"  ({folder_name})"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, ws_data)  # Store full data
            
            self.workspace_list.addItem(item)
            
            # Highlight current workspace
            if name == self.current_workspace_name:
                self.workspace_list.setCurrentItem(item)
        
        print(f"[WORKSPACE_DIALOG] 📋 Listed {len(sorted_names)} workspaces: {sorted_names}")

    def update_button_states(self, current_item=None, previous_item=None):
        """Enable/disable Delete and Select buttons based on selection."""
        selected_item = self.workspace_list.currentItem()
        is_selected = selected_item is not None
        is_deletable = is_selected and selected_item.text() != "Default"

        self.delete_button.setEnabled(is_deletable)
        self.select_button.setEnabled(is_selected)

    def add_workspace(self):
        """Add new workspace with current folder and settings."""
        new_name = self.new_ws_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Input Error", "Please enter a name for the new workspace.")
            return
            
        # Check if name exists
        workspaces = self.workspaces_data.get('workspaces', {})
        if new_name in workspaces:
            QMessageBox.warning(self, "Input Error", f"Workspace '{new_name}' already exists.")
            return
            
        if new_name.lower() in ["last_active_workspace", "workspaces"]:
            QMessageBox.warning(self, "Input Error", f"'{new_name}' is a reserved name.")
            return
        
        # Get current settings from parent window
        parent_window = self.parent()
        if hasattr(parent_window, 'current_folder_path'):
            current_folder = parent_window.current_folder_path
            current_settings = parent_window.current_scan_settings or {}
            current_instructions = parent_window.instructions_panel.get_text() if hasattr(parent_window, 'instructions_panel') else ""
        else:
            current_folder = None
            current_settings = {"include_subfolders": True, "ignore_folders": set(), "live_watcher": True}
            current_instructions = ""
        
        # Create workspace with current settings
        if 'workspaces' not in self.workspaces_data:
            self.workspaces_data['workspaces'] = {}
        
        self.workspaces_data['workspaces'][new_name] = {
            "folder_path": current_folder,
            "scan_settings": {
                "include_subfolders": current_settings.get('include_subfolders', True),
                "ignore_folders": set(current_settings.get('ignore_folders', [])),
                "live_watcher": current_settings.get('live_watcher', True)
            },
            "instructions": current_instructions,
            "active_selection_group": "Default",
            "selection_groups": {
                "Default": {"description": "Default selection", "checked_paths": []}
            }
        }
        
        # Update UI
        item = QListWidgetItem(new_name)
        self.workspace_list.addItem(item)
        self.workspace_list.setCurrentItem(item)
        self.new_ws_input.clear()
        
        # Emit signal
        self.workspace_added.emit(new_name)
        print(f"[WORKSPACE_DIALOG] ➕ Created workspace: {new_name} with current settings")

    def delete_workspace(self):
        """Delete workspace from the actual data structure."""
        selected_item = self.workspace_list.currentItem()
        if not selected_item:
            return
            
        ws_name = selected_item.text()
        
        if ws_name == "Default":
            QMessageBox.warning(self, "Delete Error", "Cannot delete the 'Default' workspace.")
            return

        workspaces = self.workspaces_data.get('workspaces', {})
        if ws_name not in workspaces:
            QMessageBox.warning(self, "Delete Error", f"Workspace '{ws_name}' not found.")
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete the workspace '{ws_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Remove from actual data
            del workspaces[ws_name]
            
            # Remove from UI
            row = self.workspace_list.row(selected_item)
            self.workspace_list.takeItem(row)
            
            # Emit signal
            self.workspace_deleted.emit(ws_name)
            print(f"[WORKSPACE_DIALOG] 🗑️ Deleted workspace: {ws_name}")
            
            # If we deleted the current workspace, select Default
            if ws_name == self.current_workspace_name:
                default_item = self.workspace_list.findItems("Default", Qt.MatchExactly)
                if default_item:
                    self.workspace_list.setCurrentItem(default_item[0])

    def handle_selection_and_close(self):
        """Sets the selected workspace and accepts the dialog."""
        selected_item = self.workspace_list.currentItem()
        if selected_item:
            # Extract clean workspace name (remove display suffixes like " (folder_name)")
            display_text = selected_item.text()
            clean_name = display_text.split('  (')[0].strip()  # Note: double space before parentheses
            self.selected_workspace_on_close = clean_name
            self.accept()

    def get_selected_workspace(self):
        """Returns the name of the workspace selected when closing."""
        return self.selected_workspace_on_close