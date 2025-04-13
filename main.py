# --- File: main.py (Updated for Refresh and Change Detection) ---
import sys
import os
import pathlib
from pathlib import Path # Add this import
import time
import traceback
import json

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QTextEdit, QTreeWidget, QTreeWidgetItem, QSplitter, QLabel,
    QMessageBox, QStyle, QHeaderView, QTreeWidgetItemIterator, QDialog, QDialogButtonBox,
    QCheckBox, QLineEdit, QFormLayout, QComboBox, QSizePolicy # <-- Import QComboBox and QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QFont, QIcon, QColor

import pyperclip

# --- Import extracted components ---
from helpers import is_text_file, calculate_tokens, TIKTOKEN_AVAILABLE
from scan_config_dialog import ScanConfigDialog, DEFAULT_IGNORE_FOLDERS
from directory_scanner import DirectoryScanner
from workspace_dialog import WorkspaceManagerDialog
# --- Import new dialog ---
from custom_instructions_dialog import CustomInstructionsDialog

# --- Configuration ---
MAX_FILE_SIZE_KB = 200
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_KB * 1024
READ_CHUNK_SIZE = 1024 * 1024
WORKSPACE_FILE = "workspaces.json"
CUSTOM_INSTRUCTIONS_FILE = "custom_instructions.json" # <-- New config file


# --- Main Application Window ---
class MainWindow(QMainWindow):
    PATH_DATA_ROLE = Qt.ItemDataRole.UserRole + 0
    TOKEN_COUNT_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Code Aggregation Tool")
        self.setGeometry(100, 100, 1200, 800)

        # --- Workspace Attributes ---
        self.workspaces = {}
        self.current_workspace_name = None
        self._pending_tree_restore_paths = set() # Store as set of normalized paths

        # --- Custom Instructions Attributes ---
        self.custom_instructions = {} # Holds loaded instruction templates

        # --- Other Attributes ---
        self.current_folder_path = None
        self.current_scan_settings = None
        self.directory_scanner = None
        self.tree_items = {}
        self.folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        self.error_color = QColor("red")
        self._is_programmatically_checking = False
        self._current_scan_discovered_files = set() # Keep track of files found in the current scan

        # --- Load Data ---
        self._load_workspaces()
        self._load_custom_instructions() # Load instructions

        # --- Setup UI ---
        self._setup_ui() # Includes dropdown now
        self._populate_instructions_dropdown() # Populate dropdown after UI setup
        self._connect_signals()

        # --- Load last active workspace ---
        last_active = self.workspaces.get("last_active_workspace", "Default")
        if last_active not in self.workspaces:
            last_active = "Default"
            if "Default" not in self.workspaces:
                self.workspaces["Default"] = {"folder_path": None, "scan_settings": None, "instructions": "", "checked_paths": []}
                self._save_workspaces()

        self._switch_workspace(last_active, initial_load=True)


    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Top Controls
        top_controls_layout = QHBoxLayout()
        # (Workspace Button/Label, Folder Button/Label remain the same)
        self.manage_workspaces_button = QPushButton("Workspaces")
        self.manage_workspaces_button.setToolTip("Manage Workspaces")
        self.workspace_label = QLabel("Workspace: None")
        self.select_folder_button = QPushButton("Select Project Folder...")
        self.select_folder_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))

        # --- NEW: Refresh Button ---
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.setToolTip("Refresh current folder view")
        self.refresh_button.setEnabled(False) # Enabled when folder is selected
        # --- END NEW ---

        self.path_display_label = QLabel("No folder selected.")
        self.path_display_label.setWordWrap(True)
        top_controls_layout.addWidget(self.manage_workspaces_button)
        top_controls_layout.addWidget(self.workspace_label)
        top_controls_layout.addSpacing(20)
        top_controls_layout.addWidget(self.select_folder_button)
        top_controls_layout.addWidget(self.refresh_button) # Add refresh button
        top_controls_layout.addWidget(self.path_display_label, 1)

        # Splitter and Tree
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        # (Tree setup remains the same)
        tree_container = QWidget()
        tree_layout = QVBoxLayout(tree_container)
        tree_layout.setContentsMargins(0,0,0,0)
        self.loading_label = QLabel("Scanning folder...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setVisible(False)
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Status / Tokens"])
        self.tree_widget.setColumnCount(2)
        self.tree_widget.header().setStretchLastSection(False)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.setAlternatingRowColors(True)
        tree_layout.addWidget(self.loading_label)
        tree_layout.addWidget(self.tree_widget)
        self.splitter.addWidget(tree_container)

        # Right Side (Instructions + Aggregation Output)
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0,0,0,0)
        self.splitter_right = QSplitter(Qt.Orientation.Vertical)

        # --- Top Part: Instructions Area ---
        instr_container = QWidget()
        instr_layout_main = QVBoxLayout(instr_container) # Main layout for this section
        instr_layout_main.setContentsMargins(5, 5, 5, 0)

        # --- Dropdown and Manage Button ---
        instr_top_bar_layout = QHBoxLayout()
        instr_top_bar_layout.addWidget(QLabel("Instruction Template:")) # Label for dropdown
        self.instruction_template_dropdown = QComboBox()
        self.instruction_template_dropdown.setToolTip("Select a saved instruction template")
        self.instruction_template_dropdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed) # Expand horizontally
        instr_top_bar_layout.addWidget(self.instruction_template_dropdown, 1) # Dropdown takes space
        self.manage_instructions_button = QPushButton("Manage...")
        self.manage_instructions_button.setToolTip("Manage custom instruction templates")
        instr_top_bar_layout.addWidget(self.manage_instructions_button)
        # Add this bar to the instructions container layout
        instr_layout_main.addLayout(instr_top_bar_layout)

        # Existing Instructions Input Text Box
        self.instructions_input = QTextEdit()
        self.instructions_input.setPlaceholderText("Add custom instructions or notes here (saved per workspace)... Select a template above to load.") # Modified placeholder
        # Set minimum height, but allow vertical expansion
        self.instructions_input.setMinimumHeight(80)
        self.instructions_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Add text box below the dropdown bar
        instr_layout_main.addWidget(self.instructions_input, 1) # Text box expands vertically

        self.splitter_right.addWidget(instr_container) # Add the whole container to splitter

        # Bottom Part: Aggregation Output (remains the same)
        agg_container = QWidget()
        agg_layout = QVBoxLayout(agg_container)
        agg_layout.setContentsMargins(5, 0, 5, 5)
        self.token_info_label = QLabel("Total Tokens: 0")
        self.token_info_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        agg_layout.addWidget(self.token_info_label)
        self.aggregation_output = QTextEdit()
        self.aggregation_output.setReadOnly(True)
        self.aggregation_output.setPlaceholderText("Select files/folders from the tree to aggregate their content here...")
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamily("Courier New" if sys.platform == 'win32' else "Monaco" if sys.platform == 'darwin' else "monospace")
        self.aggregation_output.setFont(font)
        self.aggregation_output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        agg_layout.addWidget(self.aggregation_output)
        self.splitter_right.addWidget(agg_container)

        # Adjust splitter sizes (might need tweaking)
        self.splitter_right.setStretchFactor(0, 0) # Instructions area less stretchy
        self.splitter_right.setStretchFactor(1, 1) # Output area more stretchy
        self.splitter_right.setSizes([150, 650]) # Example sizes

        right_layout.addWidget(self.splitter_right)

        # Copy Button (remains the same)
        self.copy_button = QPushButton("Copy Aggregated Content to Clipboard")
        self.copy_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        right_layout.addWidget(self.copy_button)

        self.splitter.addWidget(right_container)
        self.splitter.setSizes([450, 750])
        main_layout.addLayout(top_controls_layout)
        main_layout.addWidget(self.splitter, 1)
        self.statusBar().showMessage("Ready.")


    def _connect_signals(self):
        self.select_folder_button.clicked.connect(self.open_folder_dialog)
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        self.tree_widget.itemChanged.connect(self.handle_item_changed)
        self.manage_workspaces_button.clicked.connect(self._open_workspace_dialog)
        # --- New Connections ---
        self.refresh_button.clicked.connect(self._refresh_current_folder) # Connect refresh button
        self.manage_instructions_button.clicked.connect(self._open_custom_instructions_dialog)
        self.instruction_template_dropdown.currentIndexChanged.connect(self._apply_instruction_template)
        # --- End New Connections ---


    # --- Custom Instructions Methods (Unchanged) ---

    def _load_custom_instructions(self):
        """Loads custom instruction templates from JSON file."""
        try:
            if os.path.exists(CUSTOM_INSTRUCTIONS_FILE):
                with open(CUSTOM_INSTRUCTIONS_FILE, 'r', encoding='utf-8') as f:
                    self.custom_instructions = json.load(f)
                print(f"Custom instructions loaded from {CUSTOM_INSTRUCTIONS_FILE}")
            else:
                print("Custom instructions file not found. Creating default.")
                self.custom_instructions = {
                    "Default": "Instructions for the output format:\nOutput code without descriptions, unless it is important.\nMinimize prose, comments and empty lines."
                }
                self._save_custom_instructions() # Save the default one
        except (json.JSONDecodeError, IOError, TypeError) as e:
            print(f"Error loading custom instructions: {e}. Using default.")
            QMessageBox.warning(self, "Instructions Load Error", f"Could not load custom instructions.\nError: {e}\nUsing default.")
            self.custom_instructions = { "Default": "Default instructions." }


    def _save_custom_instructions(self):
        """Saves custom instruction templates to JSON file."""
        try:
            with open(CUSTOM_INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.custom_instructions, f, indent=4)
            # print("Custom instructions saved.")
        except (IOError, TypeError) as e:
            print(f"Error saving custom instructions: {e}")
            QMessageBox.critical(self, "Instructions Save Error", f"Could not save custom instructions.\nError: {e}")


    def _populate_instructions_dropdown(self):
        """Populates the instruction template dropdown."""
        self.instruction_template_dropdown.blockSignals(True) # Prevent triggering apply while populating
        self.instruction_template_dropdown.clear()
        # Add a placeholder item first
        self.instruction_template_dropdown.addItem("- Select Template -", "") # User data is empty string

        # Add Default first if it exists
        if "Default" in self.custom_instructions:
            self.instruction_template_dropdown.addItem("Default", "Default") # User data is the key "Default"

        # Add others sorted
        other_names = sorted([name for name in self.custom_instructions if name != "Default"])
        for name in other_names:
            self.instruction_template_dropdown.addItem(name, name) # User data is the key (name)

        self.instruction_template_dropdown.blockSignals(False)


    def _calculate_selected_tokens_for_folder(self, folder_item):
        """Recursively calculates the total token count for CHECKED descendant files."""
        selected_tokens = 0
        for i in range(folder_item.childCount()):
            child_item = folder_item.child(i)
            child_path = child_item.data(0, self.PATH_DATA_ROLE)

            # Skip items without path data or disabled items
            if not child_path or not (child_item.flags() & Qt.ItemFlag.ItemIsEnabled):
                continue
            is_child_folder = child_item.childCount() > 0


            if is_child_folder:
                # If it's a sub-folder, recurse and add its selected total
                # We don't care if the sub-folder *itself* is checked, only its contents
                selected_tokens += self._calculate_selected_tokens_for_folder(child_item)
            else:
                # If it's a file, check if it's checked
                if child_item.checkState(0) == Qt.CheckState.Checked:
                    file_tokens = child_item.data(0, self.TOKEN_COUNT_ROLE) or 0
                    selected_tokens += file_tokens
        return selected_tokens


