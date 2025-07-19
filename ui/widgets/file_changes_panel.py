from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Slot
import os
from collections import deque

class FileChangesPanel(QWidget):
    """A panel to display a consolidated log of recent file token changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.root_path = None
        self.file_changes = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        title_label = QLabel("Recent File Changes")
        title_label.setFont(QFont("Arial", 10, QFont.Bold))
        layout.addWidget(title_label)

        self.changes_list = QListWidget()
        self.changes_list.setWordWrap(True)
        layout.addWidget(self.changes_list)

    def set_root_path(self, path):
        """Sets the root directory to make file paths relative."""
        self.root_path = path
        self.file_changes.clear()
        self._update_display()

    @Slot(str, int)
    def add_change_entry(self, file_path, token_diff):
        """Adds a new token change and updates the display."""
        if token_diff == 0:
            return
        self._add_entry(file_path, token_diff)

    @Slot(list)
    def update_with_fs_events(self, event_batch):
        """Updates the panel with file system events like creation, deletion, and moves."""
        for event in event_batch:
            action = event['action']
            src_path = event['src_path']
            
            if action == 'created':
                self._add_entry(src_path, "added")
            elif action == 'deleted':
                self._add_entry(src_path, "removed")
            elif action == 'moved':
                dst_path = event['dst_path']
                display_src_path = self._get_display_path(src_path)
                self._add_entry(dst_path, f"renamed from {display_src_path}")

    def _add_entry(self, file_path, change_info):
        if file_path not in self.file_changes:
            self.file_changes[file_path] = deque(maxlen=5)
        self.file_changes[file_path].appendleft(change_info)
        self._update_display()

    def _get_display_path(self, path):
        """
        Generates a display path that does not include the root path.
        """
        if self.root_path:
            try:
                return os.path.relpath(path, self.root_path)
            except ValueError:
                pass  # Fall through
        return os.path.basename(path)

    def _update_display(self):
        """Clears and repopulates the list widget with consolidated changes."""
        self.changes_list.clear()
        
        for file_path, changes in self.file_changes.items():
            if not changes:
                continue

            display_path = self._get_display_path(file_path)

            
            change_parts = []
            for c in changes:
                if isinstance(c, int):
                    change_parts.append(f"{'+' if c > 0 else ''}{c} tokens")
                else:
                    change_parts.append(str(c))
            changes_str = ", ".join(change_parts)
            text = f"{display_path}  ({changes_str})"

            item = QListWidgetItem(text)

            # Color based on the most recent change
            most_recent = changes[0]
            if isinstance(most_recent, int):
                item.setForeground(QColor("green") if most_recent > 0 else QColor("red"))
            elif "add" in most_recent or "renamed" in most_recent:
                item.setForeground(QColor("green"))
            elif "remov" in most_recent:
                item.setForeground(QColor("red"))

            self.changes_list.addItem(item)
