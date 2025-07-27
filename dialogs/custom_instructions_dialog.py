# --- File: custom_instructions_dialog.py ---
import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QPushButton,
    QLabel, QDialogButtonBox, QScrollArea, QWidget, QMessageBox, QSizePolicy, QCheckBox
)
from PySide6.QtCore import Qt, Signal, Slot

# --- Widget for editing a single instruction ---
class InstructionEditorWidget(QWidget):
    # Signals to bubble up actions to the parent dialog
    instruction_updated = Signal(str, str) # name, new_text
    instruction_deleted = Signal(str) # name

    def __init__(self, name, text, parent=None):
        super().__init__(parent)
        self.instruction_name = name # Store the original name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5) # Add some vertical margin

        self.name_label = QLabel(f"<b>{name}</b>") # Display name (non-editable for now)
        self.name_label.setMinimumWidth(100) # Ensure name label has some width
        self.name_label.setMaximumWidth(150)
        self.name_label.setWordWrap(True)

        self.text_edit = QTextEdit(text)
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.text_edit.setMinimumHeight(60) # Ensure it's not too small

        self.update_button = QPushButton("Update")
        self.update_button.setToolTip("Save changes to this instruction")
        self.update_button.clicked.connect(self.on_update)

        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Delete this instruction")
        self.delete_button.clicked.connect(self.on_delete)
        # Disable delete for "Default" if needed (can be handled in dialog)
        if name == "Default":
            self.delete_button.setEnabled(False)
            self.delete_button.setToolTip("Cannot delete the 'Default' instruction")


        button_layout = QVBoxLayout()
        button_layout.addWidget(self.update_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch() # Push buttons to top

        layout.addWidget(self.name_label)
        layout.addWidget(self.text_edit, 1) # Text edit takes expanding space
        layout.addLayout(button_layout)

    @Slot()
    def on_update(self):
        """Emit signal to update this instruction."""
        current_text = self.text_edit.toPlainText()
        self.instruction_updated.emit(self.instruction_name, current_text)

    @Slot()
    def on_delete(self):
        """Emit signal to delete this instruction."""
        # Confirmation should probably happen in the main dialog
        self.instruction_deleted.emit(self.instruction_name)

# --- Main Dialog ---
class CustomInstructionsDialog(QDialog):
    instructions_changed = Signal(dict, bool, dict) # global, use_local, local

    def __init__(self, global_instructions, workspace_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Instructions Manager")
        self.setMinimumSize(600, 500)
        self.setModal(True)

        self.global_instructions = global_instructions
        self.workspace_data = workspace_data
        self._dirty = False

        main_layout = QVBoxLayout(self)

        # --- Workspace-specific settings ---
        self.use_local_checkbox = QCheckBox("Use workspace-specific instruction templates")
        self.use_local_checkbox.setChecked(self.workspace_data.get('use_local_templates', False))
        self.use_local_checkbox.toggled.connect(self._toggle_template_scope)
        main_layout.addWidget(self.use_local_checkbox)

        # --- Container for editors ---
        self.editors_container = QWidget()
        editors_layout = QVBoxLayout(self.editors_container)
        editors_layout.setContentsMargins(0,0,0,0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.scroll_widget)
        editors_layout.addWidget(self.scroll_area)

        # --- Add new instruction UI ---
        add_layout = QHBoxLayout()
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("Enter new instruction name...")
        self.add_button = QPushButton("Add New")
        self.add_button.clicked.connect(self.add_new_instruction_ui)
        add_layout.addWidget(self.new_name_input, 1)
        add_layout.addWidget(self.add_button)
        editors_layout.addLayout(add_layout)
        main_layout.addWidget(self.editors_container)

        # --- Dialog Buttons (Close) ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

        self._toggle_template_scope(self.use_local_checkbox.isChecked())
        self.populate_instructions()

    def _get_active_instructions(self):
        if self.use_local_checkbox.isChecked():
            return self.workspace_data.setdefault('local_custom_instructions', {})
        return self.global_instructions

    def populate_instructions(self):
        """Clears and refills the scroll area with instruction editors."""
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        instructions = self._get_active_instructions()
        sorted_names = sorted(instructions.keys())
        for name in sorted_names:
            text = instructions.get(name, "")
            self.add_instruction_widget(name, text)

    def add_instruction_widget(self, name, text):
        """Adds an InstructionEditorWidget to the scroll layout."""
        editor_widget = InstructionEditorWidget(name, text)
        editor_widget.instruction_updated.connect(self.handle_instruction_update)
        editor_widget.instruction_deleted.connect(self.handle_instruction_delete_request)
        self.scroll_layout.addWidget(editor_widget)

    @Slot()
    def add_new_instruction_ui(self):
        """Adds a new instruction entry section."""
        instructions = self._get_active_instructions()
        new_name = self.new_name_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Input Error", "Please enter a name for the new instruction.")
            return
        if new_name in instructions:
             QMessageBox.warning(self, "Input Error", f"An instruction named '{new_name}' already exists.")
             return
        if new_name == "Default":
             QMessageBox.warning(self, "Input Error", "Cannot use the reserved name 'Default'.")
             return

        instructions[new_name] = ""
        self.add_instruction_widget(new_name, "")
        self.new_name_input.clear()
        self._dirty = True
        QTimer.singleShot(0, self.scroll_area.verticalScrollBar().setValue, self.scroll_area.verticalScrollBar().maximum())

    @Slot(str, str)
    def handle_instruction_update(self, name, new_text):
        """Update the data dictionary when an instruction's text is updated."""
        instructions = self._get_active_instructions()
        if name in instructions:
            if instructions[name] != new_text:
                instructions[name] = new_text
                self._dirty = True
                print(f"Instruction '{name}' updated in memory.")
            else:
                 print(f"Instruction '{name}' text unchanged.")
        else:
             print(f"Warning: Tried to update non-existent instruction '{name}'")

    @Slot(str)
    def handle_instruction_delete_request(self, name):
        """Handle delete request, confirm, then remove data and widget."""
        instructions = self._get_active_instructions()
        if name == "Default":
            QMessageBox.warning(self, "Delete Error", "Cannot delete the 'Default' instruction.")
            return

        reply = QMessageBox.question(self, "Confirm Delete",
                                     f"Are you sure you want to delete the instruction named '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            if name in instructions:
                del instructions[name]
                self._dirty = True
                print(f"Instruction '{name}' deleted from data.")
                for i in range(self.scroll_layout.count()):
                    item = self.scroll_layout.itemAt(i)
                    widget = item.widget()
                    if isinstance(widget, InstructionEditorWidget) and widget.instruction_name == name:
                        widget.deleteLater()
                        self.scroll_layout.removeItem(item)
                        break
            else:
                 print(f"Warning: Tried to delete instruction '{name}' but it wasn't found in data.")

    def reject(self):
        """Handle dialog close."""
        if self._dirty:
             self.instructions_changed.emit(
                 self.global_instructions,
                 self.workspace_data.get('use_local_templates', False),
                 self.workspace_data.get('local_custom_instructions', {})
             )
        super().reject()

    @Slot(bool)
    def _toggle_template_scope(self, use_local):
        self.workspace_data['use_local_templates'] = use_local
        self._dirty = True

        # First, repopulate the list with the correct instruction set
        self.populate_instructions()

        # Then, set the enabled state of the controls based on the mode
        is_editable = use_local
        
        # Enable/disable the container for adding new instructions
        self.new_name_input.setEnabled(is_editable)
        self.add_button.setEnabled(is_editable)

        # Enable/disable the individual editor widgets already in the list
        for i in range(self.scroll_layout.count()):
            item = self.scroll_layout.itemAt(i)
            if item and item.widget():
                item.widget().setEnabled(is_editable)