import os
import sys
import time
import pathlib
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QStyle
)
from PySide6.QtCore import Qt, Slot, QTimer, QFileSystemWatcher, QThread, Signal, QMutex

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


class AggregationWorker(QThread):
    """Background worker that aggregates content without emitting large payloads.

    Uses a zero-copy handover: the aggregated text is stored on the worker
    instance in `result_text` and only a small status + token count are sent
    through the Qt signals.
    """

    # finished_signal emits success status (True/False) and total tokens, NO TEXT
    finished_signal = Signal(bool, int)
    progress_signal = Signal(int)
    token_progress_signal = Signal(int)

    def __init__(self, folder_path, checked_paths, system_prompt, parent=None):
        super().__init__(parent)
        self.folder_path = folder_path
        self.checked_paths = checked_paths
        self.system_prompt = system_prompt
        self._is_cancelled = False

        # Result storage (read from main thread after completion)
        self.result_text = ""
        self.result_file_path = ""
        self.result_file_paths = []
        self.result_chunk_tokens = []
        self.error_message = ""

    def run(self):
        import os
        import time
        from ui.helpers.aggregation_helper import generate_file_tree_string
        from core.helpers import calculate_tokens

        try:
            if not self.checked_paths:
                self.result_text = "No files selected"
                self.finished_signal.emit(True, 0)
                return

            if self._is_cancelled:
                return

            # 1. Tree generation
            tree_start = time.time()
            tree_str = generate_file_tree_string(self.folder_path, self.checked_paths)
            tree_time = (time.time() - tree_start) * 1000
            print(f"[AGG_WORKER] 🌳 Tree generation took {tree_time:.2f}ms")
            # Early UI nudge so users don't see 0% forever
            self.progress_signal.emit(1)
            self.token_progress_signal.emit(0)
            self.msleep(1)

            import tempfile
            total_tokens = 0

            sorted_paths = sorted(list(self.checked_paths))
            total_files = len(sorted_paths)

            # Pre-scan sizes for percent based on bytes (skip for huge selections)
            total_bytes = 0
            if total_files <= 300:
                for p in sorted_paths:
                    ap = os.path.join(self.folder_path, p)
                    try:
                        if os.path.isfile(ap):
                            total_bytes += os.path.getsize(ap)
                    except Exception:
                        pass
            processed_bytes = 0

            max_chunk_tokens = 600000
            current_chunk_tokens = 0
            fd, temp_path = tempfile.mkstemp(suffix=".agg.txt")
            os.close(fd)
            self.result_file_path = temp_path
            self.result_file_paths = [temp_path]

            def write_header(out_file):
                """Write header and return accurate token count."""
                header = ""
                if self.system_prompt:
                    header += f"--- System Prompt ---\n{self.system_prompt}\n\n"
                header += f"--- File Tree ---\n{tree_str}\n\n---\n"
                out_file.write(header)
                return calculate_tokens(header)

            out = open(temp_path, "w", encoding="utf-8", errors="replace")
            current_chunk_tokens = write_header(out)

            agg_loop_start = time.time()
            files_processed = 0

            for i, rel_path in enumerate(sorted_paths):
                if self._is_cancelled:
                    out.close()
                    return
                    
                # Update progress
                if total_files > 0 and (i % 10 == 0 or i == 0):
                    percent = int((processed_bytes / total_bytes) * 100) if total_bytes > 0 else int((i / total_files) * 100)
                    self.progress_signal.emit(percent)
                    self.token_progress_signal.emit(total_tokens)
                    self.msleep(1)

                abs_path = os.path.join(self.folder_path, rel_path)
                if not os.path.isfile(abs_path):
                    continue
                
                # Skip known binary files that would break clipboard with null bytes
                binary_patterns = {'.DS_Store', '.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.obj'}
                if any(abs_path.endswith(pattern) for pattern in binary_patterns):
                    print(f"[AGG_WORKER] ⏭️ Skipping binary file: {rel_path}")
                    continue

                try:
                    # Read entire file content first
                    # Use errors='replace' to handle binary content gracefully
                    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
                        file_content = f.read()
                    
                    # Additional check: Skip if file contains too many null bytes (likely binary)
                    null_byte_count = file_content.count('\x00')
                    if null_byte_count > 10:  # More than 10 null bytes = probably binary
                        print(f"[AGG_WORKER] ⏭️ Skipping binary-like file (has {null_byte_count} null bytes): {rel_path}")
                        continue
                    
                    # Skip empty files
                    if not file_content:
                        continue
                    
                    # Calculate accurate token count for this file
                    file_tokens = calculate_tokens(file_content)
                    
                    # Calculate file size for progress tracking
                    file_bytes = len(file_content.encode("utf-8", errors="ignore"))
                    processed_bytes += file_bytes
                    
                    # Prepare file header and footer
                    _, ext = os.path.splitext(rel_path)
                    lang = ext[1:].lower() if ext else ""
                    file_header = f"\n`{rel_path}`\n```{lang}\n"
                    file_footer = "\n```\n"
                    
                    # Calculate tokens for header and footer
                    header_footer_tokens = calculate_tokens(file_header + file_footer)
                    total_file_tokens = file_tokens + header_footer_tokens
                    
                    # Check if file fits in current chunk
                    # If current chunk has content and adding this file would exceed limit, start new chunk
                    if current_chunk_tokens > 0 and (current_chunk_tokens + total_file_tokens) > max_chunk_tokens:
                        # Close current chunk
                        out.close()
                        self.result_chunk_tokens.append(current_chunk_tokens)
                        print(f"[AGG_WORKER] 📦 Chunk {len(self.result_chunk_tokens)} completed with {current_chunk_tokens:,} tokens")
                        
                        # Start new chunk
                        fd2, temp_path2 = tempfile.mkstemp(suffix=".agg.txt")
                        os.close(fd2)
                        self.result_file_paths.append(temp_path2)
                        out = open(temp_path2, "w", encoding="utf-8", errors="replace")
                        current_chunk_tokens = write_header(out)
                        print(f"[AGG_WORKER] 📦 Started chunk {len(self.result_file_paths)} with header ({current_chunk_tokens:,} tokens)")
                    
                    
                    # Write entire file to current chunk (never split mid-file)
                    print(f"[AGG_WORKER] 📝 Writing file: {rel_path} ({len(file_content):,} chars)")
                    print(f"[AGG_WORKER] 📝 First 80 chars: {file_content[:80]}")
                    print(f"[AGG_WORKER] 📝 Last 80 chars: {file_content[-80:]}")
                    
                    out.write(file_header)
                    out.write(file_content)
                    out.write(file_footer)
                    
                    # Verify write by checking file position
                    current_pos = out.tell()
                    print(f"[AGG_WORKER] ✅ Written, file position now: {current_pos:,}")
                    
                    # Update token counts
                    current_chunk_tokens += total_file_tokens
                    total_tokens += total_file_tokens
                    files_processed += 1
                    
                except Exception as e:
                    print(f"[AGG_WORKER] ⚠️ Error processing {rel_path}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            agg_loop_time = (time.time() - agg_loop_start) * 1000
            print(f"[AGG_WORKER] 🔄 Aggregation loop processed {files_processed} files in {agg_loop_time:.2f}ms")
            print(f"[AGG_WORKER] 📊 Total tokens: {total_tokens:,} across {len(self.result_file_paths)} chunk(s)")

            try:
                out.write("\n")
                out.close()
                if current_chunk_tokens > 0:
                    self.result_chunk_tokens.append(current_chunk_tokens)
                    print(f"[AGG_WORKER] 📦 Final chunk {len(self.result_chunk_tokens)} completed with {current_chunk_tokens:,} tokens")
            except Exception:
                pass
                
            self.progress_signal.emit(100)
            self.token_progress_signal.emit(total_tokens)
            self.finished_signal.emit(True, total_tokens)

        except Exception as e:
            self.error_message = str(e)
            print(f"[AGG_WORKER] ❌ Fatal error: {e}")
            import traceback
            traceback.print_exc()
            self.finished_signal.emit(False, 0)

    def cancel(self):
        self._is_cancelled = True


class SaveWorker(QThread):
    """Background worker for saving workspace state to avoid UI freezes."""
    finished_signal = Signal(bool, str)  # success, message

    def __init__(self, workspaces, base_path=None, parent=None):
        super().__init__(parent)
        # Deep copy data to ensure thread safety
        import copy
        try:
            self.workspaces = copy.deepcopy(workspaces)
        except Exception as e:
            print(f"[SAVE_WORKER] ⚠️ Deep copy failed: {e}")
            self.workspaces = workspaces
            
        self.base_path = base_path

    def run(self):
        try:
            import time
            start_time = time.time()
            print(f"[SAVE_WORKER] 💾 Saving workspace in background...")
            
            from core import workspace_manager
            success = workspace_manager.save_workspaces(self.workspaces, base_path=self.base_path)
            
            total_time = (time.time() - start_time) * 1000
            if success:
                msg = f"Workspace saved in {total_time:.2f}ms"
                print(f"[SAVE_WORKER] ✅ {msg}")
                self.finished_signal.emit(True, msg)
            else:
                msg = "Failed to save workspace"
                print(f"[SAVE_WORKER] ❌ {msg}")
                self.finished_signal.emit(False, msg)
                
        except Exception as e:
            print(f"[SAVE_WORKER] ❌ Error in save worker: {e}")
            self.finished_signal.emit(False, str(e))


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

        # Aggregation Optimization - debounce + background worker
        self._aggregation_timer = QTimer()
        self._aggregation_timer.setSingleShot(True)
        
        # Save Optimization - debounce workspace saving
        self._save_debounce_timer = QTimer()
        self._save_debounce_timer.setSingleShot(True)
        self._save_debounce_timer.setInterval(1000)  # Wait 1 second after last change
        self._save_debounce_timer.timeout.connect(self._perform_save_workspace_state)
        self._aggregation_timer.setInterval(500)  # Wait 500ms after last click
        self._aggregation_timer.timeout.connect(self._perform_background_aggregation)
        self._current_agg_worker = None

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
            # Connect to selection manager dirty tracking for old TreePanel
            self.tree_panel.item_checked_changed.connect(self._on_checkbox_changed)
        else:
            # Model/View uses selection_changed signal
            self.tree_panel.selection_changed.connect(self._on_tree_selection_changed)
            self.tree_panel.selection_changed.connect(self.update_aggregation_and_tokens)
            # Connect model's dataChanged signal to selection manager dirty tracking for Model/View TreePanel
            if hasattr(self.tree_panel, 'file_tree_view') and hasattr(self.tree_panel.file_tree_view, 'model'):
                self.tree_panel.file_tree_view.model.dataChanged.connect(self._on_model_data_changed)
                self.tree_panel.file_tree_view.model.layoutChanged.connect(self._on_model_layout_changed)
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

        # Configure splitter sizes - ensure Repo Status panel is visible
        self.right_splitter.setStretchFactor(0, 0)  # Instructions panel
        self.right_splitter.setStretchFactor(1, 1)  # Aggregation view
        self.right_splitter.setStretchFactor(2, 0)  # Repo Status panel
        self.right_splitter.setSizes([100, 400, 300])

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
        self.aggregation_view.save_chunks_requested.connect(self._on_save_chunks_requested)
        self.aggregation_view.start_aggregation_requested.connect(self._on_manual_start_requested)

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
        import time
        start_time = time.time()
        print(f"[STREAMLINED] 🎉 Scan complete: {len(items)} items")
        
        # Reset scan flag to allow future scans
        self._scan_in_progress = False
        
        # CRITICAL FIX: Get pending restore paths from scan controller and set them on tree panel
        if hasattr(self, 'scan_ctl') and hasattr(self.scan_ctl, 'pending_restore_paths'):
            pending_paths = self.scan_ctl.pending_restore_paths
            if pending_paths:
                print(f"[MAIN_WINDOW] 🔄 Setting {len(pending_paths)} pending restore paths on tree panel")
                self.tree_panel.set_pending_restore_paths(pending_paths)
                # Clear the pending paths from scan controller after transferring
                self.scan_ctl.pending_restore_paths.clear()
            else:
                print(f"[MAIN_WINDOW] ℹ️ No pending restore paths from scan controller")
        
        # Update tree panel with results
        populate_start = time.time()
        self.tree_panel.populate_tree(items, self.current_folder_path)
        populate_time = (time.time() - populate_start) * 1000
        print(f"[MAIN_WINDOW] 🌳 Tree population took {populate_time:.2f}ms")

        self.tree_panel.show_loading(False)
        
        # Update aggregation and tokens
        agg_start = time.time()
        self.update_aggregation_and_tokens()
        agg_time = (time.time() - agg_start) * 1000
        print(f"[MAIN_WINDOW] 🔄 Aggregation update triggered in {agg_time:.2f}ms")
        
        # Show completion message
        file_count = len([item for item in items if not item[1]])  # Count files
        self.statusBar().showMessage(f"Scan complete: {len(items)} items, {file_count} files tokenized", 3000)
        
        total_time = (time.time() - start_time) * 1000
        print(f"[MAIN_WINDOW] ✅ _on_scan_complete finished in {total_time:.2f}ms")
    
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

        current_ws['selection_groups'] = self.selection_groups
        
        print(f"[STATE] ✅ Updated workspace state: {clean_workspace_name}")

    def _save_current_workspace_state(self):
        """Save current workspace state to file."""
        import time
        start_time = time.time()
        if self.workspaces:
            workspace_manager.save_workspaces(self.workspaces, base_path=self.testing_path)
            # Show status message for workspace save
            if self.current_workspace_name:
                clean_name = self.current_workspace_name.split(' (')[0].strip()
                self.statusBar().showMessage(f"Workspace '{clean_name}' saved.", 3000)
        save_time = (time.time() - start_time) * 1000
        print(f"[SAVE] 💾 save_workspaces took {save_time:.2f}ms")

    def _switch_workspace(self, workspace_name, initial_load=False):
        """Atomic workspace switch with complete data validation and error handling."""
        # Clean workspace name (remove any display suffixes like " (folder_name)")
        clean_workspace_name = workspace_name.split(' (')[0].strip()
        print(f"[WORKSPACE_SWITCH] 🔄 Initiating atomic switch to: '{clean_workspace_name}' (original: '{workspace_name}', initial_load: {initial_load})")
        
        try:
            # Phase 1: Pre-Switch State Capture
            if not initial_load and self.current_workspace_name:
                print(f"[WORKSPACE_SWITCH] 💾 Saving current workspace state: {self.current_workspace_name}")
                self._update_current_workspace_state()
                self._save_current_workspace_state()
                print(f"[WORKSPACE_SWITCH] ✅ Current workspace state saved")
            
            # Phase 2: Workspace Data Validation (use cleaned name)
            if not self._validate_workspace_exists(clean_workspace_name):
                if clean_workspace_name == "Default":
                    print(f"[WORKSPACE_SWITCH] 🏗️ Creating missing Default workspace")
                    self._create_default_workspace()
                else:
                    print(f"[WORKSPACE_SWITCH] ❌ Workspace '{clean_workspace_name}' does not exist")
                    return False
            
            # Phase 3: Atomic Workspace Load (use cleaned name)
            workspace_data = self._load_workspace_data(clean_workspace_name)
            if not workspace_data:
                print(f"[WORKSPACE_SWITCH] ❌ Failed to load workspace data for '{clean_workspace_name}'")
                return False
            
            # Phase 4: Apply Workspace State (All-or-Nothing, use cleaned name)
            success = self._apply_workspace_state(clean_workspace_name, workspace_data)
            if not success:
                print(f"[WORKSPACE_SWITCH] ❌ Failed to apply workspace state for '{clean_workspace_name}'")
                return False
            
            print(f"[WORKSPACE_SWITCH] ✅ Atomic workspace switch to '{clean_workspace_name}' completed successfully")
            # Show status message for successful workspace switch
            if not initial_load:  # Don't show message during startup
                self.statusBar().showMessage(f"Workspace '{clean_workspace_name}' loaded.", 3000)
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
        """Load and validate complete workspace data with selection restoration."""
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
            
            # Load and validate selection groups using selection manager
            self.selection_groups = selection_manager.load_groups(workspace_data)
            
            # Fix #1: Path Normalization at Data Boundary
            # Normalize all stored paths to lowercase with forward slashes for Windows compatibility
            print(f"[LOAD] 🔧 Normalizing paths for workspace: {workspace_name}")
            normalized_count = 0
            for group_name, group_data in self.selection_groups.items():
                if isinstance(group_data, dict) and "checked_paths" in group_data:
                    original_paths = group_data["checked_paths"]
                    normalized_paths = []
                    for path in original_paths:
                        # Normalize to lowercase with forward slashes for consistent matching
                        normalized_path = os.path.normpath(path).replace('\\', '/').lower()
                        normalized_paths.append(normalized_path)
                        normalized_count += 1
                    group_data["checked_paths"] = normalized_paths
            
            if normalized_count > 0:
                print(f"[NORMALIZE] ✅ Converted {normalized_count} paths to normalized format")
            
            # Determine active group (fallback to Default if needed)
            active_group = validated_data["active_selection_group"]
            if active_group not in self.selection_groups:
                active_group = "Default"
                validated_data["active_selection_group"] = "Default"
            
            # Apply to UI state
            self.active_selection_group = active_group
            
            print(f"[WORKSPACE_SWITCH] 📦 Loading workspace: {workspace_name}")
            print(f"[WORKSPACE_SWITCH] 📁 Folder: {validated_data['folder_path']}")
            print(f"[WORKSPACE_SWITCH] ⚙️ Scan settings: {validated_data['scan_settings']}")
            print(f"[WORKSPACE_SWITCH]   → Active group: {active_group}")
            
            # Get group paths for logging
            if active_group in self.selection_groups:
                group_paths = self.selection_groups[active_group].get("checked_paths", [])
                print(f"[WORKSPACE_SWITCH]   → Group paths count: {len(group_paths)}")
                if group_paths:
                    print(f"[WORKSPACE_SWITCH]   → First 3 paths: {group_paths[:3]}")
            
            print(f"[WORKSPACE_SWITCH] ✅ Workspace data loaded and validated for '{workspace_name}'")
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
            
            # Apply selection groups (already loaded in _load_workspace_data)
            # Update selection manager panel with current groups
            self.selection_manager_panel.update_groups(list(self.selection_groups.keys()), self.active_selection_group)
            
            # Restore file selections immediately if tree is already populated
            if hasattr(self, 'tree_panel') and self.current_folder_path:
                group_paths = self.selection_groups.get(self.active_selection_group, {}).get("checked_paths", [])
                if group_paths:
                    print(f"[WORKSPACE_SWITCH] 🔄 Restoring {len(group_paths)} file selections for group '{self.active_selection_group}'")
                    self.tree_panel.set_checked_paths(group_paths, relative=False)
            
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
        """Handle tree panel selection changes and save workspace state."""
        # 1. Update Aggregation
        self.update_aggregation_and_tokens()

        # 2. Update Repo Status "Active Selection" list
        if hasattr(self, 'tree_panel') and hasattr(self, 'file_changes_panel'):
            current_selection = self.tree_panel.get_checked_paths(relative=False, return_set=True)
            self.file_changes_panel.update_active_selection(current_selection)

        # 3. Save State
        self._update_current_workspace_state()
        # self._save_current_workspace_state()

    @Slot(str)
    def _on_workspace_switched(self, workspace_name):
        print(f"[PERFORMANCE] Starting workspace switch to '{workspace_name}'")
        start_time = __import__('time').time()
        
        self._update_path_display(self.current_folder_path or "No folder selected.")
        # Update Repo Status panel root and log workspace load
        if hasattr(self, 'file_changes_panel'):
            self.file_changes_panel.set_root_path(self.current_folder_path)
            self.file_changes_panel.add_system_message(f"Loaded workspace: {workspace_name}")
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
                    ignore_rules.add(str(pathlib.Path(ws_file_path).name))

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
        """Starts the debounce timer for aggregation regardless of selection size."""
        current_tokens = 0
        if hasattr(self.tree_panel, "get_selected_token_count"):
            try:
                current_tokens = self.tree_panel.get_selected_token_count()
                if hasattr(self, "aggregation_view"):
                    self.aggregation_view.update_token_count(current_tokens)
            except Exception as e:
                print(f"[MAIN_WINDOW] ⚠️ Error updating token count: {e}")
        if hasattr(self, "aggregation_view"):
            self.aggregation_view.set_manual_start_visible(False, current_tokens)
        self._aggregation_timer.start()

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
        
        # Ensure background save worker is finished
        try:
            if hasattr(self, '_save_worker') and self._save_worker and self._save_worker.isRunning():
                self._save_worker.wait()
        except Exception:
            pass
        
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
        current_ws["scan_settings"] = ensure_complete_scan_settings(self.current_scan_settings)
        current_ws["instructions"] = self.instructions_panel.get_text()
        current_ws['active_selection_group'] = self.active_selection_group
        
        # Get absolute paths from tree (for UI consistency)
        absolute_paths = self.tree_panel.get_checked_paths(relative=False)
        
        # Update the active selection group with current checked paths using selection manager
        if self.active_selection_group in self.selection_groups:
            # Get existing description
            description = self.selection_groups[self.active_selection_group].get("description", "")
            
            # Use selection manager to save with proper path conversion
            from core import selection_manager
            selection_manager.save_group(current_ws, self.active_selection_group, description, absolute_paths)
            
            # Update local selection groups cache
            self.selection_groups = selection_manager.load_groups(current_ws)
        
        print(f"[STATE] 📦 Workspace state update for {self.current_workspace_name}:")
        print(f"[STATE]   → Active group: {self.active_selection_group}")
        print(f"[STATE]   → Checked paths count: {len(absolute_paths)}")
        if absolute_paths:
            print(f"[STATE]   → First 3 paths: {list(absolute_paths)[:3]}")
        print(f"[STATE] ✅ Workspace state updated with {len(absolute_paths)} checked files")

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
            # DEBOUNCE: Don't save immediately, restart the timer
            self._save_debounce_timer.start()
            # print(f"[TREE] ⏳ Selection changed, save timer restarted")

    @Slot()
    def _perform_save_workspace_state(self):
        """Actually perform the workspace save after debounce timer fires."""
        if self.current_workspace_name and self.workspaces:
            try:
                # Update state before saving
                self._update_current_workspace_state()
                
                # Start background save
                if hasattr(self, '_save_worker') and self._save_worker and self._save_worker.isRunning():
                    # If a save is already running, we should probably wait or queue it
                    # For now, let's just log it and skip to avoid race conditions
                    print(f"[TREE] ⏳ Save already in progress, skipping intermediate save")
                    return

                self._save_worker = SaveWorker(self.workspaces, self.testing_path)
                self._save_worker.finished_signal.connect(self._on_save_finished)
                self._save_worker.start()
                
            except Exception as e:
                print(f"[TREE] ❌ Error initiating background save: {e}")

    @Slot(bool, str)
    def _on_save_finished(self, success, message):
        """Handle save completion."""
        if success:
            # Optional: Update status bar only if needed, to avoid noise
            # self.statusBar().showMessage(message, 2000)
            pass
        else:
            self.statusBar().showMessage(f"Save failed: {message}", 5000)
            
        # Clean up worker
        self._save_worker = None

    @Slot()
    def _on_checkbox_changed(self):
        """Handle checkbox state changes for dirty state tracking."""
        # Mark selection manager as dirty when checkboxes are toggled
        self.selection_manager_panel.set_dirty(True)
        print(f"[SELECTION] 🔄 Checkbox changed - selection manager marked as dirty")

    @Slot()
    def _on_model_data_changed(self, top_left, bottom_right, roles):
        """Handle model data changes, specifically checkbox state changes."""
        from PySide6.QtCore import Qt
        if Qt.ItemDataRole.CheckStateRole in roles:
            # Mark selection manager as dirty when checkboxes are toggled
            self.selection_manager_panel.set_dirty(True)
            print(f"[SELECTION] 🔄 Model checkbox changed - selection manager marked as dirty")
            # Immediately update aggregation view
            self.update_aggregation_and_tokens()

    @Slot()
    def _on_model_layout_changed(self):
        """Handle model layout changes (bulk updates)."""
        # Treat layout changes as potential bulk checkbox updates
        self.selection_manager_panel.set_dirty(True)
        print(f"[SELECTION] 🔄 Model layout changed - selection manager marked as dirty")
        # Ensure aggregation reflects latest selection
        self.update_aggregation_and_tokens()

    @Slot()
    def _on_instructions_changed(self):
        """Handle instruction changes and update aggregation view."""
        try:
            print(f"[INSTRUCTIONS] 🔄 Instructions changed - updating aggregation view...")
            
            # Update the aggregation view with new instructions
            self.update_aggregation_and_tokens()
            
            # Save workspace state to persist instruction changes
            if self.current_workspace_name and self.workspaces:
                self._update_current_workspace_state()
                self._save_current_workspace_state()
                print(f"[INSTRUCTIONS] ✅ Workspace state saved after instruction change")
                
        except Exception as e:
            print(f"[INSTRUCTIONS] ❌ Error handling instruction change: {e}")
            import traceback
            traceback.print_exc()

    @Slot()
    def update_aggregation_and_tokens(self):
        """Start debounce timer and update status immediately on selection change."""
        # FIX: Always auto-start aggregation; no manual threshold here
        current_tokens = 0
        if hasattr(self.tree_panel, "get_selected_token_count"):
            try:
                current_tokens = self.tree_panel.get_selected_token_count()
                if hasattr(self, "aggregation_view"):
                    self.aggregation_view.update_token_count(current_tokens)
            except Exception as e:
                print(f"[MAIN_WINDOW] ⚠️ Error updating token count: {e}")

        if hasattr(self, "aggregation_view"):
            self.aggregation_view.set_manual_start_visible(False, current_tokens)

        # FEEDBACK: Let the user know the click/selection was registered
        try:
            self.statusBar().showMessage(
                f"Selection updated ({current_tokens:,} tokens). Aggregating in 0.5s...",
                1000,
            )
        except Exception:
            pass

        self._aggregation_timer.start()

    def _perform_background_aggregation(self):
        """Called by timer. Starts the background thread."""
        if not self.current_folder_path:
            return

        # 1. ASYNC CANCELLATION: flag old worker to stop and disconnect signals
        if self._current_agg_worker and self._current_agg_worker.isRunning():
            self._current_agg_worker.cancel()
            try:
                self._current_agg_worker.finished_signal.disconnect()
            except Exception:
                pass
            try:
                self._current_agg_worker.progress_signal.disconnect()
            except Exception:
                pass
            # Do NOT call .wait() here; let it finish in the background
            self._current_agg_worker = None

        # 2. Show loading state
        if hasattr(self, "aggregation_view"):
            self.aggregation_view.set_loading(True)

        # 3. Start new worker with fresh data
        checked = set()
        if hasattr(self.tree_panel, "get_checked_paths"):
            checked = self.tree_panel.get_checked_paths(relative=True, return_set=True)
            print(f"[AGGREGATION] 📋 Retrieved {len(checked)} checked paths from tree panel")
            if checked:
                print(f"[AGGREGATION] 📋 First 3 checked paths: {list(checked)[:3]}")
            else:
                print(f"[AGGREGATION] ⚠️ WARNING: No checked paths retrieved from tree panel!")
                # Debug: Check if the model has any checked files
                if hasattr(self.tree_panel, 'file_tree_view') and hasattr(self.tree_panel.file_tree_view, 'model'):
                    model_checked = self.tree_panel.file_tree_view.model._checked_files
                    print(f"[AGGREGATION] 🔍 Model _checked_files cache has {len(model_checked)} entries")
                    if model_checked:
                        print(f"[AGGREGATION] 🔍 First 3 from cache: {list(model_checked)[:3]}")

        # FEEDBACK: Show when background work actually begins
        try:
            self.statusBar().showMessage(
                f"Aggregating {len(checked)} files...",
                3000,
            )
        except Exception:
            pass

        prompt = ""
        if hasattr(self, "instructions_panel"):
            prompt = self.instructions_panel.get_text()
            
        print(f"[MAIN_WINDOW] 🚀 Starting background aggregation for {len(checked)} files...")

        self._current_agg_worker = AggregationWorker(self.current_folder_path, checked, prompt)
        self._current_agg_worker.finished_signal.connect(self._on_aggregation_finished)
        self._current_agg_worker.progress_signal.connect(self._on_aggregation_progress)
        self._agg_last_tokens = 0
        try:
            self._current_agg_worker.token_progress_signal.connect(self._on_aggregation_token_progress)
        except Exception:
            pass
        self._current_agg_worker.start()

    @Slot(bool, int)
    def _on_aggregation_finished(self, success, tokens):
        """Called when aggregation thread is done. Reads data from worker instance."""
        if not hasattr(self, "aggregation_view"):
            return

        # Ensure we are handling the currently active worker
        worker = self.sender()
        if worker is None or worker != self._current_agg_worker:
            return

        if success:
            paths = getattr(worker, "result_file_paths", [])
            # Use chunked content for ANY number of chunk files (including 1)
            if paths and len(paths) >= 1:
                chunk_tokens = getattr(worker, "result_chunk_tokens", [])
                self.aggregation_view.set_chunked_content(paths, tokens, chunk_tokens)
                print(f"[MAIN_WINDOW] ✅ Aggregation complete: {len(paths)} chunk(s), {tokens:,} total tokens")
            else:
                # Fallback for in-memory content (should not happen with new worker)
                final_content = worker.result_text
                self.aggregation_view.set_content(final_content, tokens)
                print(f"[MAIN_WINDOW] ✅ Aggregation complete: in-memory, {tokens:,} tokens")
        else:
            self.aggregation_view.set_content(f"Error: {worker.error_message}", 0)
            print(f"[MAIN_WINDOW] ❌ Aggregation failed: {worker.error_message}")

        self.aggregation_view.set_loading(False)
        self._current_agg_worker = None

    @Slot(int)
    def _on_aggregation_progress(self, percent: int):
        """Update loading text with background aggregation progress."""
        if hasattr(self, "aggregation_view"):
            tokens = getattr(self, "_agg_last_tokens", 0)
            self.aggregation_view.update_loading_text(f"Processing... {percent}% • ~{tokens:,} tokens")

    @Slot(int)
    def _on_aggregation_token_progress(self, tokens: int):
        self._agg_last_tokens = tokens

    @Slot(list)
    def _on_save_chunks_requested(self, file_paths: list):
        try:
            from PySide6.QtWidgets import QFileDialog
            target_dir = QFileDialog.getExistingDirectory(self, "Select Folder to Save Chunks")
            if not target_dir:
                return
            import shutil, os
            for idx, src in enumerate(file_paths or []):
                name = f"aggregation_chunk_{idx+1:02d}.md"
                dst = os.path.join(target_dir, name)
                shutil.copyfile(src, dst)
            self.statusBar().showMessage(f"Saved {len(file_paths)} chunks to {target_dir}", 4000)
        except Exception as e:
            print(f"[MAIN_WINDOW] ❌ Error saving chunks: {e}")

    @Slot()
    def _on_manual_start_requested(self):
        self._perform_background_aggregation()

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
        """Get aggregated content from checked file paths using cached token counts and optimized I/O."""
        if not checked_paths or not self.current_folder_path:
            return "", 0
        
        aggregated_parts = []
        total_tokens = 0
        files_processed = 0
        
        try:
            print(f"[AGGREGATION] 🚀 Processing {len(checked_paths)} files with optimized I/O...")
            
            # Process files in consistent order
            for relative_path in sorted(checked_paths):
                absolute_path = os.path.join(self.current_folder_path, relative_path)
                
                if not os.path.isfile(absolute_path):
                    continue
                
                try:
                    # Get cached token count first (fast operation)
                    token_count = self._get_cached_token_count(absolute_path)
                    total_tokens += token_count
                    
                    # Get file extension for language
                    _, ext = os.path.splitext(relative_path)
                    language = ext[1:] if ext else ""
                    
                    # Read file content (this is the expensive operation)
                    with open(absolute_path, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                    
                    # Build markdown section
                    aggregated_parts.append(f"{relative_path}")
                    aggregated_parts.append(f"```{language}")
                    aggregated_parts.append(content)
                    aggregated_parts.append("```\n")
                    
                    files_processed += 1
                    
                    # Only log every 10th file to reduce console spam
                    if files_processed % 10 == 0 or files_processed == len(checked_paths):
                        print(f"[AGGREGATION] 📊 Processed {files_processed}/{len(checked_paths)} files, {total_tokens} tokens")
                    
                except Exception as e:
                    aggregated_parts.append(f"[Error reading {relative_path}: {e}]\n")
                    print(f"[AGGREGATION] ⚠️ Error reading {relative_path}: {e}")
            
            print(f"[AGGREGATION] ✅ Completed: {files_processed} files, {total_tokens} tokens (using cached counts)")
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

    @Slot()
    def _open_custom_instructions_dialog(self):
        """Open the custom instructions manager dialog."""
        try:
            print(f"[INSTRUCTIONS] 🔧 Opening custom instructions manager...")
            
            # Get current workspace data for local templates
            workspace_data = {}
            if self.current_workspace_name and self.workspaces:
                clean_workspace_name = self.current_workspace_name.split(' (')[0].strip()
                if clean_workspace_name in self.workspaces.get('workspaces', {}):
                    workspace_data = self.workspaces['workspaces'][clean_workspace_name].copy()
            
            # Ensure workspace data has required fields
            if 'use_local_templates' not in workspace_data:
                workspace_data['use_local_templates'] = False
            if 'local_custom_instructions' not in workspace_data:
                workspace_data['local_custom_instructions'] = {}
            
            # Create and show dialog
            dialog = CustomInstructionsDialog(
                global_instructions=self.custom_instructions,
                workspace_data=workspace_data,
                parent=self
            )
            
            # Connect dialog signals
            dialog.instructions_changed.connect(self._on_custom_instructions_changed)
            
            # Show dialog
            result = dialog.exec()
            
            print(f"[INSTRUCTIONS] ✅ Custom instructions dialog closed with result: {result}")
            
        except Exception as e:
            print(f"[INSTRUCTIONS] ❌ Error opening custom instructions dialog: {e}")
            import traceback
            traceback.print_exc()
    
    @Slot(dict, bool, dict)
    def _on_custom_instructions_changed(self, global_instructions, use_local_templates, local_instructions):
        """Handle changes from the custom instructions dialog."""
        try:
            print(f"[INSTRUCTIONS] 🔄 Processing custom instructions changes...")
            
            # Update global instructions
            self.custom_instructions = global_instructions
            
            # Update current workspace data if we have a workspace
            if self.current_workspace_name and self.workspaces:
                clean_workspace_name = self.current_workspace_name.split(' (')[0].strip()
                if clean_workspace_name in self.workspaces.get('workspaces', {}):
                    workspace = self.workspaces['workspaces'][clean_workspace_name]
                    workspace['use_local_templates'] = use_local_templates
                    workspace['local_custom_instructions'] = local_instructions
            
            # Save global instructions to file
            workspace_manager.save_custom_instructions(self.custom_instructions, base_path=self.testing_path)
            
            # Update instructions panel with new templates
            if hasattr(self, 'instructions_panel'):
                self.instructions_panel.populate_templates(self.custom_instructions)
                print(f"[INSTRUCTIONS] ✅ Instructions panel templates updated")
            
            # Save workspace state to persist local template settings
            self._update_current_workspace_state()
            self._save_current_workspace_state()
            
            # Update aggregation view with any instruction changes
            self.update_aggregation_and_tokens()
            
            print(f"[INSTRUCTIONS] ✅ Custom instructions changes processed successfully")
            
        except Exception as e:
            print(f"[INSTRUCTIONS] ❌ Error processing custom instructions changes: {e}")
            import traceback
            traceback.print_exc()
    
    @Slot()
    def _on_model_data_changed(self, top_left, bottom_right, roles):
        """Handle model data changes, specifically checkbox state changes."""
        from PySide6.QtCore import Qt
        if Qt.ItemDataRole.CheckStateRole in roles:
            self.selection_manager_panel.set_dirty(True)
            print("[SELECTION] 🔄 Model checkbox changed - selection manager marked as dirty")
            # Immediately update aggregation view
            self.update_aggregation_and_tokens()
    
    @Slot()
    def _on_checkbox_changed(self):
        """Handle checkbox state changes for dirty state tracking."""
        self.selection_manager_panel.set_dirty(True)
        print("[SELECTION] 🔄 Checkbox changed - selection manager marked as dirty")
        # Immediately update aggregation view
        self.update_aggregation_and_tokens()
