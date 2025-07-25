from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QDialog, QMessageBox
from core import selection_manager
from ui.dialogs.edit_selection_group_dialog import EditSelectionGroupDialog

class SelectionController(QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
    
    def update_ui(self):
        """Update the selection UI components."""
        if hasattr(self.mw, 'selection_manager_panel'):
            self.mw.selection_manager_panel.update_groups(
                list(self.mw.selection_groups.keys()), 
                self.mw.active_selection_group
            )

    # ---------- called by SelectionManagerPanel ----------
    @Slot(str)
    def on_group_changed(self, group_name):
        self.mw.active_selection_group = group_name
        paths = set(self.mw.selection_groups.get(group_name, {}).get("checked_paths", []))
        self.mw.tree_panel.set_pending_restore_paths(paths)
        self.mw._update_current_workspace_state()
        # self.mw._save_current_workspace_state()
        self.mw.selection_manager_panel.set_dirty(False)

    @Slot()
    def save_group(self):
        name = self.mw.selection_manager_panel.get_current_group_name()
        paths = self.mw.tree_panel.get_checked_paths(return_set=True) # This is correct, the wrapper handles it

        ws = self.mw.workspaces[self.mw.current_workspace_name]
        selection_manager.save_group(ws, name, "", paths)  # description handled in Edit dialog
        self.mw.selection_manager_panel.update_groups(list(self.mw.selection_groups.keys()), name)
        self.mw.selection_manager_panel.set_dirty(False)

    @Slot()
    def new_group(self):
        name = "New Group"
        counter = 1
        while name in self.mw.selection_groups:
            name = f"New Group {counter}"
            counter += 1
        ws = self.mw.workspaces[self.mw.current_workspace_name]
        selection_manager.save_group(ws, name, "", set())
        self.mw.selection_manager_panel.update_groups(list(self.mw.selection_groups.keys()), name)

    @Slot(str)
    def edit_group(self, group_name):
        if group_name not in self.mw.selection_groups:
            return
        data = self.mw.selection_groups[group_name]
        dlg = EditSelectionGroupDialog(group_name, data, self.mw.selection_groups, self.mw)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            new_name = result["name"]
            ws = self.mw.workspaces[self.mw.current_workspace_name]
            if new_name != group_name:
                selection_manager.delete_group(ws, group_name)
            selection_manager.save_group(ws, new_name, result["description"], set(result["checked_paths"]))
            self.mw.active_selection_group = new_name
            self.mw.selection_manager_panel.update_groups(list(self.mw.selection_groups.keys()), new_name)

    @Slot(str)
    def delete_group(self, group_name):
        if group_name == "Default":
            return
        ws = self.mw.workspaces[self.mw.current_workspace_name]
        selection_manager.delete_group(ws, group_name)
        self.mw.selection_groups = selection_manager.load_groups(ws)
        new_active = "Default" if self.mw.active_selection_group == group_name else self.mw.active_selection_group
        self.mw.selection_manager_panel.update_groups(list(self.mw.selection_groups.keys()), new_active)
