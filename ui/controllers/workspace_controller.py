from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QDialog
from dialogs.workspace_dialog import WorkspaceManagerDialog
from core import workspace_manager
from core.workspace_manager import get_default_scan_settings

class WorkspaceController(QObject):
    workspace_changed = Signal(str)
    workspace_created = Signal(str)  # New signal
    workspace_deleted = Signal(str)  # New signal

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window

    # ---------------- public API ----------------
    def open_manager(self):
        """Open the workspace manager dialog with full functionality."""
        print(f"[WORKSPACE] 📁 Opening workspace manager dialog...")
        
        # Ensure we have valid workspaces data
        if not self.mw.workspaces or 'workspaces' not in self.mw.workspaces:
            self.mw.workspaces = workspace_manager.load_workspaces(base_path=self.mw.testing_path)
        
        dlg = WorkspaceManagerDialog(self.mw.workspaces, self.mw.current_workspace_name, self.mw)
        
        # Connect new signals from dialog
        dlg.workspace_added.connect(self._handle_workspace_added)
        dlg.workspace_deleted.connect(self._handle_workspace_deleted)
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = dlg.get_selected_workspace()
            if selected and selected != self.mw.current_workspace_name:
                print(f"[WORKSPACE] 🔄 Switching from '{self.mw.current_workspace_name}' to '{selected}'")
                self.switch(selected)
        else:
            print("[WORKSPACE] ❌ Dialog cancelled")

    def switch(self, name, *, initial_load=False):
        """Switch to a different workspace."""
        if not initial_load:
            print(f"[WORKSPACE] 💾 Saving state before switching from '{self.mw.current_workspace_name}' to '{name}'")
            self.mw._update_current_workspace_state()
            self.mw._save_current_workspace_state()
        
        print(f"--- Switching to workspace: {name} ---")
        self.mw._switch_workspace(name, initial_load=initial_load)
        self.workspace_changed.emit(name)

    @Slot(str)
    def _handle_workspace_added(self, workspace_name):
        """Create new workspace with current scan settings."""
        print(f"[WORKSPACE] ➕ Creating new workspace: {workspace_name}")
        
        # Ensure workspaces structure exists
        if 'workspaces' not in self.mw.workspaces:
            self.mw.workspaces['workspaces'] = {}
        
        # Use fresh default settings for new workspaces, not current settings
        default_settings = get_default_scan_settings()
        
        # Create new workspace with fresh default settings
        self.mw.workspaces['workspaces'][workspace_name] = {
            "folder_path": None,  # New workspaces start with no folder selected
            "scan_settings": default_settings,
            "instructions": self.mw.instructions_panel.get_text() if hasattr(self.mw, 'instructions_panel') else "",
            "active_selection_group": "Default",
            "selection_groups": {
                "Default": {
                    "description": "Default selection",
                    "checked_paths": []  # Start fresh
                }
            }
        }
        
        # Save immediately
        workspace_manager.save_workspaces(self.mw.workspaces, base_path=self.mw.testing_path)
        print(f"[WORKSPACE] ✅ Created workspace '{workspace_name}' with settings from '{self.mw.current_workspace_name}'")
        
        # Show status bar message
        self.mw.statusBar().showMessage(f"Workspace '{workspace_name}' created.", 3000)
        
        # Emit signal
        self.workspace_created.emit(workspace_name)
        
        # Auto-switch to new workspace
        self.switch(workspace_name)

    @Slot(str)
    def _handle_workspace_deleted(self, workspace_name):
        """Handle workspace deletion from dialog."""
        print(f"[WORKSPACE] 🗑️ Deleted workspace: {workspace_name}")
        if workspace_name in self.mw.workspaces['workspaces']:
            del self.mw.workspaces['workspaces'][workspace_name]
            
            # If deleting current workspace, switch to Default
            if workspace_name == self.mw.current_workspace_name:
                self.switch("Default")
            
            workspace_manager.save_workspaces(self.mw.workspaces, base_path=self.mw.testing_path)
            
            # Show status bar message
            self.mw.statusBar().showMessage(f"Workspace '{workspace_name}' deleted.", 3000)
            
            self.workspace_deleted.emit(workspace_name)
