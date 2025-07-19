from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QLabel, QHeaderView, 
    QTreeWidgetItem, QTreeWidgetItemIterator, QStyle
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon

import os
import pathlib

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
        self.clear_tree()
        self.root_path = os.path.normpath(root_path).replace('\\', '/')
        self.tree_widget.setUpdatesEnabled(False)

        root_item = self._add_item_to_tree(
            self.tree_widget.invisibleRootItem(), self.root_path, True, True, '', 0
        )

        # Step 1: Collect all directory paths that need to exist.
        all_required_dirs = {self.root_path}
        for path_str, is_dir, _, _, _ in items:
            norm_path = os.path.normpath(path_str).replace('\\', '/')
            path_to_ascend = norm_path if is_dir else os.path.dirname(norm_path)
            p = pathlib.Path(path_to_ascend)
            while p and str(p) != self.root_path and len(str(p)) >= len(self.root_path):
                all_required_dirs.add(str(p).replace('\\', '/'))
                p = p.parent

        # Step 2: Create all directory items. Sorting ensures parents are created before children.
        for dir_path in sorted(list(all_required_dirs)):
            if dir_path == self.root_path or dir_path in self.tree_items:
                continue
            parent_path = os.path.dirname(dir_path)
            parent_item = self.tree_items.get(parent_path)
            if parent_item:
                self._add_item_to_tree(parent_item, dir_path, True, True, '', 0)

        # Step 3: Create all file items.
        for path_str, is_dir, is_valid, reason, token_count in items:
            if not is_dir:
                norm_path = os.path.normpath(path_str).replace('\\', '/')
                parent_path = os.path.dirname(norm_path)
                parent_item = self.tree_items.get(parent_path)
                if parent_item:
                    self._add_item_to_tree(parent_item, norm_path, False, is_valid, reason, token_count)

        # Final setup steps.
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
                    selected_tokens = self._calculate_selected_tokens_for_folder(item)
                    total_tokens = item.data(0, self.TOKEN_COUNT_ROLE) or 0
                    item.setText(1, f"{selected_tokens:,} / {total_tokens:,} tokens")
                iterator += 1
        finally:
            self.tree_widget.setUpdatesEnabled(True)

    @Slot(list)
    def handle_fs_events(self, event_batch):
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
                            if child_path in self.tree_items:
                                del self.tree_items[child_path]
                        iterator += 1

                    parent_item = item_to_remove.parent()
                    (parent_item or self.tree_widget.invisibleRootItem()).removeChild(item_to_remove)

                    # Recursively remove empty parent directories
                    while parent_item and parent_item.childCount() == 0:
                        parent_path = parent_item.data(0, self.PATH_DATA_ROLE)
                        if parent_path == self.root_path:
                            break
                        
                        grandparent_item = parent_item.parent()
                        (grandparent_item or self.tree_widget.invisibleRootItem()).removeChild(parent_item)
                        if parent_path in self.tree_items:
                            del self.tree_items[parent_path]
                        parent_item = grandparent_item

                elif action == 'modified':
                    if src_path in self.tree_items and not self.tree_items[src_path].data(0, self.IS_DIR_ROLE):
                        item = self.tree_items[src_path]
                        old_token_count = item.data(0, self.TOKEN_COUNT_ROLE) or 0
                        try:
                            with open(src_path, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()
                            new_token_count = len(self.tokenizer.encode(content))
                            item.setData(0, self.TOKEN_COUNT_ROLE, new_token_count)
                            item.setText(1, f"{new_token_count:,} tokens")
                            token_diff = new_token_count - old_token_count
                            if token_diff != 0:
                                self.file_tokens_changed.emit(src_path, token_diff)
                        except Exception as e:
                            item.setText(1, "Error reading")

                elif action == 'moved':
                    dst_path = os.path.normpath(event['dst_path']).replace('\\', '/')
                    if not dst_path or src_path not in self.tree_items:
                        continue

                    # Remove the old item
                    old_item = self.tree_items.pop(src_path)
                    parent_item = old_item.parent() or self.tree_widget.invisibleRootItem()
                    parent_item.removeChild(old_item)

                    # Add the new item
                    is_dir = os.path.isdir(dst_path)
                    token_count = old_item.data(0, self.TOKEN_COUNT_ROLE) or 0
                    
                    new_item = self._add_item_to_tree(parent_item, dst_path, is_dir, True, '', token_count)
                    
                    # Restore check state
                    new_item.setCheckState(0, old_item.checkState(0))

        finally:
            self.tree_widget.setUpdatesEnabled(True)
            self.update_folder_token_display()
            self.item_checked_changed.emit()

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

    def _calculate_selected_tokens_for_folder(self, folder_item):
        """Recursively calculates the total tokens of checked items within a folder."""
        selected_tokens = 0
        iterator = QTreeWidgetItemIterator(folder_item)
        while iterator.value():
            item = iterator.value()
            # Add tokens only for checked files
            if item and not item.data(0, self.IS_DIR_ROLE) and item.checkState(0) == Qt.CheckState.Checked:
                selected_tokens += item.data(0, self.TOKEN_COUNT_ROLE) or 0
            iterator += 1
        return selected_tokens

    def _calculate_and_store_total_tokens(self, item):
        """Recursively calculates and stores total tokens for a folder item."""
        # Base case: item is a file, its token count is already stored.
        if not item.childCount() > 0:
            return item.data(0, self.TOKEN_COUNT_ROLE) or 0

        total_tokens = 0
        for i in range(item.childCount()):
            child = item.child(i)
            total_tokens += self._calculate_and_store_total_tokens(child)
        
        item.setData(0, self.TOKEN_COUNT_ROLE, total_tokens)
        return total_tokens









    def _update_total_token_label(self):
        total_tokens = 0
        iterator = QTreeWidgetItemIterator(self.tree_widget, QTreeWidgetItemIterator.IteratorFlag.Checked)
        while iterator.value():
            item = iterator.value()
            if not item.data(0, self.IS_DIR_ROLE):
                total_tokens += item.data(0, self.TOKEN_COUNT_ROLE) or 0
            iterator += 1
        self.token_count_label.setText(f"Total tokens: {total_tokens:,}")
