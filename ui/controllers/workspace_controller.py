from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QDialog
from dialogs.workspace_dialog import WorkspaceManagerDialog
from core import workspace_manager

class WorkspaceController(QObject):
    workspace_changed = Signal(str)

    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window

    # ---------------- public API ----------------
    def open_manager(self):
        dlg = WorkspaceManagerDialog(self.mw.workspaces, self.mw.current_workspace_name, self.mw)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            selected = dlg.get_selected_workspace()
            if selected and selected != self.mw.current_workspace_name:
                self.mw._save_current_workspace_state() # Save state of the OLD workspace before switching
                self.switch(selected)

    def switch(self, name, *, initial_load=False):
        """Switch to a different workspace."""
        if not initial_load:
            print(f"[WORKSPACE] 💾 Saving state before switching from '{self.mw.current_workspace_name}' to '{name}'")
            self.mw._update_current_workspace_state()
            self.mw._save_current_workspace_state()
        
        self.mw._switch_workspace(name, initial_load=initial_load)
        self.workspace_changed.emit(name)