# (Inside MainWindow class)
    def _update_selected_folder_token_display(self):
        """
        Updates the display text (col 1) for all folders showing
        TOTAL / SELECTED tokens based on currently selected children.
        """
        if not TIKTOKEN_AVAILABLE: return # Skip if tokens can't be calculated

        print("Updating folder token display based on selection...")
        self.tree_widget.setUpdatesEnabled(False) # Performance improvement
        try:
            iterator = QTreeWidgetItemIterator(self.tree_widget, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                path_str = item.data(0, self.PATH_DATA_ROLE)

                if not path_str or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                    iterator += 1
                    continue

                # Determine if it's a folder
                is_folder = item.childCount() > 0 # Basic check
                # Add more robust checks if needed

                if is_folder:
                    # --- Calculate SELECTED tokens ---
                    selected_token_sum = self._calculate_selected_tokens_for_folder(item)

                    # --- Retrieve STORED TOTAL tokens ---
                    total_tokens = item.data(0, self.TOKEN_COUNT_ROLE) or 0 # Get total stored previously

                    # --- Update the display text and tooltip (TOTAL / SELECTED) ---
                    display_text = f"{total_tokens:,} / {selected_token_sum:,} tokens"
                    tooltip_text = f"Total: {total_tokens:,} / Selected: {selected_token_sum:,} tokens"

                    item.setText(1, display_text)
                    item.setToolTip(1, tooltip_text)
                    # --- End Update ---

                iterator += 1
        finally:
            self.tree_widget.setUpdatesEnabled(True)
            # Optionally resize column again if text length changes significantly
            # self.tree_widget.resizeColumnToContents(1) # Might cause flickering if called too often
        print("Folder selected token display updated.")
    @Slot()
    def _open_custom_instructions_dialog(self):
        """Opens the dialog to manage custom instructions."""
        dialog = CustomInstructionsDialog(self.custom_instructions, self)
        dialog.instructions_changed.connect(self._handle_instructions_changed) # Connect signal

        # No exec() needed if it's modeless, but modal is simpler here
        dialog.exec() # Show modally

    @Slot()
    def _handle_instructions_changed(self):
        """Called when the instruction dialog signals changes."""
        print("Custom instructions were changed in the dialog.")
        self._save_custom_instructions() # Save the updated data
        self._populate_instructions_dropdown() # Refresh the dropdown

    @Slot(int)
    def _apply_instruction_template(self, index):
        """Applies the selected instruction template to the main text box."""
        template_name = self.instruction_template_dropdown.itemData(index) # Get name from user data
        if template_name and template_name in self.custom_instructions:
            print(f"Applying instruction template: {template_name}")
            instruction_text = self.custom_instructions[template_name]
            # Update the main instructions box
            # This WILL be saved with the workspace state later
            self.instructions_input.setPlainText(instruction_text)
        elif index == 0: # Handle the placeholder "- Select Template -"
             print("Placeholder selected, no template applied.")
             # self.instructions_input.clear() # Uncomment to clear on placeholder selection


    # --- Workspace Methods (Modified loading/switching) ---
    def _load_workspaces(self):
        # (Load logic remains mostly the same, but ensure checked_paths are loaded correctly)
        try:
            if os.path.exists(WORKSPACE_FILE):
                with open(WORKSPACE_FILE, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    self.workspaces = {}
                    for ws_name, ws_data in loaded_data.items():
                        if ws_name == "last_active_workspace":
                            self.workspaces[ws_name] = ws_data
                            continue
                        # Ensure checked_paths is loaded as a list, conversion to set happens on switch
                        checked_paths_list = ws_data.get("checked_paths", [])
                        validated_data = {
                            "folder_path": ws_data.get("folder_path"),
                            "scan_settings": ws_data.get("scan_settings"),
                            "instructions": ws_data.get("instructions", ""),
                            "checked_paths": checked_paths_list # Store as list from file
                        }
                        if validated_data["scan_settings"] and "ignore_folders" in validated_data["scan_settings"]:
                            if isinstance(validated_data["scan_settings"]["ignore_folders"], list):
                                validated_data["scan_settings"]["ignore_folders"] = set(validated_data["scan_settings"]["ignore_folders"])
                            elif validated_data["scan_settings"]["ignore_folders"] is None:
                                validated_data["scan_settings"]["ignore_folders"] = set(DEFAULT_IGNORE_FOLDERS)
                        self.workspaces[ws_name] = validated_data
                print(f"Workspaces loaded and validated from {WORKSPACE_FILE}")
            else: raise FileNotFoundError
        except (json.JSONDecodeError, IOError, TypeError, FileNotFoundError) as e:
            if not isinstance(e, FileNotFoundError): print(f"Error loading workspaces: {e}. Resetting to default.")
            else: print("Workspace file not found. Creating default.")
            self.workspaces = {"Default": {"folder_path": None, "scan_settings": None, "instructions": "", "checked_paths": []},"last_active_workspace": "Default"}
            self._save_workspaces()

    def _save_workspaces(self):
        # (Save logic remains mostly the same, ensures checked_paths are saved as list)
        workspaces_to_save = {}
        for ws_name, ws_data in self.workspaces.items():
            if ws_name == "last_active_workspace":
                workspaces_to_save[ws_name] = ws_data; continue
            new_ws_data = ws_data.copy()
            # Convert checked_paths set back to list for JSON serialization
            if "checked_paths" in new_ws_data and isinstance(new_ws_data["checked_paths"], set):
                 new_ws_data["checked_paths"] = sorted(list(new_ws_data["checked_paths"]))
            elif "checked_paths" not in new_ws_data:
                 new_ws_data["checked_paths"] = [] # Ensure it exists as an empty list

            if "scan_settings" in new_ws_data and new_ws_data["scan_settings"]:
                new_ws_data["scan_settings"] = new_ws_data["scan_settings"].copy()
                if "ignore_folders" in new_ws_data["scan_settings"] and isinstance(new_ws_data["scan_settings"]["ignore_folders"], set):
                    new_ws_data["scan_settings"]["ignore_folders"] = sorted(list(new_ws_data["scan_settings"]["ignore_folders"]))
            workspaces_to_save[ws_name] = new_ws_data
        try:
            with open(WORKSPACE_FILE, 'w', encoding='utf-8') as f: json.dump(workspaces_to_save, f, indent=4)
        except (IOError, TypeError) as e: print(f"Error saving workspaces: {e}"); QMessageBox.critical(self, "Workspace Save Error", f"Could not save workspace data.\nError: {e}")

    @Slot()
    def _open_workspace_dialog(self):
        # (Unchanged)
        self._save_current_workspace_state()
        dialog = WorkspaceManagerDialog(self.workspaces, self.current_workspace_name, self)
        dialog.workspace_added.connect(self._handle_workspace_added)
        dialog.workspace_deleted.connect(self._handle_workspace_deleted)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_ws = dialog.get_selected_workspace()
            if selected_ws and selected_ws != self.current_workspace_name:
                print(f"Switching to selected workspace: {selected_ws}")
                self._save_current_workspace_state()
                self._switch_workspace(selected_ws)
            elif selected_ws: print(f"Workspace '{selected_ws}' re-selected (no switch).")
        else:
            if self.current_workspace_name not in self.workspaces:
                print(f"Current workspace '{self.current_workspace_name}' was deleted. Switching to Default.")
                self._switch_workspace("Default")
            else: print("Workspace dialog closed without selection change.")

    @Slot(str)
    def _handle_workspace_added(self, new_ws_name):
        # (Unchanged)
        print(f"Handling addition of workspace: {new_ws_name}")
        current_instructions = self.instructions_input.toPlainText()
        current_checked_paths = self._get_checked_paths() # Get current checked paths as list
        current_folder = self.current_folder_path
        current_settings = self.current_scan_settings
        self.workspaces[new_ws_name] = {"folder_path": current_folder, "scan_settings": current_settings,"instructions": current_instructions,"checked_paths": current_checked_paths} # Store as list
        self._save_workspaces()
        print(f"Switching to newly added workspace: {new_ws_name}")
        self._switch_workspace(new_ws_name)

    @Slot(str)
    def _handle_workspace_deleted(self, deleted_ws_name):
        # (Unchanged)
        print(f"Handling deletion of workspace: {deleted_ws_name}")
        if deleted_ws_name in self.workspaces:
            del self.workspaces[deleted_ws_name]
            self._save_workspaces()
        else: print(f"Warning: Tried to delete '{deleted_ws_name}' but it was not found.")

    def _switch_workspace(self, workspace_name, initial_load=False):
        # (Modified to handle checked paths as set internally)
        if workspace_name not in self.workspaces:
            print(f"Error: Switch to non-existent workspace '{workspace_name}'. Falling back to Default.")
            workspace_name = "Default"
            if workspace_name not in self.workspaces: self.workspaces["Default"] = {"folder_path": None, "scan_settings": None, "instructions": "", "checked_paths": []}
        if not initial_load and self.current_workspace_name:
             if self.current_workspace_name in self.workspaces: print(f"Saving state for previous workspace: {self.current_workspace_name}"); self._save_current_workspace_state()
             else: print(f"Previous workspace {self.current_workspace_name} no longer exists, cannot save.")
        print(f"Loading workspace: {workspace_name}")
        self.current_workspace_name = workspace_name
        ws_data = self.workspaces[workspace_name]
        self.workspace_label.setText(f"Workspace: {workspace_name}")
        folder_path = ws_data.get("folder_path")
        scan_settings = ws_data.get("scan_settings")
        instructions = ws_data.get("instructions", "")

        # Load saved paths and convert to a set of normalized paths for internal use
        saved_paths_list = ws_data.get("checked_paths", [])
        self._pending_tree_restore_paths = {os.path.normpath(p) for p in saved_paths_list}

        self.current_folder_path = folder_path
        self.current_scan_settings = scan_settings
        self.refresh_button.setEnabled(bool(folder_path)) # Enable refresh if folder exists
        self.instructions_input.blockSignals(True); self.instructions_input.setPlainText(instructions); self.instructions_input.blockSignals(False)
        if folder_path: self.path_display_label.setText(f"Selected: {folder_path}")
        else: self.path_display_label.setText("No folder selected for this workspace.")
        self.tree_items.clear(); self.tree_widget.clear(); self.aggregation_output.clear()
        self.token_info_label.setText("Total Tokens: 0"); self.loading_label.setVisible(False); self.tree_widget.setVisible(True)
        if folder_path:
            if os.path.isdir(folder_path):
                if not scan_settings: scan_settings = {'include_subfolders': True, 'ignore_folders': set(DEFAULT_IGNORE_FOLDERS)}; ws_data["scan_settings"] = scan_settings
                print(f"Triggering scan for workspace folder: {folder_path}"); self.statusBar().showMessage(f"Scanning workspace folder: {folder_path}...")
                self._start_scan(folder_path, scan_settings) # Use helper to start scan
            else: self.statusBar().showMessage(f"Folder '{folder_path}' for workspace '{workspace_name}' not found.", 5000); self.path_display_label.setText(f"Folder NOT FOUND: {folder_path}"); self._pending_tree_restore_paths = set(); self.refresh_button.setEnabled(False)
        else: self.statusBar().showMessage(f"Workspace '{workspace_name}' loaded. Select a folder to begin.", 3000); self._pending_tree_restore_paths = set(); self.refresh_button.setEnabled(False)
        self.workspaces["last_active_workspace"] = workspace_name

    def _get_checked_paths(self, return_set=False):
        """Gets currently checked paths from the tree. Returns list by default, or set if specified."""
        checked_items = set()
        iterator = QTreeWidgetItemIterator(self.tree_widget, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value(); path_str = item.data(0, self.PATH_DATA_ROLE)
            if path_str: checked_items.add(os.path.normpath(path_str))
            iterator += 1
        if return_set:
             return checked_items
        else:
             return sorted(list(checked_items)) # Return sorted list for consistent saving

    def _restore_tree_selection(self, paths_to_check_set):
        """Restores tree selection based on a SET of normalized paths."""
        if not paths_to_check_set: print("No tree selection to restore."); return
        print(f"Attempting to restore tree selection for {len(paths_to_check_set)} items...")
        self._is_programmatically_checking = True
        try:
            items_restored = 0
            # --- (Existing loop to setCheckState) ---
            for item_path, item in self.tree_items.items():
                if not item or not item.treeWidget(): continue
                if item_path in paths_to_check_set and (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                    if item.checkState(0) != Qt.CheckState.Checked:
                        item.setCheckState(0, Qt.CheckState.Checked)
                        # Uncheck items not in the set (optional, depends on desired behavior)
                    # else:
                    #    if item.checkState(0) != Qt.CheckState.Unchecked:
                    #        item.setCheckState(0, Qt.CheckState.Unchecked)
                    items_restored += 1 # Count might need adjustment based on uncheck logic
            print(f"Restored check state affecting {items_restored} items.")

        finally:
            self._is_programmatically_checking = False

        # Update aggregation output and main token count first
        self.update_aggregation_and_tokens()

        # --- NEW: Update folder display based on new selection ---
        self._update_selected_folder_token_display()
        # --- END NEW ---


    def _save_current_workspace_state(self):
        # (Modified to get paths as list)
        if self.current_workspace_name and self.current_workspace_name in self.workspaces:
            print(f"Saving instructions and tree state for workspace: {self.current_workspace_name}")
            current_instructions = self.instructions_input.toPlainText()
            current_checked_paths_list = self._get_checked_paths(return_set=False) # Get list
            self.workspaces[self.current_workspace_name]["instructions"] = current_instructions
            self.workspaces[self.current_workspace_name]["checked_paths"] = current_checked_paths_list # Save list
        else: print("Warning: Cannot save state, no valid current workspace.")


    # --- NEW: Refresh Folder Method ---
    @Slot()
    def _refresh_current_folder(self):
        """Initiates a re-scan of the current folder."""
        if not self.current_folder_path or not self.current_scan_settings:
             QMessageBox.warning(self, "Refresh Error", "No folder or scan settings are currently active.")
             return
        if self.directory_scanner and self.directory_scanner.isRunning():
             QMessageBox.information(self, "Scan in Progress", "A folder scan is already in progress.")
             return

        print(f"Refreshing folder: {self.current_folder_path}")
        self.statusBar().showMessage(f"Refreshing folder: {self.current_folder_path}...")
        # Save current selection before clearing the tree for refresh
        self._pending_tree_restore_paths = self._get_checked_paths(return_set=True) # Save as set
        # Clear tree and start scan
        self.tree_items.clear()
        self.tree_widget.clear()
        self.aggregation_output.clear()
        self._start_scan(self.current_folder_path, self.current_scan_settings)

    # --- Helper to start scan (reduces code duplication) ---
    def _start_scan(self, folder_path, scan_settings):
        """Creates and starts the directory scanner thread."""
        if self.directory_scanner and self.directory_scanner.isRunning():
            print("Warning: Scan already running, cannot start another.")
            return

        self.directory_scanner = DirectoryScanner(folder_path, scan_settings)
        self.directory_scanner.items_discovered.connect(self.add_tree_items_batch)
        self.directory_scanner.scan_started.connect(self.handle_scan_started)
        self.directory_scanner.scan_finished.connect(self.handle_scan_finished)
        self.directory_scanner.error_signal.connect(self.handle_scan_error)
        self.directory_scanner.progress_update.connect(self.handle_progress_update)
        self.directory_scanner.start()



    def _create_or_update_tree_item(self, path_str, is_directory, is_valid, reason, token_count=0):
        """Creates or updates a single item in the QTreeWidget."""
        try:
            # --- Path normalization and finding parent ---
            normalized_path_str = os.path.normpath(path_str)
            path_obj = pathlib.Path(normalized_path_str)
            parent_path_str = os.path.normpath(str(path_obj.parent))
            root_path_norm = os.path.normpath(self.current_folder_path) if self.current_folder_path else None

            if root_path_norm and normalized_path_str == root_path_norm:
                parent_widget = self.tree_widget # Root item's parent is the tree itself
            else:
                parent_widget = self.tree_items.get(parent_path_str, self.tree_widget.invisibleRootItem())
                # Ensure parent_widget is valid if found in dict
                if not isinstance(parent_widget, (QTreeWidget, QTreeWidgetItem)):
                     parent_widget = self.tree_widget.invisibleRootItem()

            # --- Find or create item ---
            item = self.tree_items.get(normalized_path_str)
            is_new_item = False
            if item is None:
                is_new_item = True
                actual_parent = parent_widget # Use the located parent
                item = QTreeWidgetItem(actual_parent)
                self.tree_items[normalized_path_str] = item # Add to dictionary
                item.setText(0, path_obj.name)
                item.setData(0, self.PATH_DATA_ROLE, normalized_path_str) # Store normalized path

            # --- Set common properties ---
            item.setIcon(0, self.folder_icon if is_directory else self.file_icon)
            item.setToolTip(0, normalized_path_str)
            item.setForeground(1, self.palette().color(self.foregroundRole())) # Reset color

            # --- Store Token Count (Crucial: Store 0 for folders initially) ---
            # Store token count in data role for files, 0 for folders/invalid
            item.setData(0, self.TOKEN_COUNT_ROLE, token_count if is_valid and not is_directory else 0)

            # --- Set Status, Tooltip, Flags based on validity ---
            if is_valid:
                # Initial Status Text (Column 1) - Folders just show "Folder" for now
                status_text = "Folder" if is_directory else f"{token_count:,} tokens" if TIKTOKEN_AVAILABLE else ""
                item.setText(1, status_text)

                # Tooltip for Status column (Column 1) - Folders just show "Folder" for now
                tooltip_text = "Folder" if is_directory else f"Estimated tokens: {token_count:,}" if TIKTOKEN_AVAILABLE else "File"
                item.setToolTip(1, tooltip_text)

                # Set flags for valid items
                flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
                item.setFlags(flags)
                # Ensure check state is initially Unchecked if new or previously disabled
                if is_new_item or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setDisabled(False)
            else:
                # Handle invalid/skipped items
                item.setText(1, reason)
                flags = Qt.ItemFlag.ItemIsSelectable # Not enabled, not checkable
                item.setFlags(flags)
                item.setCheckState(0, Qt.CheckState.Unchecked)
                item.setDisabled(True)
                item.setToolTip(1, f"Skipped: {reason}")
                # Set error color if applicable
                if "permission denied" in reason.lower() or "error" in reason.lower():
                    item.setForeground(1, self.error_color)

        except Exception as e:
            print(f"Error in _create_or_update_tree_item for ('{path_str}'): {e}")
            traceback.print_exc()

    # --- Other Methods (Tree/Scan/Aggregation/Copy/Close - Modified Scan Handling) ---
    def _calculate_folder_tokens(self, folder_item):
            """Recursively calculates the total token count for a folder item."""
            total_tokens = 0
            for i in range(folder_item.childCount()):
                child_item = folder_item.child(i)
                child_path = child_item.data(0, self.PATH_DATA_ROLE)
                if not child_path: continue # Skip if no path data

                # Check if child is a folder using stored item data (more reliable than icon)
                # Note: This assumes tree_items is populated correctly.
                child_node_in_dict = self.tree_items.get(child_path)
                # A simple check if it has children might suffice, or use a stored is_dir flag if available
                # Using icon check as fallback if needed (but can be unreliable if icons missing/wrong)
                is_child_folder = False
                if child_node_in_dict:
                    # Check if it has children OR check its icon if necessary
                    if child_node_in_dict.childCount() > 0:
                        is_child_folder = True
                    # Fallback icon check (use carefully)
                    # elif self.folder_icon and callable(getattr(child_node_in_dict.icon(0), 'name', None)):
                    #      is_child_folder = child_node_in_dict.icon(0).name() == self.folder_icon.name()


                if is_child_folder:
                    # If it's a sub-folder, recurse
                    total_tokens += self._calculate_folder_tokens(child_item)
                else:
                    # If it's a file, add its token count (if valid)
                    if child_item.flags() & Qt.ItemFlag.ItemIsEnabled: # Check if valid/enabled
                        file_tokens = child_item.data(0, self.TOKEN_COUNT_ROLE) or 0
                        total_tokens += file_tokens
            return total_tokens
# (Inside MainWindow class)
# (Inside MainWindow class)
    def _update_folder_token_counts(self):
        """
        Iterates through the tree after scan, calculates TOTAL tokens for folders,
        stores it, and sets initial display text.
        """
        if not TIKTOKEN_AVAILABLE: return # Skip if tokens can't be calculated

        print("Calculating and storing total folder token counts...")
        self.tree_widget.setUpdatesEnabled(False) # Improve performance
        try:
            iterator = QTreeWidgetItemIterator(self.tree_widget, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                path_str = item.data(0, self.PATH_DATA_ROLE)
                if not path_str or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                    iterator += 1
                    continue

                # Determine if it's a folder
                is_folder = item.childCount() > 0 # Basic check
                # Add more robust checks if needed

                if is_folder:
                    folder_total_tokens = self._calculate_folder_tokens(item) # Calculate TOTAL

                    # --- STORE the total token count ---
                    item.setData(0, self.TOKEN_COUNT_ROLE, folder_total_tokens)

                    # --- Set INITIAL display text (showing total, selected is 0 initially) ---
                    # Format: TOTAL / SELECTED (where selected is initially 0)
                    display_text = f"{folder_total_tokens:,} / 0 tokens"
                    tooltip_text = f"Total: {folder_total_tokens:,} / Selected: 0 tokens"

                    item.setText(1, display_text)
                    item.setToolTip(1, tooltip_text)

                iterator += 1
        finally:
            self.tree_widget.setUpdatesEnabled(True)
            # Resize happens in handle_scan_finished after this call
            # self.tree_widget.resizeColumnToContents(1)
        print("Total folder token counts calculated and stored.")
        """Iterates through the tree and updates the token count text for folder items."""
        print("Updating folder token counts...")
        self.tree_widget.setUpdatesEnabled(False) # Improve performance
        try:
            iterator = QTreeWidgetItemIterator(self.tree_widget, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                path_str = item.data(0, self.PATH_DATA_ROLE)
                if not path_str:
                    iterator += 1
                    continue

                # Check if it's a folder using stored item data or icon
                item_in_dict = self.tree_items.get(path_str)
                is_folder = False
                if item_in_dict:
                     # Check children or icon
                     if item_in_dict.childCount() > 0: is_folder = True
                     # Fallback icon check (use carefully)
                     # elif self.folder_icon and callable(getattr(item_in_dict.icon(0), 'name', None)):
                     #      is_folder = item_in_dict.icon(0).name() == self.folder_icon.name()


                if is_folder and (item.flags() & Qt.ItemFlag.ItemIsEnabled): # Only update valid folders
                    folder_total_tokens = self._calculate_folder_tokens(item)
                    # Update the text and tooltip in column 1
                    item.setText(1, f"{folder_total_tokens:,} tokens" if TIKTOKEN_AVAILABLE else "Folder")
                    item.setToolTip(1, f"Estimated total tokens in folder: {folder_total_tokens:,}" if TIKTOKEN_AVAILABLE else "Folder")
                    # Optionally store the total in the folder's data role too
                    # item.setData(0, self.TOKEN_COUNT_ROLE, folder_total_tokens)

                iterator += 1
        finally:
            self.tree_widget.setUpdatesEnabled(True)
            self.tree_widget.resizeColumnToContents(1) # Adjust column width after updates
        print("Folder token counts updated.")
    @Slot()
    def open_folder_dialog(self):
        # (Modified to use _start_scan helper)
        if not self.current_workspace_name: QMessageBox.warning(self, "No Workspace", "Please select or create a workspace first."); return
        if self.directory_scanner and self.directory_scanner.isRunning(): QMessageBox.information(self, "Scan in Progress", "A folder scan is already in progress."); return
        start_dir = self.current_folder_path or os.path.expanduser("~"); folder_path = QFileDialog.getExistingDirectory(self, "Select Project Folder for Workspace: " + self.current_workspace_name, start_dir)
        if folder_path:
            normalized_folder_path = os.path.normpath(folder_path); initial_settings = self.current_scan_settings or {'include_subfolders': True, 'ignore_folders': set(DEFAULT_IGNORE_FOLDERS)}; config_dialog = ScanConfigDialog(normalized_folder_path, initial_settings, self)
            if config_dialog.exec() == QDialog.DialogCode.Accepted:
                scan_settings = config_dialog.get_settings(); self.current_folder_path = normalized_folder_path; self.current_scan_settings = scan_settings
                self.refresh_button.setEnabled(True) # Enable refresh button
                if self.current_workspace_name in self.workspaces: self.workspaces[self.current_workspace_name]["folder_path"] = normalized_folder_path; self.workspaces[self.current_workspace_name]["scan_settings"] = scan_settings; self.workspaces[self.current_workspace_name]["checked_paths"] = []; self._save_workspaces()
                else: print(f"Warning: Current workspace '{self.current_workspace_name}' not found while saving folder.")
                self.path_display_label.setText(f"Selected: {self.current_folder_path}"); self.statusBar().showMessage(f"Starting scan: {self.current_folder_path}..."); self.tree_items.clear(); self.tree_widget.clear(); self.aggregation_output.clear(); self._pending_tree_restore_paths = set() # Clear pending paths for new folder
                self._start_scan(self.current_folder_path, self.current_scan_settings) # Use helper
            else: self.statusBar().showMessage("Folder scan configuration cancelled.")
        else: self.statusBar().showMessage("Folder selection cancelled.")

    @Slot()
    def handle_scan_started(self):
        # (Modified to disable refresh button)
        print("Scan started signal received."); self.loading_label.setText("Scanning folder..."); self.loading_label.setVisible(True); self.tree_widget.setVisible(False); self.select_folder_button.setEnabled(False); self.refresh_button.setEnabled(False); self.copy_button.setEnabled(False); self.tree_widget.setEnabled(False); self.manage_workspaces_button.setEnabled(False); self.manage_instructions_button.setEnabled(False)
        self._current_scan_discovered_files.clear() # Clear list for new scan

    @Slot(list)
    def add_tree_items_batch(self, batch_data):
       # (Modified to collect discovered valid file paths)
       self.tree_widget.setUpdatesEnabled(False)
       try:
           for i, item_data in enumerate(batch_data):
               path_str, is_dir, is_valid, reason, token_count = item_data
               normalized_path = os.path.normpath(path_str) # Normalize here
               self._create_or_update_tree_item(normalized_path, is_dir, is_valid, reason, token_count)
               # Add to discovered list *if valid and not a directory*
               if is_valid and not is_dir:
                   self._current_scan_discovered_files.add(normalized_path)
               # Optional: Process events periodically for responsiveness
               # if i > 0 and i % 100 == 0: QApplication.processEvents()
       finally:
           self.tree_widget.setUpdatesEnabled(True)


    @Slot(int)
    def handle_progress_update(self, count):
        # (Unchanged)
        self.loading_label.setText(f"Scanning... ({count} items found)")

# (Inside MainWindow class)

    @Slot()
    def handle_scan_finished(self):
        """Handles completion of the directory scan, updates folder tokens, and manages changes."""
        print("Scan finished signal received.")
        self.loading_label.setVisible(False)
        self.tree_widget.setVisible(True)
        self.tree_widget.setEnabled(True)
        self.select_folder_button.setEnabled(True)
        self.refresh_button.setEnabled(True) # Re-enable refresh button
        self.copy_button.setEnabled(True)
        self.manage_workspaces_button.setEnabled(True)
        self.manage_instructions_button.setEnabled(True)
        # self.tree_widget.resizeColumnToContents(1) # Moved to after token update

        # --- NEW: Update folder token counts ---
        # Calculate and display aggregated token counts for folders
        self._update_folder_token_counts()
        # --- END NEW ---

        # Resize column *after* potential text changes from token updates
        self.tree_widget.resizeColumnToContents(1)

        # --- Change Detection Logic ---
        saved_checked_paths = self._pending_tree_restore_paths # Set of normalized paths saved before scan
        current_discovered_files = self._current_scan_discovered_files # Set of normalized valid files found now

        # Files found now that were NOT checked before (includes truly new files and existing files that weren't checked)
        newly_discovered_or_unchecked_files = current_discovered_files - saved_checked_paths
        # Files that WERE checked before but are NOT valid/found now
        missing_or_invalid_files = saved_checked_paths - current_discovered_files

        paths_to_check_now = set(saved_checked_paths) # Start with the original set

        if newly_discovered_or_unchecked_files:
            print(f"Found {len(newly_discovered_or_unchecked_files)} new or previously unchecked valid files.")
            # Keep message reasonable length
            max_files_to_show = 10
            # Ensure items shown exist in the current tree before displaying
            valid_new_files_in_tree = sorted([p for p in newly_discovered_or_unchecked_files if p in self.tree_items])

            if valid_new_files_in_tree: # Only prompt if there are valid new files to show/add
                files_list_str = "\n".join(valid_new_files_in_tree[:max_files_to_show])
                if len(valid_new_files_in_tree) > max_files_to_show:
                    files_list_str += f"\n... and {len(valid_new_files_in_tree) - max_files_to_show} more"

                reply = QMessageBox.question(self, "New/Unchecked Files Found",
                                             f"The following valid files were found that were not in your previous selection:\n\n{files_list_str}\n\nDo you want to add them to your selection?",
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                             QMessageBox.StandardButton.No)

                if reply == QMessageBox.StandardButton.Yes:
                    print("User chose to add new/unchecked files to selection.")
                    # Add only those new files that are actually present in the tree items now
                    # (Redundant check as we filtered above, but safe)
                    paths_to_check_now.update(valid_new_files_in_tree)
            else:
                print("New/unchecked files found, but none are currently visible/valid in the tree.")


        # --- Restore Selection ---
        # This also triggers update_aggregation_and_tokens via _restore_tree_selection
        self.statusBar().showMessage("Scan complete. Restoring selection...", 5000)
        self._restore_tree_selection(paths_to_check_now)

        # --- Notify about missing files ---
        if missing_or_invalid_files:
            print(f"Note: {len(missing_or_invalid_files)} previously selected files are now missing or invalid.")
            # Show a more persistent message if files were actually removed from selection
            if saved_checked_paths != paths_to_check_now: # Check if the final set differs from original
                 self.statusBar().showMessage(f"Scan complete. {len(missing_or_invalid_files)} previously selected files removed/invalid.", 8000)
            else: # Selection wasn't changed, just noting they weren't found this time
                 self.statusBar().showMessage(f"Scan complete. {len(missing_or_invalid_files)} previously selected files missing/invalid.", 5000)

        elif newly_discovered_or_unchecked_files and valid_new_files_in_tree and reply == QMessageBox.StandardButton.Yes:
             self.statusBar().showMessage("Scan complete. New files added to selection.", 4000)
        else:
            self.statusBar().showMessage("Scan and selection restore complete.", 3000)

        # Clear pending paths now that they've been processed
        self._pending_tree_restore_paths = set()

    @Slot(str, str)
    def handle_scan_error(self, path, error_msg):
        # (Unchanged)
        print(f"Scan error signal received: Path={path}, Error={error_msg}"); norm_path = os.path.normpath(path); item = self.tree_items.get(norm_path)
        if item: item.setText(1, f"Error: {error_msg}"); item.setForeground(1, self.error_color); item.setDisabled(True); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled); item.setCheckState(0, Qt.CheckState.Unchecked)
        else: print(f"Scan Error (Item not found in tree): Path={norm_path}, Error={error_msg}"); self.statusBar().showMessage(f"Scan error on {norm_path}: {error_msg}", 5000)
        # If the scanner thread reports an error and is no longer running, trigger finish handler
        # This is important for errors like the root directory being invalid
        if self.directory_scanner and not self.directory_scanner.isRunning():
            print("Scanner thread stopped after error signal, calling finish handler.")
            self.handle_scan_finished()



    @Slot(QTreeWidgetItem, int)
    def handle_item_changed(self, item, column):
        if column == 0 and not self._is_programmatically_checking:
            path_str = item.data(0, self.PATH_DATA_ROLE)
            if not path_str: return

            # Prevent checking disabled items
            if not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                if item.checkState(0) == Qt.CheckState.Checked:
                    print(f"Prevented checking disabled item: {path_str}")
                    self._is_programmatically_checking = True
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    self._is_programmatically_checking = False
                return # Don't process children or update aggregation

            path_obj = pathlib.Path(path_str) # Assuming pathlib is imported
            check_state = item.checkState(0)

            # Determine if folder (using childCount is simple here)
            is_folder = item.childCount() > 0
            # Add more robust checks if needed

            if is_folder:
                # Propagate check state to children BEFORE updating counts
                self._set_children_check_state(item, check_state)

            # Update aggregation output and main token count
            self.update_aggregation_and_tokens()

            # --- NEW: Update folder display based on new selection ---
            self._update_selected_folder_token_display()
            # --- END NEW ---


    def _set_children_check_state(self, parent_item, check_state):
        # (Unchanged)
        self._is_programmatically_checking = True
        try:
            queue = [parent_item];
            while queue:
                current_parent = queue.pop(0);
                for i in range(current_parent.childCount()):
                    child = current_parent.child(i)
                    # Only change check state if the child is enabled and checkable
                    if child and child.flags() & Qt.ItemFlag.ItemIsEnabled and child.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                        if child.checkState(0) != check_state: child.setCheckState(0, check_state)
                        # If it's a directory, add to queue to process its children
                        child_path_str = child.data(0, self.PATH_DATA_ROLE)
                        # Check if path exists and is a directory before adding to queue
                        if child_path_str:
                             # Use self.tree_items for quick check if it's registered as a folder
                             child_item_in_dict = self.tree_items.get(os.path.normpath(child_path_str))
                             if child_item_in_dict and child_item_in_dict.icon(0).name() == self.folder_icon.name(): # Crude check based on icon
                                 queue.append(child)
        finally: self._is_programmatically_checking = False


    @Slot()
    def update_aggregation_and_tokens(self):
        # (Unchanged)
        if not self.current_folder_path: self.aggregation_output.clear(); self.token_info_label.setText("Total Tokens: 0"); return
        if self.directory_scanner and self.directory_scanner.isRunning(): return
        # Debounce or delay slightly? Maybe not needed now.
        self._perform_update_aggregation_and_tokens()

    def _generate_file_tree_string(self, relative_paths):
  
            if not self.current_folder_path:
                return "[Error: Base folder path not set]"

            # Assume pathlib and os are imported elsewhere in the class/module
            import pathlib
            import os # Needed for normpath

            try:
                base_path = pathlib.Path(self.current_folder_path)
                if not base_path.is_dir(): # Basic check on base path
                    return f"[Error: Base folder path is not a valid directory: {self.current_folder_path}]"
            except Exception as base_err:
                return f"[Error: Invalid base folder path '{self.current_folder_path}': {base_err}]"

            # --- Input processing and sorting ---
            relative_paths_list = list(relative_paths)
            path_objects = []
            processed_path_strs = set()
            for p_str in relative_paths_list:
                try:
                    p_obj = pathlib.Path(p_str)
                    p_norm_str = p_obj.as_posix()
                    if p_norm_str and p_norm_str not in processed_path_strs:
                        path_objects.append(p_obj)
                        processed_path_strs.add(p_norm_str)
                    elif not p_norm_str and '.' not in processed_path_strs:
                        p_obj = pathlib.Path('.')
                        if p_obj.as_posix() not in processed_path_strs:
                            path_objects.append(p_obj)
                            processed_path_strs.add(p_obj.as_posix())
                except Exception as e:
                    print(f"Warning: Could not process path string '{p_str}': {e}")

            if not path_objects:
                if '.' in processed_path_strs: return f"{base_path.name}/"
                return ""

            def sort_key(p): return p.parts if p.parts else ('',)
            try: sorted_paths = sorted(path_objects, key=sort_key)
            except Exception as e: print(f"Error sorting paths: {e}"); return "[Error: Could not sort paths for tree view]"
            # --- End input processing and sorting ---

            tree_lines = []
            root_added = False
            root_name = base_path.name if base_path else "root"

            # --- Root handling ---
            if pathlib.Path('.') in sorted_paths:
                root_index = -1
                try: root_index = sorted_paths.index(pathlib.Path('.'))
                except ValueError: pass
                if root_index != -1:
                    is_root_dir = True
                    try:
                        if not base_path.is_dir(): is_root_dir = False
                    except OSError: is_root_dir = False
                    tree_lines.append(f"{root_name}{'/' if is_root_dir else ''}")
                    root_added = True
            # --- End root handling ---

            # --- Prefix and Connector helper functions ---
            def get_prefix_parts(current_index, current_path_parts, sorted_paths_list):
                prefix_parts = []
                for i in range(len(current_path_parts) - 1):
                    parent_level_prefix = current_path_parts[:i+1]; grandparent_prefix = current_path_parts[:i]; has_later = False
                    for j in range(current_index + 1, len(sorted_paths_list)):
                        later = sorted_paths_list[j]
                        if len(later.parts) > i and later.parts[:i] == grandparent_prefix:
                            if len(later.parts) <= i+1 or later.parts[:i+1] != parent_level_prefix: has_later = True; break
                    prefix_parts.append("│   " if has_later else "    ")
                return prefix_parts

            def get_connector(current_index, current_path_parts, sorted_paths_list):
                is_last = True; parent_parts = current_path_parts[:-1]
                for j in range(current_index + 1, len(sorted_paths_list)):
                    later = sorted_paths_list[j]
                    if len(later.parts) == len(current_path_parts) and later.parts[:-1] == parent_parts: is_last = False; break
                return "└── " if is_last else "├── "
            # --- End Helper Functions ---

            processed_indices = set()

            for i, path_obj in enumerate(sorted_paths):
                # Skip root '.' if already handled
                if path_obj == pathlib.Path('.') and root_added:
                    processed_indices.add(i); continue
                # Skip if already processed for some other reason
                if i in processed_indices: continue

                current_parts = path_obj.parts
                if not current_parts: continue # Should not happen normally

                try:
                    # --- Determine directory status (Filesystem only) ---
                    is_dir = False # Default to False (file)
                    absolute_path = base_path / path_obj

                    # Rely primarily on the filesystem check
                    try:
                        # is_dir() checks for existence implicitly. Handle potential errors.
                        if absolute_path.is_dir():
                            is_dir = True
                    except OSError as fs_err:
                        print(f"Debug: Filesystem check failed for '{absolute_path}': {fs_err}")
                        # Defaulting to file (is_dir=False) on error
                    except Exception as e:
                        print(f"Debug: Error checking path type for '{absolute_path}': {e}")
                        # Defaulting to file (is_dir=False) on error

                    # --- Icon check is NOT used to determine is_dir here ---

                    # --- End directory status determination ---

                    prefix_indent_parts = get_prefix_parts(i, current_parts, sorted_paths)
                    connector = get_connector(i, current_parts, sorted_paths)

                    prefix_str = "".join(prefix_indent_parts) + connector
                    display_name = current_parts[-1]
                    # Use the is_dir status determined primarily by the filesystem
                    suffix = "/" if is_dir else ""

                    tree_lines.append(f"{prefix_str}{display_name}{suffix}")
                    processed_indices.add(i)

                except Exception as e:
                    print(f"Error processing path '{path_obj}' for tree string: {e}")
                    error_prefix = "    " * (len(current_parts) - 1) + "└── " if current_parts else ""
                    error_name = getattr(path_obj, 'name', str(path_obj))
                    tree_lines.append(f"{error_prefix}[Error: {error_name}]")
                    processed_indices.add(i)

            # Join lines, handling potential empty list if only root was processed
            return "\n".join(tree_lines) if tree_lines else (f"{root_name}/" if root_added else "")



    def _perform_update_aggregation_and_tokens(self):
        # (Modified slightly to handle relative path generation more robustly)
        self.statusBar().showMessage("Updating aggregation and token count...", 1000); aggregated_lines = []; total_token_count = 0; processed_files = set(); checked_relative_paths_for_tree = []
        checked_absolute_paths = self._get_checked_paths(return_set=True) # Get the set of currently checked absolute paths

        # Generate relative paths for the file tree section
        if self.current_folder_path:
             base_path_norm = os.path.normpath(self.current_folder_path)
             for abs_path_norm in sorted(list(checked_absolute_paths)):
                  try:
                      relative_path = os.path.relpath(abs_path_norm, base_path_norm)
                      checked_relative_paths_for_tree.append(relative_path.replace('\\', '/')) # Use forward slashes for consistency
                  except ValueError: # Handle cases like different drives on Windows
                      if abs_path_norm == base_path_norm:
                           checked_relative_paths_for_tree.append('.')
                      else:
                           # Fallback: use only the name if relative path fails
                           checked_relative_paths_for_tree.append(os.path.basename(abs_path_norm))

        # Add File Tree if paths were checked
        if checked_relative_paths_for_tree:
             file_tree_string = self._generate_file_tree_string(checked_relative_paths_for_tree)
             if file_tree_string: aggregated_lines.append("--- File Tree ---"); aggregated_lines.append(file_tree_string); aggregated_lines.append("--- End File Tree ---"); aggregated_lines.append("")

        # Add Instructions
        instructions = self.instructions_input.toPlainText().strip(); instruction_tokens = calculate_tokens(instructions); total_token_count += instruction_tokens
        if instructions: aggregated_lines.append(f"--- Instructions ({instruction_tokens} tokens) ---"); aggregated_lines.append(instructions); aggregated_lines.append("-" * 60)

        # Add File Contents - Iterate through checked items using the absolute path set
        # Sort the absolute paths to ensure consistent order in the output
        for normalized_path in sorted(list(checked_absolute_paths)):
            if normalized_path not in processed_files:
                item = self.tree_items.get(normalized_path) # Get the item from our dictionary
                if item:
                    path_obj = pathlib.Path(normalized_path)
                    if path_obj.is_file(): # Process only files here
                        is_valid = bool(item.flags() & Qt.ItemFlag.ItemIsEnabled); file_token_count = item.data(0, self.TOKEN_COUNT_ROLE) or 0

                        # Regenerate relative path for display in the header
                        relative_path_str = "[Unknown Path]"
                        if self.current_folder_path:
                            try: relative_path_str = str(path_obj.relative_to(self.current_folder_path)).replace('\\', '/')
                            except ValueError: relative_path_str = path_obj.name

                        # Extract the file extension (like '.py', '.tsx', '.md')
                        _, file_extension = os.path.splitext(relative_path_str)

                        # Get the language identifier for the code block fence:
                        # Remove the leading dot and convert to lowercase.
                        # If there's no extension, default to an empty string (or 'txt').

                        # Append the opening code fence with the language identifier
                        aggregated_lines.append(f"{relative_path_str}")
            

                        if is_valid:
                            total_token_count += file_token_count # Add file tokens to total

                            _, file_extension = os.path.splitext(relative_path_str)
                            language_identifier = file_extension.lstrip('.').lower() if file_extension else ""

                            aggregated_lines.append(f"```{language_identifier}")
                            try:
                                with open(path_obj, 'rb') as f:
                                    raw_bytes = f.read(MAX_FILE_SIZE_BYTES + 1)
                                content = raw_bytes[:MAX_FILE_SIZE_BYTES].decode('utf-8', errors='replace')

                                sanitized_content = content.replace("```", "")

                                aggregated_lines.append(sanitized_content)

                                if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
                                    aggregated_lines.append("\n[... File content truncated ...]")

                            except Exception as e:
                                aggregated_lines.append(f"[Error reading file: {e}]")

                            aggregated_lines.append("```")
                    
                        else:
                            aggregated_lines.append(f"(Skipped: {item.text(1)})")

                        aggregated_lines.append("")
                        processed_files.add(normalized_path)
                else:
                    # This case should ideally not happen if the tree/checked state is consistent
                    print(f"Warning: Checked path '{normalized_path}' not found in tree_items during aggregation.")

        self.aggregation_output.setUpdatesEnabled(False); self.aggregation_output.setPlainText("\n".join(aggregated_lines)); self.aggregation_output.setUpdatesEnabled(True)
        cursor = self.aggregation_output.textCursor(); cursor.movePosition(cursor.MoveOperation.Start); self.aggregation_output.setTextCursor(cursor)
        self.token_info_label.setText(f"Total Estimated Tokens: {total_token_count:,}")
        if self.statusBar().currentMessage().startswith("Updating"): self.statusBar().showMessage("Aggregation complete.", 3000)


    def copy_to_clipboard(self):
        # (Unchanged)
        content = self.aggregation_output.toPlainText();
        if not content: self.statusBar().showMessage("Nothing to copy.", 3000); return
        try: pyperclip.copy(content); self.statusBar().showMessage("Content copied to clipboard!", 1500)
        except Exception as e: error_msg = f"Could not copy to clipboard: {e}"; print(f"Clipboard Error: {error_msg}"); self.statusBar().showMessage("Error copying to clipboard.", 5000); QMessageBox.warning(self, "Clipboard Error", error_msg)


    def closeEvent(self, event):
        # (Unchanged)
        print("Close event triggered.")
        self._save_current_workspace_state() # Save active workspace state
        self._save_workspaces() # Save all workspace data
        self._save_custom_instructions() # Save custom instructions templates

        if self.directory_scanner and self.directory_scanner.isRunning():
            print("Stopping scanner thread on close...")
            self.directory_scanner.stop()
            if not self.directory_scanner.wait(2000):
                print("Warning: Scanner thread did not stop gracefully on close.")
        event.accept()


# --- Main Execution (Unchanged) ---
def main():
    try: QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    except AttributeError: print("Note: Qt.AA_EnableHighDpiScaling attribute not found.")
    try: QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    except AttributeError: print("Note: Qt.AA_UseHighDpiPixmaps attribute not found.")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()