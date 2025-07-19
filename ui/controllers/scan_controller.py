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
        folder = QFileDialog.getExistingDirectory(self.mw, "Select Project Folder")
        if not folder:
            return

        self.folder_selected.emit(folder)
        dlg = ScanConfigDialog(folder, self.mw.current_scan_settings, self.mw)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.start(folder, dlg.get_settings())

    def start(self, folder_path, settings, checked_paths_to_restore=None):
        self.mw.current_folder_path = folder_path
        self.mw.current_scan_settings = settings
        if checked_paths_to_restore:
            self.pending_restore_paths = set(checked_paths_to_restore)
        else:
            self.pending_restore_paths.clear()

        self.mw.tree_panel.clear_tree()
        self.mw.tree_panel.show_loading(True)
        self.mw.statusBar().showMessage(f"Scanning {folder_path}...")
        self.mw.scanner.start_scan(folder_path, settings)

    @Slot()
    def refresh(self):
        if not self.mw.current_folder_path:
            return
        pending = self.mw.tree_panel.get_checked_paths(return_set=True)
        self.mw.tree_panel.set_pending_restore_paths(pending)
        self.start(self.mw.current_folder_path, self.mw.current_scan_settings)
