from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLabel, QPushButton, QStyle
)
from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QFont
import pyperclip
import sys

class AggregationView(QWidget):
    """A widget to display aggregated content, token count, and a copy button."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._system_prompt = ""
        self._aggregated_text = ""
        self._aggregated_tokens = 0
        self._full_content = ""
        self._content_file_path = ""
        self._content_file_paths = []
        self._setup_ui()
        self._connect_signals()
        self._preview_limit = 20000

    def _setup_ui(self):
        """Sets up the widgets within this panel."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 5)

        self.token_info_label = QLabel("Total Tokens: 0")
        self.token_info_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        # Make it bold and slightly larger for better visibility
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        self.token_info_label.setFont(font)
        layout.addWidget(self.token_info_label)

        self.aggregation_output = QTextEdit()
        self.aggregation_output.setReadOnly(True)
        self.aggregation_output.setPlaceholderText("Select files/folders from the tree to aggregate their content here...")
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamily("Courier New" if sys.platform == 'win32' else "Monaco" if sys.platform == 'darwin' else "monospace")
        self.aggregation_output.setFont(font)
        self.aggregation_output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.aggregation_output)

        self.copy_button = QPushButton("Copy Aggregated Content to Clipboard")
        self.copy_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        layout.addWidget(self.copy_button)
        self.save_chunks_button = QPushButton("Save All Chunks")
        self.save_chunks_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        self.save_chunks_button.setVisible(False)
        layout.addWidget(self.save_chunks_button)
        self.manual_start_button = QPushButton("Start Aggregation")
        self.manual_start_button.setVisible(False)
        layout.addWidget(self.manual_start_button)
        self.chunk_buttons_container = QWidget()
        self.chunk_buttons_layout = QVBoxLayout(self.chunk_buttons_container)
        self.chunk_buttons_layout.setContentsMargins(0,0,0,0)
        layout.addWidget(self.chunk_buttons_container)

    def update_token_count(self, count: int):
        """Update the token count display immediately."""
        self.token_info_label.setText(f"Total Tokens: {count:,}")

    def _connect_signals(self):
        """Connects the copy button's clicked signal."""
        self.copy_button.clicked.connect(self._copy_to_clipboard)
        self.save_chunks_button.clicked.connect(lambda: self.save_chunks_requested.emit(self._content_file_paths))
        self.manual_start_button.clicked.connect(lambda: self.start_aggregation_requested.emit())

    @Slot()
    def _copy_to_clipboard(self):
        """Copies the content of the aggregation output to the clipboard."""
        content = ""
        
        # Case 1: Multiple chunk files (chunked aggregation)
        if self._content_file_paths:
            try:
                parts = []
                total_size = 0
                for i, p in enumerate(self._content_file_paths):
                    # Verify file exists and check size
                    import os
                    if not os.path.exists(p):
                        print(f"[COPY] ❌ ERROR: Chunk file does not exist: {p}")
                        return False
                    
                    file_size = os.path.getsize(p)
                    print(f"[COPY] 📁 Chunk file {i+1} size on disk: {file_size:,} bytes")
                    
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        chunk_content = f.read()
                        parts.append(chunk_content)
                        chunk_size = len(chunk_content)
                        total_size += chunk_size
                        print(f"[COPY] 📄 Chunk {i+1}/{len(self._content_file_paths)}: {chunk_size:,} characters")
                        
                        # Debug: Show sample of content to verify it's not just headers
                        if chunk_size > 1000:
                            print(f"[COPY] 📝 First 200 chars: {chunk_content[:200]}")
                            print(f"[COPY] 📝 Last 200 chars: {chunk_content[-200:]}")
                
                content = "".join(parts)
                print(f"[COPY] ✅ Full content from {len(self._content_file_paths)} chunks copied: {total_size:,} total characters")
                
                # CRITICAL: Save backup copy to known location for verification
                backup_path = os.path.expanduser("~/Documents/contextm_aggregation_backup.txt")
                try:
                    with open(backup_path, "w", encoding="utf-8", errors="replace") as f:
                        f.write(content)
                    backup_size = os.path.getsize(backup_path)
                    print(f"[COPY] 💾 Backup saved to: {backup_path} ({backup_size:,} bytes)")
                    print(f"[COPY] 💾 You can open this file to verify the full content!")
                except Exception as e:
                    print(f"[COPY] ⚠️ Could not save backup: {e}")
                
            except Exception as e:
                print(f"[COPY] ❌ Error copying full content: {e}")
                import traceback
                traceback.print_exc()
                return False
                
        # Case 2: Single file (non-chunked aggregation)
        elif self._content_file_path:
            try:
                with open(self._content_file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                print(f"[COPY] ✅ Content from single file copied: {len(content):,} characters")
            except Exception as e:
                print(f"[COPY] ⚠️ Error reading file, falling back to text view: {e}")
                content = self.aggregation_output.toPlainText()
                
        # Case 3: In-memory content (small aggregations)
        else:
            content = self._full_content or self.aggregation_output.toPlainText()
            print(f"[COPY] ✅ In-memory content copied: {len(content):,} characters")
        
        # Verify content before copying
        print(f"[COPY] 📋 About to copy {len(content):,} characters to clipboard")
        print(f"[COPY] 📝 Content starts with: {content[:100]}")
        print(f"[COPY] 📝 Content ends with: {content[-100:]}")
        
        # Count how many file blocks are in the content
        file_block_count = content.count("```")
        print(f"[COPY] 📊 Content contains {file_block_count} code fence markers (should be 2 per file)")
        
        # CRITICAL FIX: Remove null bytes that kill the clipboard
        # Binary files like .DS_Store contain \x00 which pyperclip/Windows clipboard treats as string termination
        original_len = len(content)
        content = content.replace('\x00', '')
        null_bytes_removed = original_len - len(content)
        if null_bytes_removed > 0:
            print(f"[COPY] 🧹 Sanitized: Removed {null_bytes_removed} null bytes from content")
        
        # Copy to clipboard using Qt (more robust than pyperclip for GUI apps)
        try:
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(content)
            print(f"[COPY] 📋 Qt clipboard.setText() completed successfully")
            
            # VERIFY: Try to read back from clipboard
            verified_content = clipboard.text()
            verified_len = len(verified_content)
            print(f"[COPY] 🔍 Verification: clipboard now contains {verified_len:,} characters")
            
            if verified_len != len(content):
                print(f"[COPY] ❌ WARNING: Clipboard content length mismatch!")
                print(f"[COPY] ❌ Expected: {len(content):,}, Got: {verified_len:,}")
                print(f"[COPY] ❌ Data loss: {len(content) - verified_len:,} characters")
                print(f"[COPY] 💡 TIP: Use the backup file at ~/Documents/contextm_aggregation_backup.txt instead!")
            else:
                print(f"[COPY] ✅ Clipboard verification passed - full content copied!")
            
            return True
        except Exception as e:
            print(f"[COPY] ❌ Error copying to clipboard: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _copy_chunk_to_clipboard(self, index: int):
        if index < 0 or index >= len(self._content_file_paths):
            return False
        try:
            with open(self._content_file_paths[index], "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            pyperclip.copy(content)
            print(f"Chunk {index+1} copied to clipboard.")
            return True
        except Exception as e:
            print(f"Error copying chunk {index+1}: {e}")
            return False

    @Slot(str)
    def set_system_prompt(self, prompt):
        """Sets the system prompt and updates the display."""
        self._system_prompt = prompt
        self._update_display()

    # Public façade for tests
    def get_content(self):
        return self.aggregation_output.toPlainText()

    def set_content(self, text, token_count=None):
        """Ultra-safe content setter for huge aggregations.

        Stores the full text for clipboard use, but only renders a small
        preview in the QTextEdit and aggressively disables expensive painting
        operations to keep the UI responsive even with 800k+ tokens.
        """
        from PySide6.QtWidgets import QTextEdit

        # Store full content for copy operations
        self._full_content = text or ""
        self._content_file_path = ""
        self._content_file_paths = []

        # Update Token Label
        count_str = f"{token_count:,}" if token_count is not None else "0"
        self.token_info_label.setText(f"Total Tokens: {count_str}")
        self.copy_button.setText(f"Copy Full (~{count_str} tokens)")

        # Preview settings
        preview_limit = self._preview_limit
        text_length = len(self._full_content)

        self.aggregation_output.blockSignals(True)
        self.aggregation_output.setUpdatesEnabled(False)
        try:
            self.aggregation_output.clear()

            # Force NoWrap for anything moderately large to avoid layout churn
            if text_length > 5000:
                self.aggregation_output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            else:
                self.aggregation_output.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

            if text_length > preview_limit:
                preview_text = self._full_content[:preview_limit]
                footer = (
                    "\n\n"
                    "########################################################################\n"
                    f"#  PREVIEW TRUNCATED (Showing first {preview_limit:,} of {text_length:,} characters)\n"
                    f"#  Full content ({token_count} tokens) is ready in memory.\n"
                    "#  Click 'Copy to Clipboard' to paste into LLM.\n"
                    "########################################################################\n"
                )
                self.aggregation_output.setPlainText(preview_text + footer)
            else:
                self.aggregation_output.setPlainText(self._full_content)

            # Reset scroll to top
            cursor = self.aggregation_output.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.aggregation_output.setTextCursor(cursor)

        finally:
            self.aggregation_output.setUpdatesEnabled(True)
            self.aggregation_output.blockSignals(False)

    def set_loading(self, is_loading):
        if is_loading:
            self.token_info_label.setText("Processing... 0%")
            self.aggregation_output.setPlaceholderText("Generating aggregation...")
            # Do not clear content immediately to avoid flicker; just lock UI
            self.aggregation_output.setReadOnly(True)
            self.copy_button.setEnabled(False)
        else:
            # Will be overwritten by set_content
            self.token_info_label.setText("")
            self.aggregation_output.setReadOnly(True)
            self.copy_button.setEnabled(True)

    def set_content_from_file(self, file_path: str, token_count: int):
        self._content_file_path = file_path or ""
        self._full_content = ""
        self._content_file_paths = []
        count_str = f"{token_count:,}" if token_count is not None else "0"
        self.token_info_label.setText(f"Total Tokens: {count_str}")
        self.copy_button.setText(f"Copy Full (~{count_str} tokens)")
        preview_limit = self._preview_limit
        preview_text = ""
        try:
            with open(self._content_file_path, "r", encoding="utf-8", errors="replace") as f:
                preview_text = f.read(preview_limit)
        except Exception:
            preview_text = ""
        footer = (
            "\n\n"
            "########################################################################\n"
            f"#  PREVIEW TRUNCATED (Showing first {preview_limit:,} characters)\n"
            f"#  Full content ({token_count} tokens) is stored on disk.\n"
            "#  Click 'Copy to Clipboard' to load and paste into LLM.\n"
            "########################################################################\n"
        )
        self.aggregation_output.blockSignals(True)
        self.aggregation_output.setUpdatesEnabled(False)
        try:
            self.aggregation_output.clear()
            from PySide6.QtWidgets import QTextEdit
            self.aggregation_output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.aggregation_output.setPlainText(preview_text + footer)
            cursor = self.aggregation_output.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.aggregation_output.setTextCursor(cursor)
        finally:
            self.aggregation_output.setUpdatesEnabled(True)
            self.aggregation_output.blockSignals(False)

        for i in range(self.chunk_buttons_layout.count()):
            w = self.chunk_buttons_layout.itemAt(0).widget()
            if w:
                w.setParent(None)

    def set_preview_limit(self, limit: int):
        try:
            v = int(limit)
            self._preview_limit = max(1000, min(v, 1000000))
        except Exception:
            pass

    def set_chunked_content(self, file_paths: list, total_tokens: int, chunk_tokens: list = None):
        self._content_file_paths = file_paths or []
        self._content_file_path = ""
        self._full_content = ""
        count_str = f"{total_tokens:,}"
        self.token_info_label.setText(f"Total Tokens: {count_str}")
        self.copy_button.setText(f"Copy Full (~{count_str} tokens)")
        self.save_chunks_button.setVisible(bool(self._content_file_paths))
        self.manual_start_button.setVisible(False)
        preview_limit = self._preview_limit
        preview_text = ""
        if self._content_file_paths:
            try:
                with open(self._content_file_paths[0], "r", encoding="utf-8", errors="replace") as f:
                    preview_text = f.read(preview_limit)
            except Exception:
                preview_text = ""
        footer = (
            "\n\n"
            "########################################################################\n"
            f"#  PREVIEW TRUNCATED (Showing first {preview_limit:,} characters)\n"
            f"#  Content split into {len(self._content_file_paths)} chunks.\n"
            "#  Use the buttons below to copy each chunk.\n"
            "########################################################################\n"
        )
        self.aggregation_output.blockSignals(True)
        self.aggregation_output.setUpdatesEnabled(False)
        try:
            self.aggregation_output.clear()
            from PySide6.QtWidgets import QTextEdit
            self.aggregation_output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
            self.aggregation_output.setPlainText(preview_text + footer)
            cursor = self.aggregation_output.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.aggregation_output.setTextCursor(cursor)
        finally:
            self.aggregation_output.setUpdatesEnabled(True)
            self.aggregation_output.blockSignals(False)

        for i in range(self.chunk_buttons_layout.count()):
            w = self.chunk_buttons_layout.itemAt(0).widget()
            if w:
                w.setParent(None)
        for idx, _ in enumerate(self._content_file_paths):
            token_label = ""
            if chunk_tokens and idx < len(chunk_tokens):
                token_label = f" (~{chunk_tokens[idx]:,} tokens)"
            btn = QPushButton(f"Copy Chunk {idx+1}{token_label}")
            btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
            def make_handler(i):
                return lambda: self._copy_chunk_to_clipboard(i)
            btn.clicked.connect(make_handler(idx))
            self.chunk_buttons_layout.addWidget(btn)

    def set_manual_start_visible(self, visible: bool, tokens: int):
        self.manual_start_button.setVisible(visible)
        if visible:
            self.save_chunks_button.setVisible(False)
            self.token_info_label.setText(f"Ready to aggregate • ~{tokens:,} tokens")

    def update_loading_text(self, text: str):
        """Update the token label while aggregation is in progress."""
        self.token_info_label.setText(text)

    def _update_display(self):
        """Constructs the full output from prompt and content and updates the view."""
        full_text = self._aggregated_text
        if self._system_prompt:
            full_text = f"--- System Prompt ---\n{self._system_prompt}\n\n--- File Tree ---\n{self._aggregated_text}"
        
        # This is a simplification; a real implementation would need to recalculate total tokens.
        # For now, we'll just show the aggregated file tokens.
        self.aggregation_output.setPlainText(full_text)
        self.token_info_label.setText(f"File Tokens: {self._aggregated_tokens:,}")
    save_chunks_requested = Signal(list)
    start_aggregation_requested = Signal()
