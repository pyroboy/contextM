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

    def populate_list(self):
        """Clears and refills the list widget from workspace data."""
        self.workspace_list.clear()
        if "Default" in self.workspaces_data:
             item = QListWidgetItem("Default")
             self.workspace_list.addItem(item)
             if "Default" == self.current_workspace_name:
                 self.workspace_list.setCurrentItem(item) # Select if current

        other_workspaces = sorted([name for name in self.workspaces_data if name != "Default" and name != "last_active_workspace"])
        for name in other_workspaces:
            item = QListWidgetItem(name)
            self.workspace_list.addItem(item)
            if name == self.current_workspace_name:
                self.workspace_list.setCurrentItem(item) # Select if current

    def update_button_states(self, current_item=None, previous_item=None):
        """Enable/disable Delete and Select buttons based on selection."""
        selected_item = self.workspace_list.currentItem()
        is_selected = selected_item is not None
        is_deletable = is_selected and selected_item.text() != "Default"

        self.delete_button.setEnabled(is_deletable)
        self.select_button.setEnabled(is_selected)

    def add_workspace(self):
        """Adds a new workspace name to the list and emits a signal."""
        new_name = self.new_ws_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Input Error", "Please enter a name for the new workspace.")
            return
        if new_name in self.workspaces_data:
            QMessageBox.warning(self, "Input Error", f"Workspace '{new_name}' already exists.")
            return
        if new_name == "last_active_workspace" or new_name == "Default": # Reserved keys
             QMessageBox.warning(self, "Input Error", f"'{new_name}' is a reserved name.")
             return

        # Only add visually and emit signal. MainWindow will handle data creation.
        item = QListWidgetItem(new_name)
        self.workspace_list.addItem(item)
        self.workspace_list.setCurrentItem(item) # Select the new item
        print(f"Workspace '{new_name}' added to list, signalling main window.")
        self.new_ws_input.clear()
        self.workspace_added.emit(new_name) # <--- Emit NEW signal

    def delete_workspace(self):
        """Deletes the selected workspace after confirmation and emits signal."""
        selected_item = self.workspace_list.currentItem()
        if not selected_item: return
        ws_name = selected_item.text()

        if ws_name == "Default":
            QMessageBox.warning(self, "Delete Error", "Cannot delete the 'Default' workspace.")
            return

        reply = QMessageBox.question(self, "Confirm Delete",
                                     f"Are you sure you want to delete the workspace '{ws_name}'?\n"
                                     "This action cannot be undone.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            # Remove from list visually first
            row = self.workspace_list.row(selected_item)
            self.workspace_list.takeItem(row)
            print(f"Workspace '{ws_name}' deleted from list, signalling main window.")
            self.workspace_deleted.emit(ws_name) # <--- Emit NEW signal
            # Main window will handle actual data deletion

    def handle_selection_and_close(self):
        """Sets the selected workspace and accepts the dialog."""
        selected_item = self.workspace_list.currentItem()
        if selected_item:
            self.selected_workspace_on_close = selected_item.text()
            self.accept()

    def get_selected_workspace(self):
        """Returns the name of the workspace selected when closing."""
        return self.selected_workspace_on_close