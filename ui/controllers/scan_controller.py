from PySide6.QtCore import QObject, Slot, Signal
from PySide6.QtWidgets import QFileDialog, QDialog
from dialogs.scan_config_dialog import ScanConfigDialog

class ScanController(QObject):
    folder_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mw = parent
        self.pending_restore_paths = set()

    # ---------------- public API ----------------
    def select_folder(self):
        print(f"[SCAN_CTRL] 📁 Opening folder selection dialog...")
        folder = QFileDialog.getExistingDirectory(self.mw, "Select Project Folder")
        print(f"[SCAN_CTRL] 📁 User selected folder: {folder}")
        if not folder:
            print(f"[SCAN_CTRL] ❌ No folder selected, returning")
            return

        print(f"[SCAN_CTRL] 📡 Emitting folder_selected signal...")
        self.folder_selected.emit(folder)
        print(f"[SCAN_CTRL] 🔧 Opening scan config dialog...")
        dlg = ScanConfigDialog(folder, self.mw.current_scan_settings, self.mw)
        print(f"[SCAN_CTRL] 🔧 Executing scan config dialog...")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            print(f"[SCAN_CTRL] ✅ Dialog accepted, starting scan...")
            self.start(folder, dlg.get_settings())
        else:
            print(f"[SCAN_CTRL] ❌ Dialog cancelled or rejected")

    def start(self, folder_path, settings, checked_paths_to_restore=None):
        print(f"[SCAN_CTRL] 🚀 Starting scan for: {folder_path}")
        print(f"[SCAN_CTRL] ⚙️ Scan settings: {settings}")
        
        self.mw.current_folder_path = folder_path
        self.mw.current_scan_settings = settings
        
        if checked_paths_to_restore:
            print(f"[SCAN_CTRL] 🔄 Restoring {len(checked_paths_to_restore)} checked paths")
            self.pending_restore_paths = set(checked_paths_to_restore)
        else:
            print(f"[SCAN_CTRL] 🆕 No paths to restore, clearing pending")
            self.pending_restore_paths.clear()

        self.mw.tree_panel.clear_tree()
        self.mw.tree_panel.show_loading(True)
        self.mw.statusBar().showMessage(f"Scanning {folder_path}...")
        
        # Use ONLY the streamlined scanner - fast and simple
        print(f"[SCAN_CTRL] 🚀 Using streamlined scanner (bg_scanner process only)")
        success = self.mw.streamlined_scanner.start_scan(folder_path, settings)
        
        if not success:
            print(f"[SCAN_CTRL] ❌ Failed to start streamlined scan")
            self.mw.tree_panel.show_loading(False)
            self.mw.statusBar().showMessage("Failed to start scan", 3000)
        
        # Note: The old blocking scanner call was:
        # self.mw.scanner.start_scan(folder_path, settings)

    @Slot()
    def refresh(self):
        if not self.mw.current_folder_path:
            return
        pending = self.mw.tree_panel.get_checked_paths(return_set=True) # This is correct, the wrapper handles it
        self.mw.tree_panel.set_pending_restore_paths(pending)
        
        # Use ONLY the streamlined scanner - no complex optimistic loading
        print(f"[SCAN_CTRL] 🚀 Refreshing with streamlined scanner...")
        self.start(self.mw.current_folder_path, self.mw.current_scan_settings)
    
    def start_scan(self, folder_path, settings):
        """Start background scan without clearing the tree (for optimistic loading)."""
        self.mw.statusBar().showMessage(f"Validating {folder_path}...", 2000)
        self.mw.scanner.start_scan(folder_path, settings)
