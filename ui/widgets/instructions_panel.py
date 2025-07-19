from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QTextEdit, QSizePolicy
)
from PySide6.QtCore import Signal, Slot

class InstructionsPanel(QWidget):
    """A widget for managing and displaying instruction templates."""
    
    # Signals
    instructions_changed = Signal(str)
    template_selected = Signal(str) # Emits the name of the template
    manage_templates_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Sets up the widgets within this panel."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 0)

        # Top bar with dropdown and manage button
        top_bar_layout = QHBoxLayout()
        top_bar_layout.addWidget(QLabel("Instruction Template:"))
        
        self.template_dropdown = QComboBox()
        self.template_dropdown.setToolTip("Select a saved instruction template")
        self.template_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        top_bar_layout.addWidget(self.template_dropdown, 1)
        
        self.manage_button = QPushButton("Manage...")
        self.manage_button.setToolTip("Manage custom instruction templates")
        top_bar_layout.addWidget(self.manage_button)
        
        main_layout.addLayout(top_bar_layout)

        # Main text edit area
        self.instructions_input = QTextEdit()
        self.instructions_input.setPlaceholderText("Add custom instructions or notes here (saved per workspace)... Select a template above to load.")
        self.instructions_input.setMinimumHeight(80)
        self.instructions_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.instructions_input, 1)

    def _connect_signals(self):
        """Connects internal signals to emit the panel's public signals."""
        self.manage_button.clicked.connect(self.manage_templates_requested)
        self.template_dropdown.currentIndexChanged.connect(self._on_template_selected)
        self.instructions_input.textChanged.connect(self._on_text_changed)

    @Slot()
    def _on_text_changed(self):
        """Emits the current text when it changes."""
        self.instructions_changed.emit(self.instructions_input.toPlainText())

    @Slot(int)
    def _on_template_selected(self, index):
        """Emits the selected template name."""
        template_name = self.template_dropdown.itemData(index)
        if template_name:
            self.template_selected.emit(template_name)

    def set_text(self, text):
        """Programmatically sets the text in the instructions input."""
        self.instructions_input.blockSignals(True)
        self.instructions_input.setPlainText(text)
        self.instructions_input.blockSignals(False)

    def get_text(self):
        """Returns the current text from the instructions input."""
        return self.instructions_input.toPlainText()

    def populate_templates(self, templates_dict):
        """Populates the template dropdown from a dictionary."""
        self.template_dropdown.blockSignals(True)
        self.template_dropdown.clear()
        self.template_dropdown.addItem("- Select Template -", "")

        if "Default" in templates_dict:
            self.template_dropdown.addItem("Default", "Default")

        other_names = sorted([name for name in templates_dict if name != "Default"])
        for name in other_names:
            self.template_dropdown.addItem(name, name)
            
        self.template_dropdown.blockSignals(False)

    def get_instructions(self):
        return self.instructions_input.toPlainText()

    def set_instructions(self, text):
        self.instructions_input.setPlainText(text)

    def set_instructions(self, text):
        self.instructions_input.setPlainText(text)

    def update_templates(self, templates_dict):
        self.populate_templates(templates_dict)
