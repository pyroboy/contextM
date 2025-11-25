import os
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

    def _detect_and_resolve_drift(self, stored_paths: set, group_data: dict) -> set:
        """Smart drift detection.

        1. Missing Files: File is in selection but gone from disk.
        2. New Files: File creation / modification time > group saved time.
        """
        import os

        final_paths = stored_paths.copy()
        missing_files = []
        new_candidates = []

        # 1. Get Last Saved Timestamp (legacy groups may not have this)
        last_saved_time = group_data.get("last_updated", None)

        # 2. Detect Missing Files
        for path in stored_paths:
            if not os.path.exists(path):
                missing_files.append(path)

        # 3. Detect TRULY New Files (time-based) only if we have a timestamp
        if last_saved_time is not None:
            scanned_folders = set()
            for path in stored_paths:
                folder = os.path.dirname(path)
                if folder in scanned_folders or not os.path.exists(folder):
                    continue

                scanned_folders.add(folder)
                try:
                    with os.scandir(folder) as entries:
                        for entry in entries:
                            if not entry.is_file():
                                continue

                            norm_path = os.path.normpath(entry.path).replace('\\', '/')

                            # Skip files already in the selection
                            if norm_path in stored_paths:
                                continue

                            try:
                                stats = entry.stat()
                                created_time = getattr(stats, "st_ctime", stats.st_mtime)
                                # 1s buffer to reduce race conditions
                                if created_time > (last_saved_time + 1.0):
                                    new_candidates.append(norm_path)
                            except OSError:
                                pass
                except OSError:
                    pass

        # 4. Exit early if nothing changed
        if not missing_files and not new_candidates:
            return final_paths

        # 5. Build message
        msg_text = "Repo changes detected since this group was last saved:\n\n"
        if missing_files:
            msg_text += f"❌ {len(missing_files)} selected files have been deleted.\n"
        if new_candidates:
            msg_text += f"🆕 {len(new_candidates)} new files added to selected folders.\n"

        msg_text += "\nDo you want to update the selection?"

        # 6. Popup
        reply = QMessageBox.question(
            self.mw, "Selection Update", msg_text,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )

        # 7. Apply
        if reply == QMessageBox.Yes:
            # Remove missing
            for p in missing_files:
                if p in final_paths:
                    final_paths.remove(p)
            # Add new
            for p in new_candidates:
                final_paths.add(p)

            # Log
            if hasattr(self.mw, "file_changes_panel"):
                if missing_files:
                    self.mw.file_changes_panel.add_system_message(
                        f"⚠️ Cleaned up {len(missing_files)} deleted files."
                    )
                if new_candidates:
                    self.mw.file_changes_panel.add_system_message(
                        f"✨ Auto-added {len(new_candidates)} new files."
                    )

            # Mark as dirty so timestamp updates when the user explicitly saves
            if hasattr(self.mw, "selection_manager_panel"):
                self.mw.selection_manager_panel.set_dirty(True)

        return final_paths

    # ---------- called by SelectionManagerPanel ----------
    @Slot(str)
    def on_group_changed(self, group_name):
        self.mw.active_selection_group = group_name
        
        # 1. Get full group data
        group_data = self.mw.selection_groups.get(group_name, {})
        stored_paths = group_data.get("checked_paths", [])
        
        # 2. Convert to absolute paths with forced Forward Slashes
        absolute_paths = set()
        workspace_root = self.mw.current_folder_path
        
        if workspace_root:
            for path in stored_paths:
                # Normalize to forward slashes for consistency with Tree Model
                if os.path.isabs(path):
                    norm = os.path.normpath(path).replace('\\', '/')
                    absolute_paths.add(norm)
                else:
                    full = os.path.join(workspace_root, path)
                    norm = os.path.normpath(full).replace('\\', '/')
                    absolute_paths.add(norm)
        else:
            absolute_paths = {os.path.normpath(p).replace('\\', '/') for p in stored_paths}

        # CHECK FOR DRIFT (time-aware, using group_data)
        absolute_paths = self._detect_and_resolve_drift(absolute_paths, group_data)

        # 3. Apply to Tree Panel (Works for both Old and New TreePanel)
        # This fixes the visual bug: unconditionally set paths
        self.mw.tree_panel.set_pending_restore_paths(absolute_paths)
        self.mw.tree_panel.set_checked_paths(absolute_paths, relative=False)
        
        # 4. Update Repo Status Panel
        if hasattr(self.mw, 'file_changes_panel'):
            self.mw.file_changes_panel.add_system_message(f"Switched to group: '{group_name}'")
            self.mw.file_changes_panel.update_active_selection(absolute_paths)

        # 5. Update UI State
        self.mw.selection_manager_panel.set_dirty(False)
        if hasattr(self.mw, 'update_aggregation_and_tokens'):
            self.mw.update_aggregation_and_tokens()

    @Slot()
    def save_group(self):
        name = self.mw.selection_manager_panel.get_current_group_name()
        # Get checked paths as relative paths for storage
        paths = self.mw.tree_panel.get_checked_paths(relative=True, return_set=True)
        
        ws = self.mw.workspaces['workspaces'][self.mw.current_workspace_name]
        selection_manager.save_group(ws, name, "", paths)  # description handled in Edit dialog
        print(f"[SELECTION] ✅ Group '{name}' saved with {len(paths)} paths")

        # Update workspace state
        self.mw.selection_groups = selection_manager.load_groups(ws)
        self.mw.active_selection_group = name
        
        # Update UI
        self.mw.selection_manager_panel.update_groups(
            list(self.mw.selection_groups.keys()), 
            name
        )
        self.mw.selection_manager_panel.set_dirty(False)
        
        # Update aggregation view
        if hasattr(self.mw, 'update_aggregation_and_tokens'):
            self.mw.update_aggregation_and_tokens()
        
        # Update Repo Status panel
        if hasattr(self.mw, 'file_changes_panel'):
            self.mw.file_changes_panel.add_system_message(f"Saved group: '{name}' with {len(paths)} files")
            current_abs = self.mw.tree_panel.get_checked_paths(relative=False, return_set=True)
            self.mw.file_changes_panel.update_active_selection(current_abs)

    @Slot()
    def new_group(self):
        name = "New Group"
        counter = 1
        while name in self.mw.selection_groups:
            name = f"New Group {counter}"
            counter += 1
        ws = self.mw.workspaces['workspaces'][self.mw.current_workspace_name]
        selection_manager.save_group(ws, name, "", set())
        self.mw.selection_manager_panel.update_groups(list(self.mw.selection_groups.keys()), name)
        if hasattr(self.mw, 'file_changes_panel'):
            self.mw.file_changes_panel.add_system_message(f"Created new group: {name}")
            self.mw.file_changes_panel.update_active_selection(set())

    @Slot(str)
    def edit_group(self, group_name):
        if group_name not in self.mw.selection_groups:
            return
        data = self.mw.selection_groups[group_name]
        dlg = EditSelectionGroupDialog(group_name, data, self.mw.selection_groups, self.mw)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            new_name = result["name"]
            ws = self.mw.workspaces['workspaces'][self.mw.current_workspace_name]
            if new_name != group_name:
                selection_manager.delete_group(ws, group_name)
            selection_manager.save_group(ws, new_name, result["description"], set(result["checked_paths"]))
            self.mw.active_selection_group = new_name
            self.mw.selection_manager_panel.update_groups(list(self.mw.selection_groups.keys()), new_name)

    @Slot(str)
    def delete_group(self, group_name):
        if group_name == "Default":
            return
        ws = self.mw.workspaces['workspaces'][self.mw.current_workspace_name]
        selection_manager.delete_group(ws, group_name)
        self.mw.selection_groups = selection_manager.load_groups(ws)
        new_active = "Default" if self.mw.active_selection_group == group_name else self.mw.active_selection_group
        self.mw.active_selection_group = new_active
        self.mw.selection_manager_panel.update_groups(list(self.mw.selection_groups.keys()), new_active)
        # Trigger selection change logic to refresh tree
        self.on_group_changed(new_active)
        # Log
        if hasattr(self.mw, 'file_changes_panel'):
            self.mw.file_changes_panel.add_system_message(f"Deleted group: '{group_name}'")
