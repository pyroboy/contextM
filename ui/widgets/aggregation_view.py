from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLabel, QPushButton, QStyle
)
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont
import pyperclip
import sys

class AggregationView(QWidget):
    """A widget to display aggregated content, token count, and a copy button."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._system_prompt = ""
        self._aggregated_text = ""
        self._aggregated_tokens = 0
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Sets up the widgets within this panel."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 5)

        self.token_info_label = QLabel("Total Tokens: 0")
        self.token_info_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.token_info_label)

        self.aggregation_output = QTextEdit()
        self.aggregation_output.setReadOnly(True)
        self.aggregation_output.setPlaceholderText("Select files/folders from the tree to aggregate their content here...")
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamily("Courier New" if sys.platform == 'win32' else "Monaco" if sys.platform == 'darwin' else "monospace")
        self.aggregation_output.setFont(font)
        self.aggregation_output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.aggregation_output)

        self.copy_button = QPushButton("Copy Aggregated Content to Clipboard")
        self.copy_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        layout.addWidget(self.copy_button)

    def _connect_signals(self):
        """Connects the copy button's clicked signal."""
        self.copy_button.clicked.connect(self._copy_to_clipboard)

    @Slot()
    def _copy_to_clipboard(self):
        """Copies the content of the aggregation output to the clipboard."""
        content = self.aggregation_output.toPlainText()
        try:
            pyperclip.copy(content)
            print("Content copied to clipboard.")
            # Optionally, provide feedback to the user, e.g., in a status bar
        except pyperclip.PyperclipException as e:
            print(f"Error copying to clipboard: {e}")
            # Optionally, show a message box to the user

    @Slot(str)
    def set_system_prompt(self, prompt):
        """Sets the system prompt and updates the display."""
        self._system_prompt = prompt
        self._update_display()

    def set_content(self, text, token_count):
        """Updates the display with new text and token count."""
        self._aggregated_text = text
        self._aggregated_tokens = token_count
        self._update_display()

    def _update_display(self):
        """Constructs the full output from prompt and content and updates the view."""
        full_text = self._aggregated_text
        if self._system_prompt:
            full_text = f"--- System Prompt ---\n{self._system_prompt}\n\n--- File Tree ---\n{self._aggregated_text}"
        
        # This is a simplification; a real implementation would need to recalculate total tokens.
        # For now, we'll just show the aggregated file tokens.
        self.aggregation_output.setPlainText(full_text)
        self.token_info_label.setText(f"File Tokens: {self._aggregated_tokens:,}")

    def get_content(self):
        """Returns the current aggregated text."""
        return self.aggregation_output.toPlainText()
