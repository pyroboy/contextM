import os
import sys
import pathlib
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QStyle
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
from dialogs.custom_instructions_dialog import CustomInstructionsDialog

# Controllers
from .controllers.workspace_controller import WorkspaceController
from .controllers.scan_controller import ScanController
from .controllers.selection_controller import SelectionController

class MainWindow(QMainWindow):
    def __init__(self, test_mode=False, testing_path=None):
        print("MainWindow: Initializing...")
        super().__init__()
        self.setWindowTitle("Context-M")
        self.setGeometry(100, 100, 1200, 800)

        self.test_mode = test_mode
        self.testing_path = testing_path

        # Workspace and core components
        self.workspaces = {}
        self.custom_instructions = {}
        self.current_workspace_name = None
        self.current_folder_path = None
        self.current_scan_settings = None
        self.scanner = Scanner(self)
        self.file_watcher = None

        # Selection Groups
        self.selection_groups = {}
        self.active_selection_group = "Default"

        # Controllers
        self.workspace_ctl = WorkspaceController(self)
        self.scan_ctl = ScanController(self)
        self.sel_ctl = SelectionController(self)

        self._setup_ui()
        self._connect_signals()

        # In normal mode, load data and the last active workspace. In test mode, wait for the test to decide.
        if not test_mode:
            self.load_initial_data()
            print(f"[DEBUG] In __init__, after load_initial_data: {self.workspaces}")
            last_active = self.workspaces.get("last_active_workspace", "Default")
            self.workspace_ctl.switch(last_active, initial_load=True)

    def load_initial_data(self):
        """Loads workspaces and other initial data. Can be called manually in test mode."""
        self.workspaces = workspace_manager.load_workspaces(base_path=self.testing_path)
        print(f"[DEBUG] Inside load_initial_data, after loading: {self.workspaces}")
        if not self.workspaces or ("workspaces" not in self.workspaces or not self.workspaces["workspaces"]):
            self.workspaces = {"workspaces": {"Default": {}}, "last_active_workspace": "Default"}
        self.custom_instructions = workspace_manager.load_custom_instructions(base_path=self.testing_path)

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

        # Left side
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self.left_splitter = QSplitter(Qt.Orientation.Vertical)
        self.selection_manager_panel = SelectionManagerPanel(self)
        self.tree_panel = TreePanel(self)
        self.tree_panel.item_checked_changed.connect(self._on_tree_selection_changed)
        self.left_splitter.addWidget(self.selection_manager_panel)
        self.left_splitter.addWidget(self.tree_panel)
        self.left_splitter.setStretchFactor(0, 0)
        self.left_splitter.setStretchFactor(1, 1)
        left_layout.addWidget(self.left_splitter)
        self.splitter.addWidget(left_container)

        # Right side
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.instructions_panel = InstructionsPanel(self)
        self.instructions_panel.populate_templates(self.custom_instructions)
        self.aggregation_view = AggregationView(self)
        self.file_changes_panel = FileChangesPanel(self)
        self.right_splitter.addWidget(self.instructions_panel)
        self.right_splitter.addWidget(self.aggregation_view)
        self.right_splitter.addWidget(self.file_changes_panel)

        # Configure splitter sizes - ensure file changes panel is visible
        self.right_splitter.setStretchFactor(0, 0)  # Instructions panel
        self.right_splitter.setStretchFactor(1, 1)  # Aggregation view
        self.right_splitter.setStretchFactor(2, 0)  # File changes panel
        self.right_splitter.setSizes([150, 500, 150])  # Ensure file changes panel has space

        right_layout.addWidget(self.right_splitter)
        self.splitter.addWidget(right_container)

        self.splitter.setSizes([300, 900])
        main_layout.addLayout(top_controls_layout)
        main_layout.addWidget(self.splitter)

        # Status bar watcher indicator
        self._setup_watcher_indicator()
        print("MainWindow: UI setup complete.")

    def _connect_signals(self):
        # Top controls
        self.manage_workspaces_button.clicked.connect(self.workspace_ctl.open_manager)
        self.select_folder_button.clicked.connect(self.scan_ctl.select_folder)
        self.scan_ctl.folder_selected.connect(self._update_path_display)
        self.refresh_button.clicked.connect(self.scan_ctl.refresh)

        # Core components
        self.scanner.scan_complete.connect(self._handle_scan_complete)
        self.workspace_ctl.workspace_changed.connect(self._on_workspace_switched)

        # Panels
        self.instructions_panel.manage_button.clicked.connect(self._open_custom_instructions_dialog)
        self.instructions_panel.template_selected.connect(self._apply_instruction_template)
        self.instructions_panel.instructions_changed.connect(self._on_instructions_changed)

        # Selection Manager Panel
        self.selection_manager_panel.group_changed.connect(self.sel_ctl.on_group_changed)
        self.selection_manager_panel.save_requested.connect(self.sel_ctl.save_group)
        self.selection_manager_panel.new_requested.connect(self.sel_ctl.new_group)
        self.selection_manager_panel.edit_requested.connect(self.sel_ctl.edit_group)
        self.selection_manager_panel.delete_requested.connect(self.sel_ctl.delete_group)

    def closeEvent(self, event):
        """Handle the window close event by ensuring graceful shutdown of background threads."""
        self._update_current_workspace_state()
        self._save_current_workspace_state()
        self._stop_file_watcher()
        if self.scanner and self.scanner.is_running():
            self.scanner.quit()
            self.scanner.wait()
        event.accept()

    def _update_current_workspace_state(self):
        if not self.current_workspace_name or self.current_workspace_name not in self.workspaces.get('workspaces', {}):
            return

        current_ws = self.workspaces['workspaces'][self.current_workspace_name]
        if not isinstance(current_ws, dict):
            current_ws = {}
            self.workspaces['workspaces'][self.current_workspace_name] = current_ws

        current_ws["folder_path"] = self.current_folder_path
        current_ws["scan_settings"] = self.current_scan_settings
        current_ws["instructions"] = self.instructions_panel.get_text()
        current_ws['active_selection_group'] = self.active_selection_group

        if self.active_selection_group in self.selection_groups:
            checked_paths = self.tree_panel.get_checked_paths(relative=True)
            if isinstance(self.selection_groups[self.active_selection_group], dict):
                self.selection_groups[self.active_selection_group]["checked_paths"] = checked_paths
        current_ws['selection_groups'] = self.selection_groups

    def _save_current_workspace_state(self):
        if self.workspaces:
            workspace_manager.save_workspaces(self.workspaces)

    def _switch_workspace(self, workspace_name, initial_load=False):
        print(f"[DEBUG][_switch_workspace] Initiating switch to workspace: '{workspace_name}'. Initial load: {initial_load}")

        # This check is to create a brand new Default workspace if the JSON is empty or missing.
        # It should only run if the workspace truly doesn't exist after loading.
        if workspace_name == "Default" and not self.workspaces.get('workspaces', {}).get(workspace_name):
            print("[DEBUG][_switch_workspace] 'Default' workspace not found. Creating a new one.")
            if 'workspaces' not in self.workspaces:
                print("[DEBUG][_switch_workspace] 'workspaces' key missing. Initializing.")
                self.workspaces['workspaces'] = {}
            self.workspaces['workspaces']['Default'] = {}
            print(f"[DEBUG][_switch_workspace] New 'Default' workspace created. Current workspaces object: {self.workspaces}")

        if not initial_load:
            print(f"[DEBUG][_switch_workspace] Not initial load. Saving state for current workspace: '{self.current_workspace_name}'")
            self._save_current_workspace_state()
            print("[DEBUG][_switch_workspace] State saved.")
        else:
            print("[DEBUG][_switch_workspace] Initial load detected. Skipping state save.")

        print(f"--- Switching to workspace: {workspace_name} ---")
        self.current_workspace_name = workspace_name
        self.workspace_label.setText(f"Workspace: {workspace_name}")
        print(f"[DEBUG][_switch_workspace] Set current_workspace_name to: '{self.current_workspace_name}'")


        print(f"[DEBUG][_switch_workspace] Attempting to retrieve data for workspace '{workspace_name}' from self.workspaces")
        current_ws = self.workspaces.get('workspaces', {}).get(workspace_name, {})
        print(f"[DEBUG][_switch_workspace] Loaded workspace data: {current_ws}")

        self.current_folder_path = current_ws.get("folder_path")
        self.current_scan_settings = current_ws.get("scan_settings")
        print(f"[DEBUG][_switch_workspace] Extracted folder path: {self.current_folder_path}")
        print(f"[DEBUG][_switch_workspace] Extracted scan settings: {self.current_scan_settings}")

        self._update_path_display(self.current_folder_path if self.current_folder_path else "No folder selected.")
        print(f"[DEBUG][_switch_workspace] Updated path display.")

        self._on_workspace_switched(workspace_name)
        print(f"[DEBUG][_switch_workspace] Executed _on_workspace_switched callback.")

        if self.current_folder_path and self.current_scan_settings:
            print(f"[DEBUG][_switch_workspace] Folder path and scan settings found. Starting scan for: {self.current_folder_path}")
            active_group_data = self.selection_groups.get(self.active_selection_group, {})
            checked_paths_to_restore = active_group_data.get("checked_paths", [])
            self.scan_ctl.start(self.current_folder_path, self.current_scan_settings, checked_paths_to_restore)
        else:
            print("[DEBUG][_switch_workspace] Not starting scan. Folder path, scan settings, or both are missing.")
            print(f"[DEBUG][_switch_workspace] -> Has folder path: {bool(self.current_folder_path)}")
            print(f"[DEBUG][_switch_workspace] -> Has scan settings: {bool(self.current_scan_settings)}")

        instructions_text = current_ws.get("instructions", "")
        self.instructions_panel.set_text(instructions_text)
        print(f"[DEBUG][_switch_workspace] Set instructions text. Length: {len(instructions_text)}")


        print("[DEBUG][_switch_workspace] Loading selection groups from workspace data.")
        self.selection_groups = selection_manager.load_groups(current_ws)
        self.active_selection_group = current_ws.get("active_selection_group", "Default")
        self.selection_manager_panel.update_groups(list(self.selection_groups.keys()), self.active_selection_group)
        print(f"[DEBUG][_switch_workspace] Loaded {len(self.selection_groups)} selection groups. Active group: '{self.active_selection_group}'")

        print(f"[DEBUG][_switch_workspace] Workspace switch to '{workspace_name}' complete. ✅")
    @Slot(str)
    def _on_instructions_changed(self):
        self._update_current_workspace_state()
        self._save_current_workspace_state()

    def _on_tree_selection_changed(self):
        self.update_aggregation_and_tokens()
        self._update_current_workspace_state()
        # self._save_current_workspace_state()

    @Slot(str)
    def _on_workspace_switched(self, workspace_name):
        self._update_path_display(self.current_folder_path or "No folder selected.")
        self.refresh_button.setEnabled(bool(self.current_folder_path))

        if self.current_folder_path:
            self.tree_panel.show_loading(True)
            self._start_file_watcher()
        else:
            self.tree_panel.clear_tree()
            self.tree_panel.show_loading(False)
            self.update_aggregation_and_tokens()
            self._stop_file_watcher()

    def _handle_scan_complete(self, results):
        self.statusBar().showMessage("Scan complete.", 3000)
        self.tree_panel.show_loading(False)
        if results and results.get('items'):
            self.tree_panel.populate_tree(results['items'], self.current_folder_path)
            # After populating, apply the checked state from the active selection group
            if self.active_selection_group in self.selection_groups:
                group_data = self.selection_groups[self.active_selection_group]
                if isinstance(group_data, dict):
                    checked_paths = group_data.get("checked_paths", [])
                    self.tree_panel.set_checked_paths(checked_paths, relative=True)
        else:
            self.sel_ctl.update_ui()
        self._update_instructions_ui()

    def _start_file_watcher(self):
        self._stop_file_watcher()

        if self.current_folder_path and self.current_scan_settings:
            if self.current_scan_settings.get('live_watcher', True):
                ignore_rules = self.current_scan_settings.get('ignore_folders', [])
                
                # Add workspace file to ignore patterns to prevent save loops
                ws_file_path = workspace_manager._get_workspace_file_path()
                if ws_file_path:
                    ignore_rules.append(str(pathlib.Path(ws_file_path).name))

                self.file_watcher = FileWatcher(self.current_folder_path, ignore_rules)
                self.file_watcher.fs_event_batch.connect(self.file_changes_panel.update_with_fs_events)
                self.file_watcher.start()
                self.watcher_indicator.setVisible(True)
                self.watcher_indicator.setToolTip("File watcher is active")
            else:
                self.watcher_indicator.setVisible(False)
                self.watcher_indicator.setToolTip("File watcher is disabled for this workspace")

    def _stop_file_watcher(self):
        if self.file_watcher:
            self.file_watcher.stop()
            self.file_watcher = None
            self.watcher_indicator.setVisible(False)

    def update_aggregation_and_tokens(self):
        from .helpers.aggregation_helper import generate_file_tree_string
        checked = self.tree_panel.get_checked_paths(relative=True)
        tree_str = generate_file_tree_string(self.current_folder_path, checked)
        content, tokens = self.tree_panel.get_aggregated_content()
        final = f"{tree_str}\n\n---\n\n{content}"
        self.aggregation_view.set_content(final, tokens)

    def _setup_watcher_indicator(self):
        """Adds a green dot indicator to the status bar for watcher status."""
        from PySide6.QtWidgets import QLabel
        from PySide6.QtGui import QPixmap, QPainter, QColor
        
        # Create the indicator label
        self.watcher_indicator = QLabel()
        self.watcher_indicator.setToolTip("File watcher status")
        self.watcher_indicator.setFixedSize(16, 16)
        
        # Create green dot pixmap
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setBrush(QColor(0, 200, 0))  # Green
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 12, 12)
        painter.end()
        
        self.watcher_indicator.setPixmap(pixmap)
        self.watcher_indicator.setVisible(False)  # Hidden by default
        
        # Add to status bar (right side)
        self.statusBar().addPermanentWidget(self.watcher_indicator)

    @Slot(str)
    def _open_custom_instructions_dialog(self):
        if not self.current_workspace_name:
            return
        current_ws = self.workspaces.get('workspaces', {}).get(self.current_workspace_name, {})
        # Ensure local instructions dict exists
        current_ws.setdefault('local_custom_instructions', {})
        
        dialog = CustomInstructionsDialog(self.custom_instructions, current_ws, self)
        dialog.instructions_changed.connect(self._handle_instructions_changed)
        dialog.exec()

    @Slot(dict, bool, dict)
    def _handle_instructions_changed(self, global_instructions, use_local, local_instructions):
        self.custom_instructions = global_instructions
        if self.current_workspace_name:
            current_ws = self.workspaces.get('workspaces', {}).get(self.current_workspace_name, {})
            current_ws['use_local_templates'] = use_local
            current_ws['local_custom_instructions'] = local_instructions
            self._update_instructions_ui()
            self._save_current_workspace_state()

    def _update_instructions_ui(self):
        if not self.current_workspace_name:
            self.instructions_panel.populate_templates({})
            return

        current_ws = self.workspaces.get('workspaces', {}).get(self.current_workspace_name, {})
        use_local = current_ws.get('use_local_templates', False)
        
        if use_local:
            templates = current_ws.get('local_custom_instructions', {})
        else:
            templates = self.custom_instructions
        self.instructions_panel.populate_templates(templates)

    @Slot(str)
    def _apply_instruction_template(self, template_name):
        if not self.current_workspace_name or not template_name:
            return

        current_ws = self.workspaces.get('workspaces', {}).get(self.current_workspace_name, {})
        use_local = current_ws.get('use_local_templates', False)
        
        if use_local:
            templates = current_ws.get('local_custom_instructions', {})
        else:
            templates = self.custom_instructions

        content = templates.get(template_name, "")
        self.instructions_panel.set_text(content)

    @Slot(str)
    def _update_path_display(self, folder_path):
        self.path_display_label.setText(f"Current Project: {folder_path}")
