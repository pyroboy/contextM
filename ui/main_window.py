import os
import sys
import pathlib
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QSplitter, QLabel, QMessageBox, QStyle, QDialog
)
from PySide6.QtCore import Qt, Slot, QTimer

# Core components
from core import workspace_manager, selection_manager
from core.scanner import Scanner
from core.watcher import FileWatcher

# UI components
from .widgets.tree_panel import TreePanel
from .widgets.instructions_panel import InstructionsPanel
from .widgets.aggregation_view import AggregationView
from .widgets.file_changes_panel import FileChangesPanel
from .widgets.selection_manager import SelectionManagerPanel

# Dialogs
from .dialogs.scan_config_dialog import ScanConfigDialog
from .dialogs.workspace_dialog import WorkspaceManagerDialog
from .dialogs.custom_instructions_dialog import CustomInstructionsDialog
from .dialogs.edit_selection_group_dialog import EditSelectionGroupDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Context-M")
        self.setGeometry(100, 100, 1200, 800)

        # Workspace and core components
        self.workspaces = workspace_manager.load_workspaces()
        self.custom_instructions = workspace_manager.load_custom_instructions()
        self.current_workspace_name = None
        self.current_folder_path = None
        self.current_scan_settings = None
        self.scanner = Scanner(self)
        self.file_watcher = None

        # Selection Groups
        self.selection_groups = {}
        self.active_selection_group = "Default"

        self._setup_ui()
        self._connect_signals()

        # Initial workspace load
        last_active = self.workspaces.get("last_active_workspace", "Default")
        if last_active not in self.workspaces:
            last_active = "Default"
        self._switch_workspace(last_active, initial_load=True)

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # Top Controls
        top_controls_layout = QHBoxLayout()
        self.manage_workspaces_button = QPushButton("Workspaces")
        self.workspace_label = QLabel("Workspace: None")
        self.select_folder_button = QPushButton("Select Project Folder...")
        self.select_folder_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.refresh_button = QPushButton()
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.setToolTip("Refresh current folder view")
        self.refresh_button.setEnabled(False)
        self.path_display_label = QLabel("No folder selected.")
        self.path_display_label.setWordWrap(True)
        
        top_controls_layout.addWidget(self.manage_workspaces_button)
        top_controls_layout.addWidget(self.workspace_label)
        top_controls_layout.addSpacing(20)
        top_controls_layout.addWidget(self.select_folder_button)
        top_controls_layout.addWidget(self.refresh_button)
        top_controls_layout.addWidget(self.path_display_label, 1)

        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: Selection Manager and Tree Panel in a vertical splitter
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.selection_manager_panel = SelectionManagerPanel(self)
        self.tree_panel = TreePanel(self)

        self.left_splitter.addWidget(self.selection_manager_panel)
        self.left_splitter.addWidget(self.tree_panel)
        self.left_splitter.setStretchFactor(0, 0)
        self.left_splitter.setStretchFactor(1, 1)
        self.left_splitter.setSizes([30, 770]) # Small initial size for the manager

        left_layout.addWidget(self.left_splitter)
        self.splitter.addWidget(left_container)

        # Right side: Instructions and Aggregation
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter_right = QSplitter(Qt.Orientation.Vertical)

        self.instructions_panel = InstructionsPanel(self)
        self.aggregation_view = AggregationView(self)

        self.splitter_right.addWidget(self.instructions_panel)
        self.splitter_right.addWidget(self.aggregation_view)
        self.splitter_right.setStretchFactor(0, 0)
        self.splitter_right.setStretchFactor(1, 1)
        self.splitter_right.setSizes([150, 650])

        right_layout.addWidget(self.splitter_right)
        self.splitter.addWidget(right_container)

        # Create a new top-level splitter to add the third column
        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.addWidget(self.splitter)

        # Rightmost panel: File Changes Log
        self.file_changes_panel = FileChangesPanel(self)
        self.top_splitter.addWidget(self.file_changes_panel)

        # Set initial sizes for the three main panels
        self.top_splitter.setSizes([850, 350]) # Main area and changes panel
        self.splitter.setSizes([450, 400]) # Tree panel and right container

        main_layout.addLayout(top_controls_layout)
        main_layout.addWidget(self.top_splitter, 1)
        self.statusBar().showMessage("Ready.")

    def _connect_signals(self):
        # Top control signals
        self.select_folder_button.clicked.connect(self.open_folder_dialog)
        self.refresh_button.clicked.connect(self._refresh_current_folder)
        self.manage_workspaces_button.clicked.connect(self._open_workspace_dialog)

        # Scanner signals
        self.scanner.scan_complete.connect(self._handle_scan_complete)
        self.scanner.scan_error.connect(lambda p, e: print(f"Scan Error: {p} - {e}"))

        # Panel signals
        self.tree_panel.item_checked_changed.connect(self.update_aggregation_and_tokens)
        self.tree_panel.file_tokens_changed.connect(self.file_changes_panel.add_change_entry)
        self.tree_panel.root_path_changed.connect(self.file_changes_panel.set_root_path)
        self.tree_panel.selection_changed.connect(self._on_tree_selection_changed)

        self.instructions_panel.manage_templates_requested.connect(self._open_custom_instructions_dialog)
        self.instructions_panel.template_selected.connect(self._apply_instruction_template)
        self.instructions_panel.instructions_text_changed.connect(self.aggregation_view.set_system_prompt)

        self.aggregation_view.token_count_changed.connect(self.instructions_panel.update_token_count)

        # Selection Manager signals
        self.selection_manager_panel.group_changed.connect(self._on_group_changed)
        self.selection_manager_panel.save_requested.connect(self._on_save_group_requested)
        self.selection_manager_panel.new_requested.connect(self._on_new_group_requested)
        self.selection_manager_panel.edit_requested.connect(self._on_edit_group_requested)
        self.selection_manager_panel.delete_requested.connect(self._on_delete_group_requested)

    def closeEvent(self, event):
        print("Closing application...")
        if self.file_watcher:
            self.file_watcher.stop()
        self._save_current_workspace_state()
        super().closeEvent(event)

    
    # --- High-Level Orchestration Methods ---

    def _save_current_workspace_state(self):
        if not self.current_workspace_name:
            return
        current_ws = self.workspaces[self.current_workspace_name]
        # This now saves the active group, not just the checked paths
        current_ws["active_selection_group"] = self.active_selection_group
        current_ws["instructions"] = self.instructions_panel.get_text()
        workspace_manager.save_workspaces(self.workspaces)

    def _switch_workspace(self, workspace_name, initial_load=False):
        if not initial_load:
            self._save_current_workspace_state()

        if self.file_watcher:
            self.file_watcher.stop()
            self.file_watcher = None

        if workspace_name not in self.workspaces:
            workspace_name = "Default"

        print(f"Switching to workspace: {workspace_name}")
        self.current_workspace_name = workspace_name
        self.workspace_label.setText(f"Workspace: {workspace_name}")

        current_ws = self.workspaces[self.current_workspace_name]
        self.current_folder_path = current_ws.get("folder_path")
        self.current_scan_settings = current_ws.get("scan_settings")

        # Load selection groups
        self.selection_groups = selection_manager.load_groups(current_ws)
        self.active_selection_group = current_ws.get("active_selection_group", "Default")
        if self.active_selection_group not in self.selection_groups:
            self.active_selection_group = "Default"
        self.selection_manager_panel.update_groups(list(self.selection_groups.keys()), self.active_selection_group)

        self.instructions_panel.set_text(current_ws.get("instructions", ""))

        if self.current_folder_path:
            self.path_display_label.setText(f"Selected: {self.current_folder_path}")
            self.refresh_button.setEnabled(True)
            # Set pending paths from the active group before triggering a scan/refresh
            active_group_data = self.selection_groups.get(self.active_selection_group, {})
            pending_paths = set(active_group_data.get("checked_paths", []))
            self.tree_panel.set_pending_restore_paths(pending_paths)
            self._refresh_current_folder()
        else:
            self.tree_panel.clear_tree()
            self.path_display_label.setText("No folder selected for this workspace.")
            self.refresh_button.setEnabled(False)
        
        self.selection_manager_panel.set_dirty(False)
        self.workspaces["last_active_workspace"] = workspace_name

    @Slot()
    def update_aggregation_and_tokens(self):
        """Updates the aggregation view based on the current tree selection."""
        checked_paths = self.tree_panel.get_checked_paths(relative=True)
        
        # Generate the file tree string from checked paths
        tree_string = self._generate_file_tree_string(checked_paths)
        
        # Get the actual aggregated content and token count
        aggregated_content, total_tokens = self.tree_panel.get_aggregated_content()
        
        # Combine the tree string with the aggregated content
        final_content = f"{tree_string}\n\n---\n\n{aggregated_content}"
        
        self.aggregation_view.set_content(final_content, total_tokens)
        self.tree_panel.update_folder_token_display()

    def _generate_file_tree_string(self, relative_paths: set) -> str:
        """Turns a set of relative paths into a pretty ASCII tree string."""
        if not self.current_folder_path or not relative_paths:
            return ""

        # Create a hierarchical dictionary from the paths
        path_tree = {}
        # Add all parent directories to the tree structure implicitly
        all_paths = set(relative_paths)
        for path_str in relative_paths:
            if path_str == '.': continue
            parent = pathlib.Path(path_str).parent
            while str(parent) != '.':
                all_paths.add(str(parent))
                parent = parent.parent

        for path_str in sorted(list(all_paths)):
            if path_str == '.': continue
            parts = path_str.split(os.sep)
            node = path_tree
            for part in parts:
                node = node.setdefault(part, {})

        # Recursive function to build the string lines
        def build_lines(subtree, path_prefix, tree_prefix=""):
            lines = []
            entries = sorted(subtree.keys())
            for i, name in enumerate(entries):
                is_last = (i == len(entries) - 1)
                connector = "└── " if is_last else "├── "
                
                current_path_str = os.path.join(path_prefix, name)
                current_path_obj = pathlib.Path(self.current_folder_path) / current_path_str
                
                # A path is a directory if it has children in our tree or is a dir on disk
                is_dir = bool(subtree[name]) or current_path_obj.is_dir()
                suffix = "/" if is_dir else ""
                
                # Only add lines for paths that were explicitly checked or are parents
                if current_path_str in all_paths:
                    lines.append(f"{tree_prefix}{connector}{name}{suffix}")

                if subtree[name]:
                    new_tree_prefix = tree_prefix + ("    " if is_last else "│   ")
                    lines.extend(build_lines(subtree[name], current_path_str, new_tree_prefix))
            return lines

        # Start building the tree string
        root_name = os.path.basename(self.current_folder_path)
        output_lines = [f"{root_name}/"]
        output_lines.extend(build_lines(path_tree, ""))

        return "\n".join(output_lines)

    # --- Action/Event Handler Methods ---

    @Slot()
    def open_folder_dialog(self):
        new_folder = QFileDialog.getExistingDirectory(self, "Select Project Folder")
        if not new_folder:
            return

        dialog = ScanConfigDialog(new_folder, self.current_scan_settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.current_folder_path = new_folder
            self.current_scan_settings = dialog.get_settings()
            
            current_ws = self.workspaces[self.current_workspace_name]
            current_ws["folder_path"] = self.current_folder_path
            current_ws["scan_settings"] = self.current_scan_settings
            
            self.path_display_label.setText(f"Selected: {self.current_folder_path}")
            self.refresh_button.setEnabled(True)
            self._start_scan(self.current_folder_path, self.current_scan_settings)

    @Slot()
    def _refresh_current_folder(self):
        if not self.current_folder_path or not self.current_scan_settings:
            return
        self.tree_panel.set_pending_restore_paths(self.tree_panel.get_checked_paths(return_set=True))
        self._start_scan(self.current_folder_path, self.current_scan_settings)

    def _start_scan(self, folder_path, settings):
        self.tree_panel.clear_tree()
        self.tree_panel.show_loading(True)
        self.statusBar().showMessage(f"Scanning {folder_path}...")
        self.scanner.start_scan(folder_path, settings)

    @Slot(dict)
    def _handle_scan_complete(self, results):
        self.tree_panel.show_loading(False)
        self.tree_panel.populate_tree(results['items'], self.current_folder_path)
        self.update_aggregation_and_tokens()
        self.statusBar().showMessage(f"Scan complete. Found {len(results['items'])} items.", 5000)
        for path, error in results['errors']:
            print(f"Scan Error: {path} - {error}")
        self._start_file_watcher()

    def _start_file_watcher(self):
        if self.file_watcher and self.file_watcher.isRunning():
            self.file_watcher.stop()

        ws = self.workspaces[self.current_workspace_name]
        if ws.get('scan_settings', {}).get('live_watcher', False) and self.current_folder_path:
            self.file_watcher = FileWatcher(self.current_folder_path, self.current_scan_settings.get('ignore_folders', set()))
            self.file_watcher.fs_event_batch.connect(self.tree_panel.handle_fs_events)
            self.file_watcher.fs_event_batch.connect(self.file_changes_panel.update_with_fs_events)
            self.file_watcher.start()
            print(f"File watcher started for {self.current_folder_path}")

    @Slot()
    def _open_workspace_dialog(self):
        self._save_current_workspace_state()
        dialog = WorkspaceManagerDialog(self.workspaces, self.current_workspace_name, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_ws = dialog.get_selected_workspace()
            if selected_ws and selected_ws != self.current_workspace_name:
                self._switch_workspace(selected_ws)

    @Slot()
    def _open_custom_instructions_dialog(self):
        dialog = CustomInstructionsDialog(self.custom_instructions, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.custom_instructions = dialog.get_instructions()
            workspace_manager.save_custom_instructions(self.custom_instructions)
            self.instructions_panel.populate_templates(self.custom_instructions)

    def closeEvent(self, event):
        """Ensure background threads are stopped when the window closes."""
        if self.file_watcher and self.file_watcher.isRunning():
            self.file_watcher.stop()
            self.file_watcher.wait()  # Wait for the thread to finish
        super().closeEvent(event)

    @Slot(str)
    def _apply_instruction_template(self, template_name):
        if template_name in self.custom_instructions:
            instruction_text = self.custom_instructions[template_name]
            self.instructions_panel.set_text(instruction_text)
            # Manually emit the signal since programmatic text changes don't trigger it
            self.instructions_panel.instructions_text_changed.emit(instruction_text)

    # --- Selection Group Handlers ---

    @Slot(str)
    def _on_group_changed(self, group_name):
        if not group_name or group_name not in self.selection_groups:
            return

        self.active_selection_group = group_name
        paths_to_check = set(self.selection_groups[group_name].get("checked_paths", []))
        self.tree_panel.set_checked_paths(paths_to_check)
        self.selection_manager_panel.set_dirty(False)
        self._save_current_workspace_state() # Save active group change

    @Slot()
    def _on_save_group_requested(self):
        current_group_name = self.selection_manager_panel.get_current_group_name()
        if not current_group_name:
            return
        
        current_paths = self.tree_panel.get_checked_paths(return_set=True)
        current_description = self.selection_groups.get(current_group_name, {}).get("description", "")
        
        current_ws = self.workspaces[self.current_workspace_name]
        selection_manager.save_group(current_ws, current_group_name, current_description, current_paths)
        workspace_manager.save_workspaces(self.workspaces)

        # Reload groups to update internal state
        self.selection_groups = selection_manager.load_groups(current_ws)
        self.selection_manager_panel.set_dirty(False)
        self.statusBar().showMessage(f"Group '{current_group_name}' saved.", 3000)

    @Slot()
    def _on_new_group_requested(self):
        # For now, we'll just create a new group with a default name
        # A more advanced implementation would use an inline rename widget
        new_name = "New Group"
        i = 1
        while new_name in self.selection_groups:
            new_name = f"New Group {i}"
            i += 1

        current_ws = self.workspaces[self.current_workspace_name]
        selection_manager.save_group(current_ws, new_name, "", set()) # Create empty
        workspace_manager.save_workspaces(self.workspaces)
        self.selection_groups = selection_manager.load_groups(current_ws)
        self.selection_manager_panel.update_groups(list(self.selection_groups.keys()), new_name)

    @Slot(str)
    def _on_edit_group_requested(self, group_name):
        if group_name not in self.selection_groups:
            return
        
        group_data = self.selection_groups[group_name]
        dialog = EditSelectionGroupDialog(group_name, group_data, self.selection_groups, self)
        
        # Connect the reset button
        dialog.reset_button.clicked.connect(
            lambda: dialog.set_current_selection(list(self.tree_panel.get_checked_paths(return_set=True)))
        )

        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            new_name = result['name']
            
            current_ws = self.workspaces[self.current_workspace_name]

            # If renamed, delete the old group
            if new_name != group_name:
                selection_manager.delete_group(current_ws, group_name)

            selection_manager.save_group(current_ws, new_name, result['description'], set(result['checked_paths']))
            workspace_manager.save_workspaces(self.workspaces)

            self.selection_groups = selection_manager.load_groups(current_ws)
            if self.active_selection_group == group_name:
                self.active_selection_group = new_name
            
            self.selection_manager_panel.update_groups(list(self.selection_groups.keys()), self.active_selection_group)
            self.tree_panel.set_checked_paths(set(result['checked_paths']))

    @Slot(str)
    def _on_delete_group_requested(self, group_name):
        if group_name not in self.selection_groups or group_name == "Default":
            return
        
        current_ws = self.workspaces[self.current_workspace_name]
        selection_manager.delete_group(current_ws, group_name)
        workspace_manager.save_workspaces(self.workspaces)
        self.selection_groups = selection_manager.load_groups(current_ws)

        new_active_group = "Default" if self.active_selection_group == group_name else self.active_selection_group
        self.selection_manager_panel.update_groups(list(self.selection_groups.keys()), new_active_group)
        if self.active_selection_group == group_name:
            self._on_group_changed("Default")

    @Slot()
    def _on_tree_selection_changed(self):
        # Compare current tree state with the saved state of the active group
        active_group_name = self.selection_manager_panel.get_current_group_name()
        if not active_group_name or active_group_name not in self.selection_groups:
            return

        saved_paths = set(self.selection_groups[active_group_name].get("checked_paths", []))
        current_paths = self.tree_panel.get_checked_paths(return_set=True)

        if saved_paths != current_paths:
            self.selection_manager_panel.set_dirty(True)
        else:
            self.selection_manager_panel.set_dirty(False)

