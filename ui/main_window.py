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
        # Use Model/View TreePanel for dramatically better performance
        print(f"[WINDOW] 🚀 Creating Model/View TreePanel for high performance...")
        self.tree_panel = create_tree_panel(use_model_view=True, parent=self)
        print(f"[WINDOW] ✅ Model/View TreePanel created successfully")
        # Connect signals (Model/View TreePanel uses same interface)
        if hasattr(self.tree_panel, 'item_checked_changed'):
            self.tree_panel.item_checked_changed.connect(self._on_tree_selection_changed)
        else:
            # Model/View uses selection_changed signal
            self.tree_panel.selection_changed.connect(self._on_tree_selection_changed)
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
    
    def start_isolated_background_scan(self, folder_path: str, scan_settings: dict):
        """Start completely isolated background scan that never blocks the main window."""
        print(f"[WINDOW] 🚀 Starting isolated background scan for: {folder_path}")
        print(f"[WINDOW] 🔒 Main window will remain completely responsive during scan")
        
        # Lazy initialization - create isolated scanner only when needed
        if self.isolated_scanner is None:
            print(f"[WINDOW] 🏗️ Creating isolated scanner (lazy initialization)...")
            from core.isolated_background_scanner import IsolatedBackgroundScanner
            self.isolated_scanner = IsolatedBackgroundScanner()
            self.isolated_scanner_timer = QTimer()
            self.isolated_scanner_timer.timeout.connect(self._check_isolated_scanner_updates)
            print(f"[WINDOW] ✅ Isolated scanner created successfully")
        
        # Stop any existing isolated scan
        self.stop_isolated_background_scan()
        
        # Start the isolated background process
        success = self.isolated_scanner.start_scan(folder_path, scan_settings)
        
        if success:
            print(f"[WINDOW] ✅ Isolated background scan started successfully")
            # Start timer to check for updates every 500ms (non-blocking)
            self.isolated_scanner_timer.start(500)
            print(f"[WINDOW] ⏰ Update timer started (500ms intervals)")
            
            # Show loading state in UI
            self.tree_panel.show_loading(True)
        else:
            print(f"[WINDOW] ❌ Failed to start isolated background scan")
    
    def stop_isolated_background_scan(self):
        """Stop the isolated background scan."""
        print(f"[WINDOW] 🛑 Stopping isolated background scan...")
        
        # Stop the timer (only if it exists)
        if self.isolated_scanner_timer and self.isolated_scanner_timer.isActive():
            self.isolated_scanner_timer.stop()
            print(f"[WINDOW] ⏰ Update timer stopped")
        
        # Stop the isolated scanner (only if it exists)
        if self.isolated_scanner:
            self.isolated_scanner.stop_scan()
            print(f"[WINDOW] ✅ Isolated background scan stopped")
        else:
            print(f"[WINDOW] ℹ️ No isolated scanner to stop (not yet created)")
    
    def _check_isolated_scanner_updates(self):
        """Check for updates from isolated background scanner (called by timer)."""
        # This method is called every 500ms by the timer
        # It's designed to be very lightweight and non-blocking
        
        # Safety check - if scanner doesn't exist, stop the timer
        if not self.isolated_scanner:
            print(f"[WINDOW] ⚠️ Timer running but no isolated scanner exists, stopping timer")
            if self.isolated_scanner_timer:
                self.isolated_scanner_timer.stop()
            return
        
        if not self.isolated_scanner.is_scan_running():
            # Scan finished, stop the timer
            print(f"[WINDOW] 🏁 Isolated scan completed, stopping timer")
            self.isolated_scanner_timer.stop()
            return
        
        # Check for updates (non-blocking)
        update = self.isolated_scanner.get_updates()
        
        if update:
            update_type = update.get('type')
            print(f"[WINDOW] 📥 Received isolated scanner update: {update_type}")
            
            if update_type == 'structure_complete':
                # Initial structure is ready - show it immediately
                items = update.get('items', [])
                files_to_tokenize = update.get('files_to_tokenize', 0)
                
                print(f"[WINDOW] 🏗️ Structure complete: {len(items)} items, {files_to_tokenize} files to tokenize")
                
                # Update UI with structure (this is fast and non-blocking)
                scan_results = {
                    'items': items,
                    'total_files': len([item for item in items if not item[1]]),  # Count files
                    'total_dirs': len([item for item in items if item[1]]),       # Count directories
                    'errors': []
                }
                
                # Update tree panel with initial structure
                self.tree_panel.populate_tree(items, self.current_folder_path)
                print(f"[WINDOW] ✅ UI updated with initial structure")
                
                # Show progress message
                if files_to_tokenize > 0:
                    self.tree_panel.show_loading(True)
                else:
                    self.tree_panel.show_loading(False)
            
            elif update_type == 'progress_update':
                # Progress update - just update the loading message
                completed = update.get('completed', 0)
                total = update.get('total', 0)
                
                if total > 0:
                    progress_percent = (completed / total) * 100
                    self.tree_panel.show_loading(True)  # Show loading during progress
                    print(f"[WINDOW] 📊 Progress: {completed}/{total} ({progress_percent:.1f}%)")
            
            elif update_type == 'scan_complete':
                # Final results available
                items = update.get('items', [])
                completed_files = update.get('completed_files', 0)
                total_files = update.get('total_files', 0)
                
                print(f"[WINDOW] 🎉 Scan complete: {len(items)} items, {completed_files}/{total_files} files tokenized")
                
                # Update UI with final results
                scan_results = {
                    'items': items,
                    'total_files': len([item for item in items if not item[1]]),
                    'total_dirs': len([item for item in items if item[1]]),
                    'errors': []
                }
                
                self.tree_panel.populate_tree(items, self.current_folder_path)
                self.tree_panel.show_loading(False)
                
                # Stop the timer since we're done
                self.isolated_scanner_timer.stop()
                print(f"[WINDOW] ✅ All updates complete, timer stopped")
            
            elif update_type == 'error':
                # Handle errors
                error = update.get('error', 'Unknown error')
                print(f"[WINDOW] ❌ Isolated scanner error: {error}")
                self.tree_panel.show_loading(False)  # Hide loading on error
                self.isolated_scanner_timer.stop()

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
        
        # Stop isolated background scanner
        try:
            self.stop_isolated_background_scan()
            print(f"[WINDOW] ✅ Isolated scanner cleanup completed")
        except Exception as e:
            print(f"[WINDOW] ⚠️ Error during isolated scanner cleanup: {e}")
        
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
