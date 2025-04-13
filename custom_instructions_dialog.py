# --- File: custom_instructions_dialog.py ---
import sys
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QPushButton,
    QLabel, QDialogButtonBox, QScrollArea, QWidget, QMessageBox, QSizePolicy
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
    # Signal that instructions have changed and need saving/dropdown update
    instructions_changed = Signal()

    def __init__(self, instructions_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Instructions Manager")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        # Store a reference or copy? Let's work on a copy then update on close/save
        self.instructions_data = instructions_data # Reference to main data dict
        self._dirty = False # Track if changes were made

        # --- Main Layout ---
        main_layout = QVBoxLayout(self)

        # --- Scroll Area ---
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget() # Content widget for scroll area
        self.scroll_layout = QVBoxLayout(self.scroll_widget) # Layout for content widget
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop) # Add items to top
        self.scroll_area.setWidget(self.scroll_widget)

        # --- Buttons Below Scroll Area ---
        add_layout = QHBoxLayout()
        self.new_name_input = QLineEdit()
        self.new_name_input.setPlaceholderText("Name for new instruction")
        self.add_button = QPushButton("Add New Instruction")
        self.add_button.clicked.connect(self.add_new_instruction_ui)

        add_layout.addWidget(self.new_name_input, 1)
        add_layout.addWidget(self.add_button)

        # --- Standard Button Box ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self.reject) # Close button triggers reject

        # --- Assemble Main Layout ---
        main_layout.addWidget(self.scroll_area, 1) # Scroll area takes most space
        main_layout.addLayout(add_layout)
        main_layout.addWidget(self.button_box)

        # --- Populate Instructions ---
        self.populate_instructions()

    def populate_instructions(self):
        """Clears and refills the scroll area with instruction editors."""
        # Clear existing widgets from layout first
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Add Default first if present
        if "Default" in self.instructions_data:
            self.add_instruction_widget("Default", self.instructions_data["Default"])

        # Add others sorted
        other_names = sorted([name for name in self.instructions_data if name != "Default"])
        for name in other_names:
             self.add_instruction_widget(name, self.instructions_data[name])

    def add_instruction_widget(self, name, text):
        """Adds an InstructionEditorWidget to the scroll layout."""
        editor_widget = InstructionEditorWidget(name, text)
        editor_widget.instruction_updated.connect(self.handle_instruction_update)
        editor_widget.instruction_deleted.connect(self.handle_instruction_delete_request)
        self.scroll_layout.addWidget(editor_widget)

    @Slot()
    def add_new_instruction_ui(self):
        """Adds a new instruction entry section."""
        new_name = self.new_name_input.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Input Error", "Please enter a name for the new instruction.")
            return
        if new_name in self.instructions_data:
             QMessageBox.warning(self, "Input Error", f"An instruction named '{new_name}' already exists.")
             return
        if new_name == "Default":
             QMessageBox.warning(self, "Input Error", "Cannot use the reserved name 'Default'.")
             return

        # Add to data immediately with empty text
        self.instructions_data[new_name] = ""
        self.add_instruction_widget(new_name, "") # Add UI widget
        self.new_name_input.clear()
        self._dirty = True
        # Scroll to bottom? Optional.
        QTimer.singleShot(0, self.scroll_area.verticalScrollBar().setValue, self.scroll_area.verticalScrollBar().maximum())


    @Slot(str, str)
    def handle_instruction_update(self, name, new_text):
        """Update the data dictionary when an instruction's text is updated."""
        if name in self.instructions_data:
            if self.instructions_data[name] != new_text:
                self.instructions_data[name] = new_text
                self._dirty = True
                print(f"Instruction '{name}' updated in memory.")
                # Maybe provide visual feedback? e.g., status bar message
            else:
                 print(f"Instruction '{name}' text unchanged.")
        else:
             print(f"Warning: Tried to update non-existent instruction '{name}'")


    @Slot(str)
    def handle_instruction_delete_request(self, name):
        """Handle delete request, confirm, then remove data and widget."""
        if name == "Default": # Should be disabled, but double-check
            QMessageBox.warning(self, "Delete Error", "Cannot delete the 'Default' instruction.")
            return

        reply = QMessageBox.question(self, "Confirm Delete",
                                     f"Are you sure you want to delete the instruction named '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            if name in self.instructions_data:
                del self.instructions_data[name]
                self._dirty = True
                print(f"Instruction '{name}' deleted from data.")
                # Find and remove the corresponding widget
                for i in range(self.scroll_layout.count()):
                    item = self.scroll_layout.itemAt(i)
                    widget = item.widget()
                    # Check if it's our InstructionEditorWidget and matches name
                    if isinstance(widget, InstructionEditorWidget) and widget.instruction_name == name:
                        widget.deleteLater() # Remove widget from layout and schedule deletion
                        self.scroll_layout.removeItem(item) # Remove item from layout
                        break
            else:
                 print(f"Warning: Tried to delete instruction '{name}' but it wasn't found in data.")

    def reject(self):
        """Handle dialog close."""
        if self._dirty:
             # Optional: Ask user if they want to save changes on close if dirty?
             # Or just rely on MainWindow saving mechanism.
             self.instructions_changed.emit() # Signal main window even on close if dirty
        super().reject()

    # Optionally override accept() if you want the Close button to save too
    # def accept(self):
    #     if self._dirty:
    #         self.instructions_changed.emit()
    #     super().accept()