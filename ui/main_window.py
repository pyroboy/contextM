import os
import sys
import pathlib
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QStyle
)
from PySide6.QtCore import Qt, Slot, QTimer, QFileSystemWatcher

# Core components
from core import workspace_manager, selection_manager
from core.workspace_manager import get_default_scan_settings, ensure_complete_scan_settings
from core.streamlined_scanner import StreamlinedScanner
from core.watcher import FileWatcher
from core.optimistic_loader import OptimisticLoader

# UI components
from .widgets.tree_panel import TreePanel
from .widgets.tree_panel_mv import TreePanelMV, create_tree_panel
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
        print(f"[WINDOW] 🪟 MainWindow.__init__ started")
        self.setWindowTitle("Context-M")
        self.setGeometry(100, 100, 1200, 800)
        print(f"[WINDOW] 📐 Window geometry set to 1200x800")

        self.test_mode = test_mode
        self.testing_path = testing_path

        # Initialize workspace and core components FIRST
        print(f"[WINDOW] 💾 Initializing core components...")
        self.workspaces = {}
        self.custom_instructions = {}
        self.current_workspace_name = None
        self.current_folder_path = None
        self.current_scan_settings = None
        # Use ONLY the streamlined scanner - no complex initialization
        self.streamlined_scanner = StreamlinedScanner(self)
        self.file_watcher = None  # Only file watcher allowed for live updates
        self._scan_in_progress = False  # Prevent double scanner execution
        print(f"[WINDOW] ✅ Core components initialized")

        # Initialize UI components
        print(f"[WINDOW] 🎨 Starting UI initialization...")
        self._setup_ui()
        print(f"[WINDOW] ✅ UI initialization completed")
        
        # Initialize controllers
        print(f"[WINDOW] 🎮 Starting controllers initialization...")
        self.workspace_ctl = WorkspaceController(self)
        self.scan_ctl = ScanController(self)
        self.sel_ctl = SelectionController(self)
        print(f"[WINDOW] ✅ Controllers initialization completed")

        # Selection Groups
        self.selection_groups = {}
        self.active_selection_group = "Default"

        self._connect_signals()

        # Add auto-save timer for workspace state
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self._auto_save_workspace_state)
        self.auto_save_timer.start(30000)  # Save every 30 seconds
        print(f"[WINDOW] ⏰ Auto-save timer started (30 second intervals)")

        # In normal mode, load data and the last active workspace. In test mode, wait for the test to decide.
        if not test_mode:
            self.load_initial_data()
            print(f"[DEBUG] In __init__, after load_initial_data: {self.workspaces}")
            last_active = self.workspaces.get("last_active_workspace", "Default")
            print(f"[WINDOW] 🔄 Loading last active workspace: {last_active}")
            print(f"[WINDOW] 📱 Window is visible: {self.isVisible()}")
            print(f"[WINDOW] 📱 Window state: {self.windowState()}")
            self.workspace_ctl.switch(last_active, initial_load=True)
            print(f"[WINDOW] ✅ Workspace switch initiated")

    def load_initial_data(self):
        """Load workspaces with proper structure initialization."""
        self.workspaces = workspace_manager.load_workspaces(base_path=self.testing_path)
        
        # Ensure proper structure
        if not isinstance(self.workspaces, dict):
            self.workspaces = {'workspaces': {}, 'last_active_workspace': 'Default'}
        
        if 'workspaces' not in self.workspaces:
            self.workspaces['workspaces'] = {}
        
        if 'last_active_workspace' not in self.workspaces:
            self.workspaces['last_active_workspace'] = 'Default'
        
        # Always ensure Default workspace exists
        if 'Default' not in self.workspaces['workspaces']:
            self.workspaces['workspaces']['Default'] = {
                "folder_path": None,
                "scan_settings": get_default_scan_settings(),
                "instructions": "",
                "active_selection_group": "Default",
                "selection_groups": {
                    "Default": {"description": "Default selection", "checked_paths": []}
                }
            }
        
        self.custom_instructions = workspace_manager.load_custom_instructions(base_path=self.testing_path)
        print(f"[MAIN] 📁 Loaded {len(self.workspaces['workspaces'])} workspaces: {list(self.workspaces['workspaces'].keys())}")

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
        # Use Model/View TreePanel for dramatically better performance
        print(f"[WINDOW] 🚀 Creating Model/View TreePanel for high performance...")
        self.tree_panel = create_tree_panel(use_model_view=True, parent=self)
        print(f"[WINDOW] ✅ Model/View TreePanel created successfully")
        # Connect signals (Model/View TreePanel uses same interface)
        if hasattr(self.tree_panel, 'item_checked_changed'):
            self.tree_panel.item_checked_changed.connect(self._on_tree_selection_changed)
            self.tree_panel.item_checked_changed.connect(self.update_aggregation_and_tokens)
        else:
            # Model/View uses selection_changed signal
            self.tree_panel.selection_changed.connect(self._on_tree_selection_changed)
            self.tree_panel.selection_changed.connect(self.update_aggregation_and_tokens)
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

        # Connect new workspace signals
        self.workspace_ctl.workspace_created.connect(self._on_workspace_created)
        self.workspace_ctl.workspace_deleted.connect(self._on_workspace_deleted)

        # Core components
        self.streamlined_scanner.scan_started.connect(lambda: self.tree_panel.show_loading(True))
        self.streamlined_scanner.scan_progress.connect(self._on_scan_progress)
        self.streamlined_scanner.scan_complete.connect(self._on_scan_complete)
        self.streamlined_scanner.scan_error.connect(self._on_scan_error)
        
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

    def _on_scan_progress(self, completed: int, total: int):
        """Handle scan progress updates from streamlined scanner."""
        if total > 0:
            progress_percent = (completed / total) * 100
            self.statusBar().showMessage(f"Tokenizing files: {completed}/{total} ({progress_percent:.1f}%)")
            print(f"[STREAMLINED] 📊 Progress: {completed}/{total} ({progress_percent:.1f}%)")
    
    def _on_scan_complete(self, items: list):
        """Handle scan completion from streamlined scanner."""
        print(f"[STREAMLINED] 🎉 Scan complete: {len(items)} items")
        
        # Reset scan flag to allow future scans
        self._scan_in_progress = False
        
        # Update tree panel with results
        self.tree_panel.populate_tree(items, self.current_folder_path)
        self.tree_panel.show_loading(False)
        
        # Update aggregation and tokens
        self.update_aggregation_and_tokens()
        
        # Show completion message
        file_count = len([item for item in items if not item[1]])  # Count files
        self.statusBar().showMessage(f"Scan complete: {len(items)} items, {file_count} files tokenized", 3000)
    
    def _on_scan_error(self, error: str):
        """Handle scan errors from streamlined scanner."""
        print(f"[STREAMLINED] ❌ Scan error: {error}")
        
        # Reset scan flag to allow future scans
        self._scan_in_progress = False
        
        self.tree_panel.show_loading(False)
        self.statusBar().showMessage(f"Scan error: {error}", 5000)

    def closeEvent(self, event):
        """Handle the window close event by ensuring graceful shutdown of background processes."""
        self._update_current_workspace_state()
        self._save_current_workspace_state()
        self._stop_file_watcher()
        # Clean up streamlined scanner
        if self.streamlined_scanner:
            self.streamlined_scanner.cleanup()
        event.accept()

    def _update_current_workspace_state(self):
        """Update current workspace state with complete data validation."""
        if not self.current_workspace_name:
            print("[STATE] ⚠️ No current workspace name set")
            return
            
        # Clean workspace name (remove any display suffixes)
        clean_workspace_name = self.current_workspace_name.split(' (')[0].strip()
        
        if clean_workspace_name not in self.workspaces.get('workspaces', {}):
            print(f"[STATE] ⚠️ Cannot update state - invalid workspace: {self.current_workspace_name}")
            return

        current_ws = self.workspaces['workspaces'][clean_workspace_name]
        if not isinstance(current_ws, dict):
            current_ws = {}
            self.workspaces['workspaces'][clean_workspace_name] = current_ws

        # Ensure complete scan_settings are always saved
        current_ws["folder_path"] = self.current_folder_path
        current_ws["scan_settings"] = ensure_complete_scan_settings(self.current_scan_settings)
        current_ws["instructions"] = self.instructions_panel.get_text()
        current_ws['active_selection_group'] = self.active_selection_group

        if self.active_selection_group in self.selection_groups:
            checked_paths = self.tree_panel.get_checked_paths(relative=True)
            if isinstance(self.selection_groups[self.active_selection_group], dict):
                self.selection_groups[self.active_selection_group]["checked_paths"] = checked_paths
        current_ws['selection_groups'] = self.selection_groups
        
        print(f"[STATE] ✅ Updated workspace state: {clean_workspace_name}")

    def _save_current_workspace_state(self):
        if self.workspaces:
            workspace_manager.save_workspaces(self.workspaces)

    def _switch_workspace(self, workspace_name, initial_load=False):
        """Atomic workspace switch with complete data validation and error handling."""
        print(f"[WORKSPACE_SWITCH] 🔄 Initiating atomic switch to: '{workspace_name}' (initial_load: {initial_load})")
        
        try:
            # Phase 1: Pre-Switch State Capture
            if not initial_load and self.current_workspace_name:
                print(f"[WORKSPACE_SWITCH] 💾 Saving current workspace state: {self.current_workspace_name}")
                self._update_current_workspace_state()
                self._save_current_workspace_state()
                print(f"[WORKSPACE_SWITCH] ✅ Current workspace state saved")
            
            # Phase 2: Workspace Data Validation
            if not self._validate_workspace_exists(workspace_name):
                if workspace_name == "Default":
                    print(f"[WORKSPACE_SWITCH] 🏗️ Creating missing Default workspace")
                    self._create_default_workspace()
                else:
                    print(f"[WORKSPACE_SWITCH] ❌ Workspace '{workspace_name}' does not exist")
                    return False
            
            # Phase 3: Atomic Workspace Load
            workspace_data = self._load_workspace_data(workspace_name)
            if not workspace_data:
                print(f"[WORKSPACE_SWITCH] ❌ Failed to load workspace data for '{workspace_name}'")
                return False
            
            # Phase 4: Apply Workspace State (All-or-Nothing)
            success = self._apply_workspace_state(workspace_name, workspace_data)
            if not success:
                print(f"[WORKSPACE_SWITCH] ❌ Failed to apply workspace state for '{workspace_name}'")
                return False
            
            print(f"[WORKSPACE_SWITCH] ✅ Atomic workspace switch to '{workspace_name}' completed successfully")
            return True
            
        except Exception as e:
            print(f"[WORKSPACE_SWITCH] ❌ Error during workspace switch: {e}")
            return False
    
    def _validate_workspace_exists(self, workspace_name):
        """Validate that workspace exists and has proper structure."""
        workspaces = self.workspaces.get('workspaces', {})
        return workspace_name in workspaces
    
    def _create_default_workspace(self):
        """Create Default workspace with proper structure."""
        if 'workspaces' not in self.workspaces:
            self.workspaces['workspaces'] = {}
        
        self.workspaces['workspaces']['Default'] = {
            "folder_path": None,
            "scan_settings": get_default_scan_settings(),
            "instructions": "",
            "active_selection_group": "Default",
            "selection_groups": {
                "Default": {"description": "Default selection", "checked_paths": []}
            }
        }
        print(f"[WORKSPACE_SWITCH] ✅ Default workspace created with complete structure")
    
    def _load_workspace_data(self, workspace_name):
        """Load and validate complete workspace data."""
        try:
            workspace_data = self.workspaces.get('workspaces', {}).get(workspace_name, {})
            
            # Data integrity validation
            validated_data = {
                "folder_path": workspace_data.get("folder_path"),
                "scan_settings": ensure_complete_scan_settings(workspace_data.get("scan_settings")),
                "instructions": workspace_data.get("instructions", ""),
                "active_selection_group": workspace_data.get("active_selection_group", "Default"),
                "selection_groups": workspace_data.get("selection_groups", {
                    "Default": {"description": "Default selection", "checked_paths": []}
                })
            }
            
            print(f"[WORKSPACE_SWITCH] ✅ Workspace data loaded and validated for '{workspace_name}'")
            print(f"[WORKSPACE_SWITCH] 📁 Folder: {validated_data['folder_path']}")
            print(f"[WORKSPACE_SWITCH] ⚙️ Scan settings: {validated_data['scan_settings']}")
            
            return validated_data
            
        except Exception as e:
            print(f"[WORKSPACE_SWITCH] ❌ Error loading workspace data: {e}")
            return None
    
    def _apply_workspace_state(self, workspace_name, workspace_data):
        """Apply workspace state atomically with error handling."""
        try:
            # Set workspace identity
            self.current_workspace_name = workspace_name
            self.workspace_label.setText(f"Workspace: {workspace_name}")
            
            # Apply folder path and scan settings
            self.current_folder_path = workspace_data["folder_path"]
            self.current_scan_settings = workspace_data["scan_settings"]
            
            # Update path display
            display_path = self.current_folder_path if self.current_folder_path else "No folder selected."
            self._update_path_display(display_path)
            
            # Apply instructions
            self.instructions_panel.set_text(workspace_data["instructions"])
            
            # Apply selection groups
            self.selection_groups = selection_manager.load_groups(workspace_data)
            self.active_selection_group = workspace_data["active_selection_group"]
            self.selection_manager_panel.update_groups(list(self.selection_groups.keys()), self.active_selection_group)
            
            # Trigger workspace switched callback
            self._on_workspace_switched(workspace_name)
            
            # Handle folder scanning with validation
            if self.current_folder_path and self.current_scan_settings:
                if self._validate_folder_exists(self.current_folder_path):
                    print(f"[WORKSPACE_SWITCH] 🚀 Starting scan for validated folder: {self.current_folder_path}")
                    active_group_data = self.selection_groups.get(self.active_selection_group, {})
                    checked_paths_to_restore = active_group_data.get("checked_paths", [])
                    self.scan_ctl.start(self.current_folder_path, self.current_scan_settings, checked_paths_to_restore)
                else:
                    print(f"[WORKSPACE_SWITCH] ⚠️ Folder path does not exist: {self.current_folder_path}")
                    self._handle_missing_folder()
            else:
                print(f"[WORKSPACE_SWITCH] ℹ️ No folder or scan settings - workspace ready for folder selection")
            
            return True
            
        except Exception as e:
            print(f"[WORKSPACE_SWITCH] ❌ Error applying workspace state: {e}")
            return False
    
    def _validate_folder_exists(self, folder_path):
        """Validate that the assigned folder path exists."""
        if not folder_path:
            return False
        import os
        return os.path.exists(folder_path) and os.path.isdir(folder_path)
    
    def _handle_missing_folder(self):
        """Handle case where workspace folder doesn't exist."""
        from PySide6.QtWidgets import QMessageBox
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Folder Not Found")
        msg.setText(f"The folder assigned to this workspace no longer exists:\n\n{self.current_folder_path}")
        msg.setInformativeText("Would you like to select a new folder for this workspace?")
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg.setDefaultButton(QMessageBox.StandardButton.Yes)
        
        if msg.exec() == QMessageBox.StandardButton.Yes:
            # Clear current folder and let user select new one
            self.current_folder_path = None
            self._update_path_display("No folder selected.")
            print(f"[WORKSPACE_SWITCH] 🔄 User will select new folder for workspace")
        else:
            # Keep the invalid path but don't scan
            print(f"[WORKSPACE_SWITCH] ⚠️ Keeping invalid folder path - no scanning will occur")
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
        print(f"[PERFORMANCE] Starting workspace switch to '{workspace_name}'")
        start_time = __import__('time').time()
        
        self._update_path_display(self.current_folder_path or "No folder selected.")
        self.refresh_button.setEnabled(bool(self.current_folder_path))

        if self.current_folder_path:
            print(f"[STREAMLINED] 🚀 Starting streamlined scan for: {self.current_folder_path}")
            
            # Prevent double execution
            if self._scan_in_progress:
                print(f"[STREAMLINED] ⚠️ Scan already in progress, skipping duplicate")
                return
            
            self._scan_in_progress = True
            
            # Clear tree and show loading
            self.tree_panel.clear_tree()
            self.tree_panel.show_loading(True)
            
            # Start file watcher for live updates (only allowed thread)
            self._start_file_watcher()
            
            # Use ONLY the streamlined scanner - no complex layers
            scan_start = __import__('time').time()
            success = self.streamlined_scanner.start_scan(self.current_folder_path, self.current_scan_settings)
            
            if success:
                setup_time = (__import__('time').time() - scan_start) * 1000
                print(f"[STREAMLINED] ⚡ Scan started in {setup_time:.2f}ms")
                self.statusBar().showMessage(f"Scanning {self.current_folder_path}...")
            else:
                print(f"[STREAMLINED] ❌ Failed to start scan")
                self.tree_panel.show_loading(False)
                self.statusBar().showMessage("Failed to start scan", 3000)
                self._scan_in_progress = False
        else:
            print(f"[PERFORMANCE] No folder path - clearing tree")
            self.tree_panel.clear_tree()
            self.tree_panel.show_loading(False)
            self.update_aggregation_and_tokens()
            self._stop_file_watcher()
            
        total_time = (__import__('time').time() - start_time) * 1000
        print(f"[PERFORMANCE] Workspace switch completed in {total_time:.2f}ms")
    
    def showEvent(self, event):
        """Override showEvent to track when window actually becomes visible."""
        print(f"[WINDOW] 👁️ showEvent triggered - window is becoming visible!")
        super().showEvent(event)
        print(f"[WINDOW] ✅ Window is now visible: {self.isVisible()}")
        print(f"[WINDOW] 📊 Window geometry: {self.geometry()}")
        print(f"[WINDOW] 📊 Window size: {self.size()}")
    
    def _start_deferred_validation(self):
        """Start validation scan after UI is fully loaded and responsive."""
        import time
        start_time = time.time()
        
        print(f"[PERFORMANCE] ⏱️ UI is now responsive! Skipping validation scan to maintain responsiveness.")
        self.statusBar().showMessage("UI loaded - validation disabled for maximum responsiveness", 3000)
        
        # SKIP VALIDATION SCAN ENTIRELY to maintain UI responsiveness
        # The optimistic loading already shows the file tree from cached data
        # Users can manually refresh if they need up-to-date validation
        
        defer_time = (time.time() - start_time) * 1000
        print(f"[PERFORMANCE] Deferred validation skipped in {defer_time:.2f}ms - UI remains responsive")

    def _handle_optimistic_tree_ready(self, items, root_path):
        """Handle optimistic tree structure being ready for immediate display."""
        self.statusBar().showMessage("Loading file tree...", 2000)
        self.tree_panel.populate_tree_optimistic(items, root_path)
        
        # Apply checked state from the active selection group
        if self.active_selection_group in self.selection_groups:
            group_data = self.selection_groups[self.active_selection_group]
            if isinstance(group_data, dict):
                checked_paths = group_data.get("checked_paths", [])
                self.tree_panel.set_checked_paths(checked_paths, relative=True)
        
        self.sel_ctl.update_ui()
        self._update_instructions_ui()

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
                self.file_watcher.fs_event_batch.connect(self.tree_panel.update_from_fs_events)
                self.file_watcher.fs_event_batch.connect(self.file_changes_panel.update_with_fs_events)
                self.file_watcher.file_token_changed.connect(self.file_changes_panel.add_change_entry)
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
        checked = self.tree_panel.get_checked_paths(relative=True) # This is correct, the wrapper handles it
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
    
    def closeEvent(self, event):
        """Handle the window close event by ensuring graceful shutdown and saving workspace state."""
        print(f"[WINDOW] 🚪 Application closing, saving workspace state...")
        
        # Save current workspace state before closing
        if self.current_workspace_name:
            print(f"[WINDOW] 💾 Saving workspace: {self.current_workspace_name}")
            try:
                self._update_current_workspace_state()
                self._save_current_workspace_state()
                print(f"[WINDOW] ✅ Workspace state saved")
            except Exception as e:
                print(f"[WINDOW] ❌ Error saving workspace state: {e}")
                import traceback
                traceback.print_exc()
        
        # Stop file watcher
        try:
            self._stop_file_watcher()
            print(f"[WINDOW] ✅ File watcher cleanup completed")
        except Exception as e:
            print(f"[WINDOW] ⚠️ Error during file watcher cleanup: {e}")
        
        # Stop streamlined scanner
        try:
            if hasattr(self, 'streamlined_scanner') and self.streamlined_scanner:
                self.streamlined_scanner.cleanup()
                print(f"[WINDOW] ✅ Streamlined scanner stopped")
        except Exception as e:
            print(f"[WINDOW] ⚠️ Error stopping scanner: {e}")
        
        print(f"[WINDOW] 👋 Application cleanup completed")
        event.accept()

    def _update_current_workspace_state(self):
        """Update the current workspace state with all current data."""
        if not self.current_workspace_name or self.current_workspace_name not in self.workspaces.get('workspaces', {}):
            print(f"[STATE] ⚠️ Cannot update state - invalid workspace: {self.current_workspace_name}")
            return

        current_ws = self.workspaces['workspaces'][self.current_workspace_name]
        
        # Ensure we have a proper dict structure
        if not isinstance(current_ws, dict):
            current_ws = {}
            self.workspaces['workspaces'][self.current_workspace_name] = current_ws

        # Save all current state
        current_ws["folder_path"] = self.current_folder_path
        current_ws["scan_settings"] = self.current_scan_settings
        current_ws["instructions"] = self.instructions_panel.get_text()
        current_ws['active_selection_group'] = self.active_selection_group
        
        # Get checked paths from tree
        checked_paths = self.tree_panel.get_checked_paths(relative=True)
        current_ws['selection_groups'] = self.selection_groups
        
        # Update active selection group with current checked paths
        if self.active_selection_group in self.selection_groups:
            self.selection_groups[self.active_selection_group]["checked_paths"] = checked_paths
        
        print(f"[STATE] ✅ Workspace state updated: {len(checked_paths)} checked files")

    def _save_current_workspace_state(self):
        """Save workspace state with debug logging."""
        if not self.workspaces:
            print("[SAVE] ⚠️ No workspaces to save")
            return
        
        try:
            print(f"[SAVE] 💾 Saving workspaces...")
            workspace_manager.save_workspaces(self.workspaces, base_path=self.testing_path)
            print("[SAVE] ✅ Workspaces saved successfully")
        except Exception as e:
            print(f"[SAVE] ❌ Failed to save workspaces: {e}")
            import traceback
            traceback.print_exc()

    @Slot()
    def _auto_save_workspace_state(self):
        """Auto-save workspace state periodically."""
        if self.current_workspace_name and self.workspaces:
            try:
                print(f"[AUTO_SAVE] 💾 Auto-saving workspace: {self.current_workspace_name}")
                self._update_current_workspace_state()
                self._save_current_workspace_state()
                print(f"[AUTO_SAVE] ✅ Auto-save completed")
            except Exception as e:
                print(f"[AUTO_SAVE] ❌ Auto-save failed: {e}")

    @Slot(str)
    def _on_workspace_created(self, workspace_name):
        """Handle workspace creation."""
        print(f"[MAIN] 🎉 Workspace created: {workspace_name}")
        # UI already updated by workspace manager

    @Slot(str)
    def _on_workspace_deleted(self, workspace_name):
        """Handle workspace deletion."""
        print(f"[MAIN] 🗑️ Workspace deleted: {workspace_name}")
        # If current workspace was deleted, switch to Default
        if workspace_name == self.current_workspace_name:
            self.workspace_ctl.switch("Default")

    @Slot()
    def _on_tree_selection_changed(self):
        """Handle tree panel selection changes and save workspace state."""
        if self.current_workspace_name and self.workspaces:
            try:
                print(f"[TREE] 📋 File selection changed, saving workspace state...")
                self._update_current_workspace_state()
                self._save_current_workspace_state()
                print(f"[TREE] ✅ Workspace state saved after selection change")
            except Exception as e:
                print(f"[TREE] ❌ Error saving workspace state after selection change: {e}")

    @Slot()
    def update_aggregation_and_tokens(self):
        """Generate aggregation from current TreeView selections."""
        try:
            print("[AGGREGATION] 🔄 Generating content from selections...")
            
            # Get checked paths from tree panel
            if hasattr(self.tree_panel, 'get_checked_paths'):
                checked = self.tree_panel.get_checked_paths(relative=True)
                print(f"[AGGREGATION] ✅ get_checked_paths method found, returned {len(checked)} files")
            else:
                checked = []
                print(f"[AGGREGATION] ❌ get_checked_paths method NOT found on tree_panel")
            
            print(f"[AGGREGATION] 📁 {len(checked)} files selected")
            if checked:
                print(f"[AGGREGATION] 📋 Selected files: {checked[:5]}{'...' if len(checked) > 5 else ''}")
            
            if not checked:
                # No files selected - clear aggregation
                if hasattr(self, 'aggregation_view'):
                    self.aggregation_view.set_content("No files selected", 0)
                print("[AGGREGATION] ℹ️ No files selected - cleared aggregation")
                return
            
            # Generate file tree string
            tree_str = self._generate_file_tree_string(checked)
            
            # Get file content and tokens
            content, tokens = self._get_aggregated_content(checked)
            
            # Combine with system prompt
            system_prompt = ""
            if hasattr(self, 'instructions_panel'):
                system_prompt = self.instructions_panel.get_text()
            
            if system_prompt:
                final_content = f"--- System Prompt ---\n{system_prompt}\n\n--- File Tree ---\n{tree_str}\n\n---\n\n{content}"
            else:
                final_content = f"--- File Tree ---\n{tree_str}\n\n---\n\n{content}"
            
            # Update aggregation view
            if hasattr(self, 'aggregation_view'):
                self.aggregation_view.set_content(final_content, tokens)
            
            print(f"[AGGREGATION] ✅ Generated {tokens} tokens from {len(checked)} files")
            
        except Exception as e:
            print(f"[AGGREGATION] ❌ Error generating aggregation: {e}")
            import traceback
            traceback.print_exc()

    def _generate_file_tree_string(self, checked_paths):
        """Generate a file tree string from checked paths."""
        if not checked_paths or not self.current_folder_path:
            return "No files selected"
        
        try:
            # Simple tree representation
            tree_lines = []
            tree_lines.append(f"Project: {os.path.basename(self.current_folder_path)}")
            
            # Group by directory
            dirs = {}
            for path in sorted(checked_paths):
                dir_name = os.path.dirname(path) or "."
                if dir_name not in dirs:
                    dirs[dir_name] = []
                dirs[dir_name].append(os.path.basename(path))
            
            # Build tree structure
            for dir_name in sorted(dirs.keys()):
                if dir_name == ".":
                    tree_lines.append("├── (root)")
                else:
                    tree_lines.append(f"├── {dir_name}/")
                
                files = dirs[dir_name]
                for i, file_name in enumerate(files):
                    if i == len(files) - 1:
                        tree_lines.append(f"│   └── {file_name}")
                    else:
                        tree_lines.append(f"│   ├── {file_name}")
            
            return "\n".join(tree_lines)
            
        except Exception as e:
            print(f"[TREE_GEN] ❌ Error generating tree: {e}")
            return "Error generating file tree"

    def _get_aggregated_content(self, checked_paths):
        """Get aggregated content from checked file paths using cached token counts."""
        if not checked_paths or not self.current_folder_path:
            return "", 0
        
        aggregated_parts = []
        total_tokens = 0
        
        try:
            # Process files in consistent order
            for relative_path in sorted(checked_paths):
                absolute_path = os.path.join(self.current_folder_path, relative_path)
                
                if not os.path.isfile(absolute_path):
                    continue
                
                try:
                    # Get file extension for language
                    _, ext = os.path.splitext(relative_path)
                    language = ext[1:] if ext else ""
                    
                    # Read file content
                    with open(absolute_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    # Build markdown section
                    aggregated_parts.append(f"{relative_path}")
                    aggregated_parts.append(f"```{language}")
                    aggregated_parts.append(content)
                    aggregated_parts.append("```\n")
                    
                    # Use cached token count from tree model for consistency
                    token_count = self._get_cached_token_count(absolute_path)
                    total_tokens += token_count
                    
                    print(f"[AGGREGATION] 📊 {relative_path}: {token_count} tokens (cached)")
                    
                except Exception as e:
                    aggregated_parts.append(f"[Error reading {relative_path}: {e}]\n")
                    print(f"[AGGREGATION] ⚠️ Error reading {relative_path}: {e}")
            
            return "\n".join(aggregated_parts), total_tokens
            
        except Exception as e:
            print(f"[AGGREGATION] ❌ Error getting content: {e}")
            return "Error generating content", 0
    
    def _normalize_path_for_cache(self, path: str) -> str:
        """Normalize path for consistent cache lookup.
        
        Ensures consistent path format between storage and retrieval:
        - Converts to absolute path
        - Normalizes path separators
        - Uses forward slashes for consistency
        """
        try:
            # Convert to absolute path and normalize
            abs_path = os.path.abspath(path)
            # Convert to forward slashes for consistent storage/retrieval
            normalized = abs_path.replace('\\', '/')
            return normalized
        except Exception:
            return path.replace('\\', '/')
    
    def _get_cached_token_count(self, absolute_path: str) -> int:
        """Get cached token count using direct path mapping for consistency.
        
        This fixes the token cache miss issue by using consistent path normalization
        and direct dictionary lookup instead of complex tree traversal.
        
        Args:
            absolute_path: Absolute path to the file
            
        Returns:
            Token count from cache, or calculated if not cached
        """
        try:
            # Normalize path for consistent lookup
            normalized_path = self._normalize_path_for_cache(absolute_path)
            
            # Try TreePanelMV's direct token cache first (most efficient)
            if hasattr(self.tree_panel, 'get_token_cache'):
                tree_cache = self.tree_panel.get_token_cache()
                if normalized_path in tree_cache:
                    cached_count = tree_cache[normalized_path]
                    print(f"[TOKEN_CACHE] ✅ TreePanel cache hit for {os.path.basename(absolute_path)}: {cached_count}")
                    return cached_count
            
            # Try main window's direct token cache (fallback)
            if hasattr(self, '_token_cache') and normalized_path in self._token_cache:
                cached_count = self._token_cache[normalized_path]
                print(f"[TOKEN_CACHE] ✅ MainWindow cache hit for {os.path.basename(absolute_path)}: {cached_count}")
                return cached_count
            
            # Try tree model lookup with normalized path (compatibility)
            if hasattr(self.tree_panel, 'file_tree_view') and hasattr(self.tree_panel.file_tree_view, 'model'):
                model = self.tree_panel.file_tree_view.model
                
                # Search through path_to_node mapping with normalized paths
                if hasattr(model, 'path_to_node'):
                    # Try multiple path formats for compatibility
                    path_variants = [
                        normalized_path,
                        absolute_path,
                        absolute_path.replace('\\', '/'),
                        os.path.normpath(absolute_path)
                    ]
                    
                    for path_variant in path_variants:
                        if path_variant in model.path_to_node:
                            node = model.path_to_node[path_variant]
                            if node and hasattr(node, 'token_count') and node.token_count > 0:
                                cached_count = node.token_count
                                print(f"[TOKEN_CACHE] ✅ Model cache hit for {os.path.basename(absolute_path)}: {cached_count}")
                                # Store in direct cache for future lookups
                                if not hasattr(self, '_token_cache'):
                                    self._token_cache = {}
                                self._token_cache[normalized_path] = cached_count
                                return cached_count
            
            print(f"[TOKEN_CACHE] ⚠️ No cached token found for {os.path.basename(absolute_path)}")
            
            # Fallback: calculate tokens using same method as BG_scanner
            print(f"[TOKEN_CACHE] 🔄 Calculating tokens for {os.path.basename(absolute_path)}")
            with open(absolute_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Use the same token calculation as BG_scanner for consistency
            from core.helpers import calculate_tokens
            calculated_count = calculate_tokens(content)
            
            # Cache the calculated result for future lookups
            if not hasattr(self, '_token_cache'):
                self._token_cache = {}
            self._token_cache[normalized_path] = calculated_count
            
            return calculated_count
            
        except Exception as e:
            print(f"[TOKEN_CACHE] ❌ Error getting token count for {absolute_path}: {e}")
            # Last resort: simple approximation
            try:
                with open(absolute_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                return len(content.split()) + len(content) // 4
            except:
                return 0
    
    def _verify_token_consistency(self):
        """Debug method to verify token count consistency between tree view and aggregation."""
        try:
            print("[TOKEN_VERIFICATION] =====================================")
            
            # Get checked paths
            if hasattr(self.tree_panel, 'get_checked_paths'):
                checked_paths = self.tree_panel.get_checked_paths(relative=False)
                print(f"[TOKEN_VERIFICATION] Checking {len(checked_paths)} files")
                
                tree_total = 0
                agg_total = 0
                
                for absolute_path in checked_paths:
                    # Get tree token count
                    tree_count = self._get_cached_token_count(absolute_path)
                    tree_total += tree_count
                    
                    # Get aggregation token count (for comparison)
                    try:
                        with open(absolute_path, 'r', encoding='utf-8', errors='replace') as f:
                            content = f.read()
                        old_calc = len(content.split()) + len(content) // 4
                        agg_total += old_calc
                        
                        filename = os.path.basename(absolute_path)
                        if tree_count != old_calc:
                            print(f"[TOKEN_VERIFICATION] ⚠️ {filename}: Tree={tree_count}, Old={old_calc} (diff: {tree_count - old_calc})")
                        else:
                            print(f"[TOKEN_VERIFICATION] ✅ {filename}: {tree_count} tokens (consistent)")
                            
                    except Exception as e:
                        print(f"[TOKEN_VERIFICATION] ❌ Error reading {absolute_path}: {e}")
                
                print(f"[TOKEN_VERIFICATION] Tree total: {tree_total} tokens")
                print(f"[TOKEN_VERIFICATION] Old calc total: {agg_total} tokens")
                print(f"[TOKEN_VERIFICATION] Difference: {tree_total - agg_total} tokens")
                
                if tree_total == agg_total:
                    print("[TOKEN_VERIFICATION] ✅ Token counts are consistent!")
                else:
                    print("[TOKEN_VERIFICATION] ⚠️ Token count mismatch detected!")
                    
            else:
                print("[TOKEN_VERIFICATION] ❌ get_checked_paths method not found")
                
            print("[TOKEN_VERIFICATION] =====================================")
            
        except Exception as e:
            print(f"[TOKEN_VERIFICATION] ❌ Error during verification: {e}")
            import traceback
            traceback.print_exc()
