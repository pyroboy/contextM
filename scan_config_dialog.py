# --- File: scan_config_dialog.py ---
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QDialogButtonBox, QCheckBox, QFormLayout, QWidget
)
from PySide6.QtCore import Qt

# --- Default Configuration (needed for the dialog) ---
DEFAULT_IGNORE_FOLDERS = {
    ".git", ".svn", ".hg", ".vscode", ".idea", "node_modules", "venv", ".venv",
    "__pycache__", "build", "dist", "out", ".next", "coverage", "target", "bin", "obj"
}

# --- Configuration Dialog ---
class ScanConfigDialog(QDialog):
    def __init__(self, folder_path, initial_settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Folder Scan")
        self.setMinimumWidth(500)
        self.setModal(True)
        self.folder_path = folder_path
        self.settings = initial_settings if initial_settings else {
            'include_subfolders': True,
            'ignore_folders': set(DEFAULT_IGNORE_FOLDERS) # Use default if none provided
        }
        # Ensure ignore_folders is a set, using default as fallback
        self.settings['ignore_folders'] = set(self.settings.get('ignore_folders', DEFAULT_IGNORE_FOLDERS))

        self.layout = QVBoxLayout(self)

        self.path_label = QLabel(f"<b>Configure scan for:</b><br>{folder_path}")
        self.path_label.setWordWrap(True)
        self.layout.addWidget(self.path_label)
        self.layout.addSpacing(10)

        form_layout = QFormLayout()
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)

        self.subfolder_checkbox = QCheckBox("Include files from sub-folders")
        self.subfolder_checkbox.setChecked(self.settings['include_subfolders'])
        form_layout.addRow(self.subfolder_checkbox)

        # Input for ignored folders
        ignore_folders_widget = QWidget()
        folder_layout = QHBoxLayout(ignore_folders_widget)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        # Initialize input with sorted list from the current settings set
        self.ignore_folders_input = QLineEdit(", ".join(sorted(list(self.settings['ignore_folders']))))
        self.ignore_folders_input.setPlaceholderText("e.g., .git, node_modules, venv")

        reset_folders_button = QPushButton("Reset")
        reset_folders_button.setToolTip("Reset ignored folders to default")
        reset_folders_button.clicked.connect(self.reset_ignored_folders)

        folder_layout.addWidget(self.ignore_folders_input, 1) # Input takes available space
        folder_layout.addWidget(reset_folders_button)

        form_layout.addRow("Ignore Folder Names:", ignore_folders_widget)

        self.layout.addLayout(form_layout)
        self.layout.addSpacing(10)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

    def reset_ignored_folders(self):
        """Resets the ignored folders input field to the default set."""
        self.ignore_folders_input.setText(", ".join(sorted(list(DEFAULT_IGNORE_FOLDERS))))

    def accept(self):
        """Updates the settings dictionary when OK is clicked."""
        self.settings['include_subfolders'] = self.subfolder_checkbox.isChecked()
        folders_text = self.ignore_folders_input.text().strip()
        if folders_text:
            # Create set from comma-separated input, ignoring empty strings and converting to lowercase
            self.settings['ignore_folders'] = {folder.strip().lower() for folder in folders_text.split(',') if folder.strip()}
        else:
             # Set to empty set if input is empty
             self.settings['ignore_folders'] = set()
        print(f"Dialog accepted with settings: {self.settings}")
        super().accept() # Close the dialog with Accepted state

    def get_settings(self):
        """Returns the configured settings dictionary."""
        return self.settings