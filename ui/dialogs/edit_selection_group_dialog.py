# ui/dialogs/edit_selection_group_dialog.py

"""Modal dialog for editing a selection group's properties."""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPlainTextEdit,
    QListWidget, QLabel, QDialogButtonBox, QPushButton, QAbstractItemView
)


class EditSelectionGroupDialog(QDialog):
    """
    A dialog for editing the properties of a selection group.
    """
    def __init__(self, group_name: str, group_data: dict, all_groups: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Selection Group – {group_name}")

        self.original_name = group_name
        # Get all other group names for validation, case-insensitively
        self.other_group_names = {name.lower() for name in all_groups if name.lower() != group_name.lower()}

        # --- Widgets ---
        self.name_edit = QLineEdit(group_name)
        self.description_edit = QPlainTextEdit(group_data.get("description", ""))
        
        self.path_list = QListWidget()
        self.path_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.path_list.addItems(sorted(group_data.get("checked_paths", [])))

        file_count = len(group_data.get("checked_paths", []))
        self.status_label = QLabel(f"Status: {file_count} files / 0 tokens") # Token count is a placeholder

        # --- Buttons ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.reset_button = QPushButton("Reset to Current Selection")
        self.button_box.addButton(self.reset_button, QDialogButtonBox.ActionRole)

        # --- Layout ---
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        form_layout.addRow("Name:", self.name_edit)
        form_layout.addRow("Description:", self.description_edit)
        layout.addLayout(form_layout)
        layout.addWidget(QLabel("Files/Folders in group:"))
        layout.addWidget(self.path_list)
        layout.addWidget(self.status_label)
        layout.addWidget(self.button_box)

        # --- Connections ---
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.name_edit.textChanged.connect(self._validate_name)

        self._validate_name()  # Initial validation check

    def _validate_name(self):
        """Validates the group name to ensure it's not empty or a duplicate."""
        name = self.name_edit.text().strip()
        ok_button = self.button_box.button(QDialogButtonBox.Ok)

        is_valid = True
        if not name:
            is_valid = False
        elif name.lower() in self.other_group_names:
            is_valid = False
        elif self.original_name == "Default" and name != "Default":
            is_valid = False
        
        ok_button.setEnabled(is_valid)

    def set_current_selection(self, paths: list[str]):
        """Updates the list widget with the current tree selection."""
        self.path_list.clear()
        self.path_list.addItems(sorted(paths))
        file_count = len(paths)
        self.status_label.setText(f"Status: {file_count} files / 0 tokens")

    def get_result(self) -> dict:
        """Returns the updated group data, including the potentially new name."""
        return {
            "name": self.name_edit.text().strip(),
            "description": self.description_edit.toPlainText(),
            "checked_paths": [self.path_list.item(i).text() for i in range(self.path_list.count())],
        }
