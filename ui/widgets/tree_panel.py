from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QLabel, QHeaderView, 
    QTreeWidgetItem, QTreeWidgetItemIterator, QStyle
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QIcon

import os
import pathlib
import time

# Assuming these helpers will be available from the core module
from core.helpers import TIKTOKEN_AVAILABLE, get_tokenizer

class TreePanel(QWidget):
    """A widget that encapsulates the file/folder tree view and its logic."""
    
    # Signals to communicate with the main window
    selection_changed = Signal()
    item_checked_changed = Signal()
    file_tokens_changed = Signal(str, int) # path, token_diff
    root_path_changed = Signal(str) # root_path

    # Constants for data roles
    PATH_DATA_ROLE = Qt.ItemDataRole.UserRole + 0
    TOKEN_COUNT_ROLE = Qt.ItemDataRole.UserRole + 1
    IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._is_programmatically_checking = False
        self.tree_items = {}  # To keep track of items by path
        self.tokenizer = get_tokenizer()
        self._pending_tree_restore_paths = set()
        self.root_path = None
        
        # Batching variables for non-blocking tree population
        # Initialize batching variables with dynamic sizing
        self._base_batch_size = 25  # Base batch size for small projects
        self._batch_timer = QTimer()
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._process_next_batch)
        self._batch_timer.setSingleShot(True)
        
        # Timing variables for performance tracking
        self._tree_start_time = None
        self._phase_start_time = None

        # Icons
        self.folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self.file_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        self.error_color = QColor("red")

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Sets up the widgets within this panel."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.loading_label = QLabel("Scanning folder...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setVisible(False)

        # Progress label for optimistic loading
        self.progress_label = QLabel("Loading tokens...")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setVisible(False)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Name", "Status / Tokens"])
        self.tree_widget.setColumnCount(2)
        self.tree_widget.header().setStretchLastSection(False)
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.setAlternatingRowColors(True)

        self.token_count_label = QLabel("Total tokens: 0")
        self.token_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout.addWidget(self.loading_label)
        layout.addWidget(self.progress_label)
        layout.addWidget(self.tree_widget)
        layout.addWidget(self.token_count_label)

    def _connect_signals(self):
        """Connects internal signals."""
        self.tree_widget.itemChanged.connect(self._handle_item_changed)
        self.tree_widget.itemSelectionChanged.connect(self.selection_changed)
        self.item_checked_changed.connect(self.update_folder_token_display)
        self.item_checked_changed.connect(self._update_total_token_label)

    @Slot(QTreeWidgetItem, int)
    def _handle_item_changed(self, item, column):
        if column != 0 or self._is_programmatically_checking:
            return

        self._is_programmatically_checking = True
        try:
            state = item.checkState(0)
            # Propagate state down to children
            def set_children_check_state(item, state):
                for i in range(item.childCount()):
                    child = item.child(i)
                    if child.checkState(0) != state:
                        child.setCheckState(0, state)
                    if child.childCount() > 0:
                        set_children_check_state(child, state)

            if item.data(0, self.IS_DIR_ROLE):
                set_children_check_state(item, state)

            # Propagate state up to parents
            parent = item.parent()
            while parent:
                if state == Qt.CheckState.Checked:
                    if parent.checkState(0) != Qt.CheckState.Checked:
                        parent.setCheckState(0, Qt.CheckState.Checked)
                else: # Unchecked or PartiallyChecked
                    all_unchecked = True
                    for i in range(parent.childCount()):
                        if parent.child(i).checkState(0) != Qt.CheckState.Unchecked:
                            all_unchecked = False
                            break
                    if all_unchecked:
                        parent.setCheckState(0, Qt.CheckState.Unchecked)

                parent = parent.parent()
        finally:
            self._is_programmatically_checking = False
            self.item_checked_changed.emit()

    
    # --- Public Methods ---

    def clear_tree(self):
        self.tree_widget.clear()
        self.tree_items.clear()

    def show_loading(self, is_loading):
        self.loading_label.setVisible(is_loading)
        self.tree_widget.setVisible(not is_loading)

    def set_pending_restore_paths(self, paths):
        self._pending_tree_restore_paths = {os.path.normpath(p) for p in paths}

    def set_checked_paths(self, paths, relative=False):
        """Programmatically sets the check state of items based on a list of paths."""
        self._is_programmatically_checking = True
        try:
            paths_to_check = set()
            if relative and self.root_path:
                for path in paths:
                    # On Windows, os.path.join will use backslashes, but our stored paths use forward slashes.
                    # So we construct the path manually and normalize.
                    full_path = os.path.normpath(f"{self.root_path}/{path}").replace('\\', '/')
                    paths_to_check.add(full_path)
            else:
                paths_to_check = set(paths)

            iterator = QTreeWidgetItemIterator(self.tree_widget)
            while iterator.value():
                item = iterator.value()
                item_path = item.data(0, self.PATH_DATA_ROLE)
                if item_path in paths_to_check:
                    if item.checkState(0) != Qt.CheckState.Checked:
                        item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    if item.checkState(0) != Qt.CheckState.Unchecked:
                         item.setCheckState(0, Qt.CheckState.Unchecked)
                iterator += 1
        finally:
            self._is_programmatically_checking = False
        
        # Trigger updates after all changes are made
        self.item_checked_changed.emit()

    def get_checked_paths(self, return_set=False, relative=False):
        """Gets the paths of all checked items in the tree."""
        checked_paths = set()
        iterator = QTreeWidgetItemIterator(self.tree_widget)
        while iterator.value():
            item = iterator.value()
            if item.checkState(0) == Qt.CheckState.Checked:
                path = item.data(0, self.PATH_DATA_ROLE)
                if path:
                    norm_path = os.path.normpath(path).replace('\\', '/')
                    if relative and self.root_path:
                        # Ensure the path is within the root_path to avoid ValueError
                        if norm_path.startswith(self.root_path):
                            checked_paths.add(os.path.relpath(norm_path, self.root_path))
                        else:
                            checked_paths.add(norm_path) # Add absolute path as fallback
                    else:
                        checked_paths.add(norm_path)
            iterator += 1
        
        return checked_paths if return_set else sorted(list(checked_paths))

    def populate_tree(self, items, root_path):
        """Populate tree with batched processing to prevent UI blocking."""
        self._tree_start_time = time.time()
        print(f"[TREE_PANEL] 🌳 Starting batched tree population with {len(items)} items (T+0.00ms)")
        
        self.clear_tree()
        clear_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 🧽 Tree cleared (T+{clear_time:.2f}ms)")
        
        self.root_path = os.path.normpath(root_path).replace('\\', '/')
        
        # Store items for batched processing and pre-calculate token data
        self._pending_items = items.copy()
        self._batch_index = 0
        self._batch_size = self._base_batch_size  # Process 25 items per batch
        
        # Pre-calculate and store token data from BG_scanner results
        self._token_data = {}  # path -> token_count mapping
        self._folder_tokens = {}  # folder_path -> total_tokens mapping
        
        # Extract token data from BG_scanner results
        for path_str, is_dir, rel_path, file_size, tokens in items:
            norm_path = os.path.normpath(path_str).replace('\\', '/')
            if not is_dir and tokens > 0:
                self._token_data[norm_path] = tokens
                # Also accumulate folder tokens
                folder_path = os.path.dirname(norm_path)
                while folder_path and folder_path != self.root_path:
                    self._folder_tokens[folder_path] = self._folder_tokens.get(folder_path, 0) + tokens
                    folder_path = os.path.dirname(folder_path)
                # Add to root folder
                self._folder_tokens[self.root_path] = self._folder_tokens.get(self.root_path, 0) + tokens
        
        token_calc_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 🧠 Token data pre-calculated from BG_scanner: {len(self._token_data)} files, {sum(self._token_data.values())} total tokens (T+{token_calc_time:.2f}ms)")
        
        # Disable updates during batching
        self.tree_widget.setUpdatesEnabled(False)
        
        # Create root item first
        root_item = self._add_item_to_tree(
            self.tree_widget.invisibleRootItem(), self.root_path, True, True, '', 0
        )
        root_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 🌳 Root item created (T+{root_time:.2f}ms)")
        
        # Pre-calculate all required directories for batched processing
        calc_start_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 📁 Pre-calculating directory structure... (T+{calc_start_time:.2f}ms)")
        self._all_required_dirs = {self.root_path}
        for path_str, is_dir, _, _, _ in self._pending_items:
            norm_path = os.path.normpath(path_str).replace('\\', '/')
            path_to_ascend = norm_path if is_dir else os.path.dirname(norm_path)
            p = pathlib.Path(path_to_ascend)
            while p and str(p) != self.root_path and len(str(p)) >= len(self.root_path):
                self._all_required_dirs.add(str(p).replace('\\', '/'))
                p = p.parent
        
        # Convert to sorted list for batched processing
        self._sorted_dirs = sorted(list(self._all_required_dirs))
        self._dir_index = 0
        
        calc_complete_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] ✅ Directory calculation complete: {len(self._sorted_dirs)} directories, {len(self._pending_items)} items (T+{calc_complete_time:.2f}ms)")
        
        # Calculate optimal batch size and timer interval based on project size
        total_items = len(self._pending_items)
        if total_items <= 100:
            self._batch_size = 25
            self._timer_interval = 1  # 1ms for small projects
        elif total_items <= 300:
            self._batch_size = 50
            self._timer_interval = 0  # No delay for medium projects
        else:
            self._batch_size = 100
            self._timer_interval = 0  # No delay for large projects
        
        # Start batched processing with optimized timer
        batch_start_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 🚀 Starting batched processing: {self._batch_size} items/batch, {self._timer_interval}ms interval (T+{batch_start_time:.2f}ms)")
        self._phase_start_time = time.time()  # Track phase timing
        self._batch_timer.start(self._timer_interval)
    
    def _process_next_batch(self):
        """Process next batch of items to keep UI responsive."""
        current_time = (time.time() - self._tree_start_time) * 1000
        
        # Phase 1: Create directories in batches
        if self._dir_index < len(self._sorted_dirs):
            batch_end = min(self._dir_index + self._batch_size, len(self._sorted_dirs))
            
            for i in range(self._dir_index, batch_end):
                dir_path = self._sorted_dirs[i]
                if dir_path not in self.tree_items:
                    parent_path = os.path.dirname(dir_path)
                    parent_item = self.tree_items.get(parent_path, self.tree_widget.invisibleRootItem())
                    self._add_item_to_tree(parent_item, dir_path, True, True, '', 0)
            
            self._dir_index = batch_end
            
            # Progress update for directories (only every 25 items to reduce console spam)
            if self._dir_index % 25 == 0 or self._dir_index == len(self._sorted_dirs):
                dir_progress = (self._dir_index / len(self._sorted_dirs)) * 50  # Directories are 50% of total progress
                dir_progress_time = (time.time() - self._tree_start_time) * 1000
                print(f"[TREE_PANEL] 📁 Directory progress: {self._dir_index}/{len(self._sorted_dirs)} ({dir_progress:.1f}%) (T+{dir_progress_time:.2f}ms)")
            
            # Continue with next batch
            self._batch_timer.start(self._timer_interval)
            return
        
        # Phase 2: Create file items in batches
        if self._batch_index < len(self._pending_items):
            # Log phase transition on first file batch
            if self._batch_index == 0:
                phase_transition_time = (time.time() - self._tree_start_time) * 1000
                print(f"[TREE_PANEL] 🔄 Transitioning to file processing phase (T+{phase_transition_time:.2f}ms)")
            batch_end = min(self._batch_index + self._batch_size, len(self._pending_items))
            
            for i in range(self._batch_index, batch_end):
                path_str, is_dir, is_valid, reason, token_count = self._pending_items[i]
                
                if not is_dir:  # Only process files in this phase
                    norm_path = os.path.normpath(path_str).replace('\\', '/')
                    parent_path = os.path.dirname(norm_path)
                    parent_item = self.tree_items.get(parent_path, self.tree_widget.invisibleRootItem())
                    self._add_item_to_tree(parent_item, norm_path, False, is_valid, reason, token_count)
            
            self._batch_index = batch_end
            
            # Progress update for files (only every 50 items to reduce console spam for large projects)
            progress_interval = 50 if len(self._pending_items) > 200 else 25
            if self._batch_index % progress_interval == 0 or self._batch_index == len(self._pending_items):
                file_progress = 50 + (self._batch_index / len(self._pending_items)) * 50  # Files are the remaining 50%
                file_progress_time = (time.time() - self._tree_start_time) * 1000
                print(f"[TREE_PANEL] 📄 File progress: {self._batch_index}/{len(self._pending_items)} ({file_progress:.1f}%) (T+{file_progress_time:.2f}ms)")
            
            # Continue with next batch
            self._batch_timer.start(self._timer_interval)
            return
        
        # Phase 3: Finalization
        finalize_start_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] ⚙️ Finalizing tree... (T+{finalize_start_time:.2f}ms)")
        self._finalize_tree_population()
    
    def _finalize_tree_population(self):
        """Complete tree population with final setup steps."""
        # Apply pre-calculated token data directly to tree items (no recursive calculation needed!)
        token_start_time = (time.time() - self._tree_start_time) * 1000
        
        # Set file token counts from BG_scanner data
        for file_path, token_count in self._token_data.items():
            if file_path in self.tree_items:
                self.tree_items[file_path].setData(0, self.TOKEN_COUNT_ROLE, token_count)
        
        # Set folder token counts from pre-calculated totals
        for folder_path, total_tokens in self._folder_tokens.items():
            if folder_path in self.tree_items:
                self.tree_items[folder_path].setData(0, self.TOKEN_COUNT_ROLE, total_tokens)
        
        token_complete_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 🧠 Token data applied from BG_scanner (T+{token_start_time:.2f}ms -> T+{token_complete_time:.2f}ms)")
        
        display_start_time = (time.time() - self._tree_start_time) * 1000
        self.update_folder_token_display()
        display_complete_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 📊 Token display updated (T+{display_start_time:.2f}ms -> T+{display_complete_time:.2f}ms)")
        
        # Restore checked paths
        if self._pending_tree_restore_paths:
            restore_start_time = (time.time() - self._tree_start_time) * 1000
            for path in self._pending_tree_restore_paths:
                if path in self.tree_items:
                    self.tree_items[path].setCheckState(0, Qt.CheckState.Checked)
            self._pending_tree_restore_paths.clear()
            restore_complete_time = (time.time() - self._tree_start_time) * 1000
            print(f"[TREE_PANEL] ✅ Checked paths restored (T+{restore_start_time:.2f}ms -> T+{restore_complete_time:.2f}ms)")
        
        # Re-enable updates and expand tree
        ui_start_time = (time.time() - self._tree_start_time) * 1000
        self.tree_widget.setUpdatesEnabled(True)
        self.tree_widget.expandToDepth(0)
        ui_complete_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 🌳 Tree UI updates enabled and expanded (T+{ui_start_time:.2f}ms -> T+{ui_complete_time:.2f}ms)")
        
        signal_start_time = (time.time() - self._tree_start_time) * 1000
        self.root_path_changed.emit(self.root_path)
        
        # Final completion timing
        total_time = (time.time() - self._tree_start_time) * 1000
        print(f"[TREE_PANEL] 🎉 TREE POPULATION COMPLETED: {len(self.tree_items)} items in {total_time:.2f}ms")
        print(f"[TREE_PANEL] 📈 Performance: {len(self.tree_items)/total_time*1000:.1f} items/second")

    def populate_tree_optimistic(self, items, root_path):
        """Optimistically populate tree with immediate display and loading states."""
        self.clear_tree()
        self.root_path = os.path.normpath(root_path).replace('\\', '/')
        self.tree_widget.setUpdatesEnabled(False)
        
        # Hide main loading label, show tree immediately
        self.loading_label.setVisible(False)
        self.tree_widget.setVisible(True)
        
        root_item = self._add_item_to_tree(
            self.tree_widget.invisibleRootItem(), self.root_path, True, True, '', 0
        )

        # Step 1: Collect all directory paths that need to exist.
        all_required_dirs = {self.root_path}
        files_with_loading_tokens = []
        
        for path_str, is_dir, _, _, token_count in items:
            norm_path = os.path.normpath(path_str).replace('\\', '/')
            path_to_ascend = norm_path if is_dir else os.path.dirname(norm_path)
            p = pathlib.Path(path_to_ascend)
            while p and str(p) != self.root_path and len(str(p)) >= len(self.root_path):
                all_required_dirs.add(str(p).replace('\\', '/'))
                p = p.parent
                
            # Track files that need token loading
            if not is_dir and token_count == -1:
                files_with_loading_tokens.append(norm_path)

        # Step 2: Create all directory items
        for dir_path in sorted(list(all_required_dirs)):
            if dir_path == self.root_path or dir_path in self.tree_items:
                continue
            parent_path = os.path.dirname(dir_path)
            parent_item = self.tree_items.get(parent_path)
            if parent_item:
                self._add_item_to_tree(parent_item, dir_path, True, True, '', 0)

        # Step 3: Create all file items with loading states
        for path_str, is_dir, is_valid, reason, token_count in items:
            if not is_dir:
                norm_path = os.path.normpath(path_str).replace('\\', '/')
                parent_path = os.path.dirname(norm_path)
                parent_item = self.tree_items.get(parent_path)
                if parent_item:
                    # Show "Loading..." for files with token_count = -1
                    display_token_count = token_count if token_count != -1 else "Loading..."
                    item = self._add_item_to_tree(parent_item, norm_path, False, is_valid, reason, token_count)
                    if token_count == -1:
                        item.setText(1, "Loading...")
                        item.setData(1, self.TOKEN_COUNT_ROLE, -1)

        # Show progress if there are files loading
        if files_with_loading_tokens:
            self.progress_label.setText(f"Loading tokens for {len(files_with_loading_tokens)} files...")
            self.progress_label.setVisible(True)
        
        # Final setup steps
        self._calculate_and_store_total_tokens(root_item)
        self.update_folder_token_display()

        if self._pending_tree_restore_paths:
            for path in self._pending_tree_restore_paths:
                if path in self.tree_items:
                    self.tree_items[path].setCheckState(0, Qt.CheckState.Checked)
            self._pending_tree_restore_paths.clear()

        self.tree_widget.setUpdatesEnabled(True)
        self.tree_widget.expandToDepth(0)
        self.root_path_changed.emit(self.root_path)
        
    def update_file_token_count(self, file_path: str, token_count: int):
        """Update token count for a specific file."""
        norm_path = os.path.normpath(file_path).replace('\\', '/')
        if norm_path in self.tree_items:
            item = self.tree_items[norm_path]
            item.setData(1, self.TOKEN_COUNT_ROLE, token_count)
            
            if TIKTOKEN_AVAILABLE:
                item.setText(1, f"{token_count:,} tokens")
            else:
                item.setText(1, f"{token_count:,} chars")
                
            # Update total token display
            self._update_total_token_label()
            self.file_tokens_changed.emit(file_path, token_count)
            
    def update_file_validation(self, file_path: str, is_valid: bool, reason: str):
        """Update validation status for a specific file."""
        norm_path = os.path.normpath(file_path).replace('\\', '/')
        if norm_path in self.tree_items:
            item = self.tree_items[norm_path]
            
            if not is_valid:
                item.setText(1, reason)
                item.setForeground(1, self.error_color)
                item.setData(1, self.TOKEN_COUNT_ROLE, 0)
            
    def update_loading_progress(self, current: int, total: int):
        """Update the loading progress display."""
        if total > 0:
            if current < total:
                remaining = total - current
                self.progress_label.setText(f"Loading tokens... {current}/{total} complete ({remaining} remaining)")
                self.progress_label.setVisible(True)
            else:
                # All done
                self.progress_label.setVisible(False)
                self._update_total_token_label()
        else:
            self.progress_label.setVisible(False)

    def get_aggregated_content(self):
        """Aggregates content from checked files using the specified format."""
        aggregated_lines = []
        total_tokens = 0
        # We need absolute paths for reading files
        checked_absolute_paths = self.get_checked_paths(return_set=True, relative=False)

        for path_str in sorted(list(checked_absolute_paths)):
            path_obj = pathlib.Path(path_str)
            if not path_obj.is_file():
                continue

            try:
                # 1. Build the header line (relative path)
                relative_path_str = os.path.relpath(path_str, self.root_path)
                aggregated_lines.append(relative_path_str)

                # 2. Build the opening code-fence with language identifier
                _, file_extension = os.path.splitext(relative_path_str)
                language_identifier = file_extension.lstrip('.').lower() if file_extension else ""
                aggregated_lines.append(f"```{language_identifier}")

                # 3. Append the file’s actual content
                # Note: MAX_FILE_SIZE_BYTES is not defined, so reading the whole file.
                with open(path_obj, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                
                # Sanitize content to avoid breaking the markdown block
                sanitized_content = content.replace("```", "``·")
                aggregated_lines.append(sanitized_content)

                # 4. Close the code block
                aggregated_lines.append("```")
                aggregated_lines.append("")  # Blank line between files

                # Add to total tokens
                if path_str in self.tree_items:
                    total_tokens += self.tree_items[path_str].data(0, self.TOKEN_COUNT_ROLE) or 0

            except Exception as e:
                aggregated_lines.append(f"[Error reading file {relative_path_str}: {e}]")
                aggregated_lines.append("")

        return "\n".join(aggregated_lines), total_tokens

    def update_folder_token_display(self):
        if not TIKTOKEN_AVAILABLE: return
        self.tree_widget.setUpdatesEnabled(False)
        try:
            iterator = QTreeWidgetItemIterator(self.tree_widget, QTreeWidgetItemIterator.IteratorFlag.All)
            while iterator.value():
                item = iterator.value()
                # Check if it's a folder (has children or was marked as a directory)
                if item.data(0, self.IS_DIR_ROLE):
                    # Calculate selected tokens directly using BG_scanner token data
                    selected_tokens = 0
                    folder_iterator = QTreeWidgetItemIterator(item)
                    while folder_iterator.value():
                        child_item = folder_iterator.value()
                        # Add tokens only for checked files
                        if (child_item and not child_item.data(0, self.IS_DIR_ROLE) and 
                            child_item.checkState(0) == Qt.CheckState.Checked):
                            selected_tokens += child_item.data(0, self.TOKEN_COUNT_ROLE) or 0
                        folder_iterator += 1
                    
                    total_tokens = item.data(0, self.TOKEN_COUNT_ROLE) or 0
                    item.setText(1, f"{selected_tokens:,} / {total_tokens:,} tokens")
                iterator += 1
        finally:
            self.tree_widget.setUpdatesEnabled(True)

    @Slot(list)
    def update_from_fs_events(self, event_batch):
        self.tree_widget.setUpdatesEnabled(False)
        try:
            for event in event_batch:
                action = event['action']
                src_path = os.path.normpath(event['src_path']).replace('\\', '/')

                if action == 'created':
                    if src_path in self.tree_items or not os.path.exists(src_path):
                        continue
                    parent_path = os.path.dirname(src_path)
                    parent_item = self.tree_items.get(parent_path)
                    if parent_item:
                        is_dir = os.path.isdir(src_path)
                        # This part might need adjustment based on how tokens are calculated for new files
                        token_count = 0 if is_dir else count_tokens(src_path)
                        self._add_item_to_tree(parent_item, src_path, is_dir, True, '', token_count)

                elif action == 'deleted':
                    if src_path not in self.tree_items:
                        continue
                    item_to_remove = self.tree_items.pop(src_path)
                    parent = item_to_remove.parent()
                    if parent:
                        parent.removeChild(item_to_remove)

                elif action == 'moved':
                    dst_path = os.path.normpath(event['dst_path']).replace('\\', '/')
                    if src_path not in self.tree_items:
                        continue

                    item = self.tree_items.pop(src_path)
                    item.setText(0, os.path.basename(dst_path))
                    item.setData(0, self.PATH_DATA_ROLE, dst_path)
                    self.tree_items[dst_path] = item

                    # If it's a directory, update paths of all children
                    if item.data(0, self.IS_DIR_ROLE):
                        self._recursive_update_child_paths(item, src_path, dst_path)

                    # Check if parent needs to be changed
                    new_parent_path = os.path.dirname(dst_path)
                    old_parent_item = item.parent()
                    if old_parent_item and old_parent_item.data(0, self.PATH_DATA_ROLE) != new_parent_path:
                        new_parent_item = self.tree_items.get(new_parent_path, self.tree_widget.invisibleRootItem())
                        old_parent_item.removeChild(item)
                        new_parent_item.addChild(item)

        finally:
            self.tree_widget.setUpdatesEnabled(True)
            self.update_folder_token_display()
            self.item_checked_changed.emit()
        self.tree_widget.setUpdatesEnabled(False)
        try:
            for event in event_batch:
                action = event['action']
                src_path = os.path.normpath(event['src_path']).replace('\\', '/')

                if action == 'created':
                    if not os.path.exists(src_path) or src_path in self.tree_items:
                        continue
                    
                    parent_path = os.path.dirname(src_path).replace('\\', '/')
                    parent_item = self.tree_items.get(parent_path)

                    if not parent_item:
                        # Create parent directories if they don't exist
                        p = pathlib.Path(parent_path)
                        dirs_to_create = []
                        while str(p) != self.root_path and str(p).replace('\\', '/') not in self.tree_items:
                            dirs_to_create.append(p)
                            p = p.parent
                        
                        for dir_path_obj in reversed(dirs_to_create):
                            dir_path = str(dir_path_obj).replace('\\', '/')
                            parent_of_dir = os.path.dirname(dir_path)
                            parent_item = self.tree_items.get(parent_of_dir)
                            if parent_item:
                                self._add_item_to_tree(parent_item, dir_path, True, True, '', 0)
                    
                    parent_item = self.tree_items.get(parent_path)
                    if parent_item:
                        is_dir = os.path.isdir(src_path)
                        token_count = 0
                        if not is_dir:
                            try:
                                with open(src_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    content = f.read()
                                token_count = len(self.tokenizer.encode(content))
                            except Exception:
                                pass # Ignore files that can't be read
                        self._add_item_to_tree(parent_item, src_path, is_dir, True, '', token_count)

                elif action == 'deleted':
                    if src_path not in self.tree_items:
                        continue
                    item_to_remove = self.tree_items.pop(src_path)
                    
                    # Also remove all children from tree_items if it's a directory
                    iterator = QTreeWidgetItemIterator(item_to_remove)
                    while iterator.value():
                        child = iterator.value()
                        if child is not item_to_remove:
                            child_path = child.data(0, self.PATH_DATA_ROLE)

                elif action == 'modified':
                    if src_path not in self.tree_items:
                        continue
                    item = self.tree_items[src_path]
                    if not item.data(0, self.IS_DIR_ROLE):
                        try:
                            old_tokens = item.data(0, self.TOKEN_COUNT_ROLE) or 0
                            new_tokens = self.tokenizer.count_tokens(src_path)
                            item.setData(0, self.TOKEN_COUNT_ROLE, new_tokens)
                            item.setText(1, f"{new_tokens:,} tokens")
                            token_diff = new_tokens - old_tokens
                            if token_diff != 0:
                                self.file_tokens_changed.emit(src_path, token_diff)
                        except Exception as e:
                            item.setText(1, "Error reading")

                elif action == 'moved':
                    dst_path = os.path.normpath(event['dst_path']).replace('\\', '/')
                    if not dst_path or src_path not in self.tree_items:
                        continue

                    item_to_move = self.tree_items.pop(src_path)

                    # If a directory is moved, update paths for all its children
                    if item_to_move.data(0, self.IS_DIR_ROLE):
                        iterator = QTreeWidgetItemIterator(item_to_move, QTreeWidgetItemIterator.IteratorFlag.All)
                        while iterator.value():
                            child_item = iterator.value()
                            old_child_path = child_item.data(0, self.PATH_DATA_ROLE)
                            if old_child_path and old_child_path.startswith(src_path):
                                new_child_path = old_child_path.replace(src_path, dst_path, 1)
                                child_item.setData(0, self.PATH_DATA_ROLE, new_child_path)
                                if old_child_path in self.tree_items:
                                    self.tree_items.pop(old_child_path)
                                self.tree_items[new_child_path] = child_item
                            iterator += 1

                    # Update the moved item itself
                    item_to_move.setText(0, os.path.basename(dst_path))
                    item_to_move.setData(0, self.PATH_DATA_ROLE, dst_path)
                    self.tree_items[dst_path] = item_to_move

                    # Check if the parent directory changed and re-parent if necessary
                    old_parent_path = os.path.dirname(src_path)
                    new_parent_path = os.path.dirname(dst_path)
                    if old_parent_path != new_parent_path:
                        old_parent_item = item_to_move.parent()
                        if old_parent_item:
                            old_parent_item.removeChild(item_to_move)
                        new_parent_item = self.tree_items.get(new_parent_path) or self.tree_widget.invisibleRootItem()
                        new_parent_item.addChild(item_to_move)

        finally:
            self.tree_widget.setUpdatesEnabled(True)
            self.update_folder_token_display()
            self.item_checked_changed.emit()

    def _recursive_update_child_paths(self, item, old_base, new_base):
        """Recursively update the paths of child items when a directory is moved."""
        for i in range(item.childCount()):
            child = item.child(i)
            old_path = child.data(0, self.PATH_DATA_ROLE)
            if old_path in self.tree_items:
                del self.tree_items[old_path]
            
            new_path = old_path.replace(old_base, new_base, 1)
            child.setData(0, self.PATH_DATA_ROLE, new_path)
            self.tree_items[new_path] = child

            if child.data(0, self.IS_DIR_ROLE):
                self._recursive_update_child_paths(child, old_base, new_base)

    # --- Private Helper Methods ---

    def _add_item_to_tree(self, parent_item, path_str, is_dir, is_valid, reason, token_count):
        norm_path = os.path.normpath(path_str).replace('\\', '/')
        item = QTreeWidgetItem(parent_item or self.tree_widget.invisibleRootItem())
        item.setText(0, os.path.basename(path_str))
        item.setData(0, self.PATH_DATA_ROLE, norm_path)
        item.setData(0, self.IS_DIR_ROLE, is_dir)
        item.setIcon(0, self.folder_icon if is_dir else self.file_icon)

        if not is_valid:
            item.setDisabled(True)
            item.setText(1, reason)
            item.setForeground(1, self.error_color)
        else:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            if is_dir:
                item.setData(0, self.TOKEN_COUNT_ROLE, 0)  # Placeholder
            else:
                item.setData(0, self.TOKEN_COUNT_ROLE, token_count)
                item.setText(1, f"{token_count:,} tokens")

        self.tree_items[norm_path] = item
        return item

    # REMOVED: _calculate_selected_tokens_for_folder method
    # Selected token calculation now uses BG_scanner token data directly from tree items

    # REMOVED: _calculate_and_store_total_tokens method
    # Token data is now set directly from BG_scanner results for maximum performance









    def _update_total_token_label(self):
        total_tokens = 0
        iterator = QTreeWidgetItemIterator(self.tree_widget, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            if not item.data(0, self.IS_DIR_ROLE):
                total_tokens += item.data(0, self.TOKEN_COUNT_ROLE) or 0
            iterator += 1
        self.token_count_label.setText(f"Total tokens: {total_tokens:,}")
