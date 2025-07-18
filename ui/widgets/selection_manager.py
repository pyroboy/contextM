# ui/widgets/selection_manager.py

"""The main Selection Manager panel widget."""

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QComboBox, QPushButton, QMessageBox, QSizePolicy
)


class SelectionManagerPanel(QWidget):
    """
    A panel for managing selection groups.
    """
    group_changed = Signal(str)          # (new_group_name)
    save_requested = Signal()            # Request to save the active group
    new_requested = Signal()             # Request to create a new group
    edit_requested = Signal(str)         # (group_name)
    delete_requested = Signal(str)       # (group_name)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_dirty = False

        # --- Widgets ---
        self.group_combo = QComboBox()
        self.group_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.group_combo.setToolTip("Switch between selection groups")

        self.save_button = QPushButton("💾 Save")
        self.save_button.setToolTip("Save current selection (Ctrl+S)")

        self.new_button = QPushButton("+ New")
        self.new_button.setToolTip("Create new selection group")

        self.edit_button = QPushButton("✏️ Edit")
        self.edit_button.setToolTip("Rename / inspect group")

        self.delete_button = QPushButton("🗑️ Delete")
        self.delete_button.setToolTip("Delete selection group")

        # --- Layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        layout.addWidget(self.group_combo)
        layout.addWidget(self.save_button)
        layout.addWidget(self.new_button)
        layout.addWidget(self.edit_button)
        layout.addWidget(self.delete_button)

        # --- Connections ---
        self.group_combo.currentTextChanged.connect(self._on_group_changed)
        self.save_button.clicked.connect(self.save_requested)
        self.new_button.clicked.connect(self.new_requested)
        self.edit_button.clicked.connect(self._on_edit_clicked)
        self.delete_button.clicked.connect(self._on_delete_clicked)

    def update_groups(self, groups: list[str], active_group: str):
        """Populates the combo box with the list of group names."""
        self.group_combo.blockSignals(True)
        current_text = self.get_current_group_name()
        self.group_combo.clear()
        self.group_combo.addItems(sorted(groups))

        if active_group in groups:
            self.group_combo.setCurrentText(active_group)
        elif current_text in groups:
            self.group_combo.setCurrentText(current_text)
        
        self.group_combo.blockSignals(False)
        if self.group_combo.currentText() != current_text:
             self._on_group_changed(self.group_combo.currentText())
        self._update_button_states()

    def get_current_group_name(self, with_dirty_marker: bool = False) -> str:
        """Returns the name of the currently selected group."""
        text = self.group_combo.currentText()
        if not with_dirty_marker:
            return text.removesuffix('*')
        return text

    def set_dirty(self, is_dirty: bool):
        """Sets the dirty state, adding/removing an asterisk from the current group name."""
        if self._is_dirty == is_dirty:
            return
        self._is_dirty = is_dirty

        current_text = self.get_current_group_name(with_dirty_marker=True)
        current_index = self.group_combo.currentIndex()
        if current_index == -1: return

        self.group_combo.blockSignals(True)
        if is_dirty and not current_text.endswith('*'):
            self.group_combo.setItemText(current_index, f"{current_text}*")
        elif not is_dirty and current_text.endswith('*'):
            self.group_combo.setItemText(current_index, current_text[:-1])
        self.group_combo.blockSignals(False)
        self._update_button_states()

    def _on_group_changed(self, group_name: str):
        if group_name:
            self.group_changed.emit(group_name.removesuffix('*'))
        self.set_dirty(False)
        self._update_button_states()

    def _on_edit_clicked(self):
        current_group = self.get_current_group_name()
        if current_group:
            self.edit_requested.emit(current_group)

    def _on_delete_clicked(self):
        current_group = self.get_current_group_name()
        if not current_group:
            return

        if current_group == "Default":
            QMessageBox.warning(self, "Cannot Delete", "The 'Default' group cannot be deleted.")
            return

        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete the group '{current_group}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.delete_requested.emit(current_group)

    def _update_button_states(self):
        """Enables or disables buttons based on the current state."""
        current_group = self.get_current_group_name()
        has_group = bool(current_group)
        is_default = current_group == "Default"

        self.save_button.setEnabled(self._is_dirty and has_group)
        self.edit_button.setEnabled(has_group)
        self.delete_button.setEnabled(has_group and not is_default)
