from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, 
    QLabel, QProgressBar, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from ui.helpers.aggregation_helper import AggregationWorker

class AggregationView(QWidget):
    # Signals for main_window compatibility
    save_chunks_requested = Signal(list)
    start_aggregation_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chunks = []
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(10, 10, 10, 10)

        # -- Header: Stats & Progress --
        header_layout = QHBoxLayout()
        
        self.stats_label = QLabel("Ready")
        self.stats_label.setStyleSheet("font-weight: bold; color: #555;")
        header_layout.addWidget(self.stats_label)
        
        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 100)
        header_layout.addWidget(self.progress_bar)
        
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        # -- Main Content Area --
        self.text_display = QTextEdit()
        self.text_display.setReadOnly(True)
        self.text_display.setPlaceholderText("Aggregation results will appear here...")
        self.layout.addWidget(self.text_display)

        # -- Footer: Master Copy Button --
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()

        self.btn_copy = QPushButton("📋 Copy Full Context to Clipboard")
        self.btn_copy.setStyleSheet("background-color: #2da44e; color: white; font-weight: bold; padding: 8px 20px; border-radius: 4px;")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self.copy_to_clipboard)
        
        controls_layout.addWidget(self.btn_copy)
        controls_layout.addStretch()

        self.layout.addLayout(controls_layout)

    def start_aggregation(self, file_paths):
        if not file_paths:
            self.stats_label.setText("No files selected.")
            return

        self.text_display.clear()
        self.text_display.setPlaceholderText("Scanning and aggregating files...")
        
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_copy.setEnabled(False)
        self.stats_label.setText("Initializing...")
        
        self.worker = AggregationWorker(file_paths)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_aggregation_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.worker.progress_update.connect(self.update_progress)
        self.worker.token_update.connect(self.update_token_count)
        
        self.thread.start()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Processing: {current}/{total} files")

    def update_token_count(self, tokens):
        self.stats_label.setText(f"⚡ Tokens: {tokens:,}")

    def on_aggregation_finished(self, result):
        self.progress_bar.setVisible(False)
        self.btn_copy.setEnabled(True)
        
        self.chunks = result.get("chunks", [])
        total_tokens = result.get("total_tokens", 0)
        file_count = result.get("file_count", 0)
        
        self.stats_label.setText(f"✅ Done: {file_count} files | {total_tokens:,} tokens")
        
        if not self.chunks:
            self.text_display.setPlainText("No content found.")
            return
            
        self.display_preview()

    def display_preview(self):
        if not self.chunks: return
            
        preview_content = self.chunks[0]
        MAX_DISPLAY_CHARS = 20000
        
        if len(preview_content) > MAX_DISPLAY_CHARS or len(self.chunks) > 1:
            display_text = preview_content[:MAX_DISPLAY_CHARS]
            total_chars = sum(len(c) for c in self.chunks)
            msg = (f"\n\n... [DISPLAY TRUNCATED FOR PERFORMANCE] ...\n"
                   f"... [Total Context Size: {total_chars:,} characters] ...\n"
                   f"... [Click 'Copy Full Context' to grab everything] ...")
            self.text_display.setPlainText(display_text + msg)
        else:
            self.text_display.setPlainText(preview_content)

    def copy_to_clipboard(self):
        if not self.chunks: return
        
        print("[COPY] 🔄 Preparing to copy...")
        full_content = "".join(self.chunks)
        
        # 1. Sanitize Logic
        null_count = full_content.count('\x00')
        if null_count > 0:
            print(f"[COPY] 🧹 Sanitized: Removed {null_count} null bytes")
            full_content = full_content.replace('\x00', '')
        else:
            print("[COPY] 🧹 Sanitized: No null bytes found.")

        # 2. Copy to Qt Clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(full_content)
        
        # 3. Verification Logic
        copied_text = clipboard.text()
        if len(copied_text) == len(full_content):
            print("[COPY] ✅ Clipboard verification passed")
            self.stats_label.setText(f"✅ Copied {len(full_content):,} chars to clipboard!")
        else:
            print(f"[COPY] ❌ Verification FAILED. Expected {len(full_content)}, got {len(copied_text)}")
            self.stats_label.setText("❌ Copy Error (Check Console)")
    
    # ============================================================================
    # COMPATIBILITY METHODS FOR MAIN_WINDOW INTEGRATION
    # ============================================================================
    def set_manual_start_visible(self, visible, token_count=0):
        """Compatibility method - not used in new architecture"""
        pass
    
    def set_loading(self, is_loading):
        """Compatibility method for loading state"""
        self.progress_bar.setVisible(is_loading)
        if not is_loading:
            self.btn_copy.setEnabled(True)
    
    def update_loading_text(self, text):
        """Compatibility method for loading text"""
        self.stats_label.setText(text)
    
    def set_content(self, text, token_count=None):
        """Compatibility - auto-trigger display when content is set"""
        # This is called by old main_window code
        # Just display the preview
        self.chunks = [text] if text else []
        if token_count:
            self.stats_label.setText(f"✅ Done | {token_count:,} tokens")
        self.display_preview()
    
    def set_chunked_content(self, file_paths, total_tokens, chunk_tokens=None):
        """Compatibility - not fully supported in new architecture"""
        # Old architecture used temp files, new one uses in-memory chunks
        # Here we adapt by actually reading the chunk files so that:
        # - The textbox shows a real preview of aggregated content
        # - The Copy button has the full context in self.chunks
        import os

        self.chunks = []

        if not file_paths:
            self.stats_label.setText("No files selected.")
            self.text_display.setPlainText("No content found.")
            return

        total_chars = 0
        for path in file_paths:
            try:
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                if not content:
                    continue
                # Sanitize null bytes defensively
                if '\x00' in content:
                    null_count = content.count('\x00')
                    print(f"[AGG_VIEW] ⚠️ Stripping {null_count} null bytes from chunk: {path}")
                    content = content.replace('\x00', '')
                self.chunks.append(content)
                total_chars += len(content)
            except Exception as e:
                print(f"[AGG_VIEW] ❌ Error reading aggregation chunk '{path}': {e}")

        # Update stats and show preview
        file_count = len(file_paths)
        self.stats_label.setText(f"✅ Done: {file_count} files | {total_tokens:,} tokens | {total_chars:,} chars")

        if not self.chunks:
            self.text_display.setPlainText("No content found.")
            return

        self.display_preview()
    
    def set_content_from_file(self, file_path, token_count):
        """Compatibility - read file and display"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.chunks = [content]
            self.stats_label.setText(f"✅ Done | {token_count:,} tokens")
            self.display_preview()
        except Exception as e:
            print(f"Error reading file: {e}")
    
    def update_token_count(self, count):
        """Update token display"""
        self.stats_label.setText(f"⚡ Tokens: {count:,}")

