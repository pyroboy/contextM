from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, 
    QLabel, QProgressBar, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal
from ui.helpers.aggregation_helper import AggregationWorker

class AggregationView(QWidget):
    # Signal for when manual aggregation start is needed
    start_aggregation_requested = Signal()
    save_chunks_requested = Signal(list)
    
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
        
        # Progress Bar (Hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setRange(0, 100)
        header_layout.addWidget(self.progress_bar)
        
        header_layout.addStretch()
        self.layout.addLayout(header_layout)

        # -- Main Content Area (Read Only Preview) --
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
        
        # Reset UI for new scan
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_copy.setEnabled(False)
        self.stats_label.setText("Initializing...")
        
        # Setup Worker Thread
        self.worker = AggregationWorker(file_paths)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        # Connect Signals
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
        if not self.chunks: 
            return
            
        # Get first chunk for preview
        preview_content = self.chunks[0]
        
        # SMART TRUNCATION: Limit display to 20k chars to prevent UI freeze
        # This solves the "Hanging on 800k tokens" issue
        MAX_DISPLAY_CHARS = 20000
        
        if len(preview_content) > MAX_DISPLAY_CHARS or len(self.chunks) > 1:
            display_text = preview_content[:MAX_DISPLAY_CHARS]
            
            # Calculate total size across all chunks
            total_chars = sum(len(c) for c in self.chunks)
            
            msg = (f"\n\n... [DISPLAY TRUNCATED FOR PERFORMANCE] ...\n"
                   f"... [Total Context Size: {total_chars:,} characters] ...\n"
                   f"... [Click 'Copy Full Context' to grab everything] ...")
            
            self.text_display.setPlainText(display_text + msg)
        else:
            self.text_display.setPlainText(preview_content)

    def copy_to_clipboard(self):
        if not self.chunks: 
            return
        
        print("[COPY] 🔄 Preparing to copy...")
        
        # Join all internal chunks into one Master String
        full_content = "".join(self.chunks)
        
        # 1. Verification Logic: Check for Null Bytes again (safety double-check)
        null_count = full_content.count('\x00')
        if null_count > 0:
            print(f"[COPY] 🧹 Sanitized: Removed {null_count} null bytes")
            full_content = full_content.replace('\x00', '')
        else:
            print("[COPY] 🧹 Sanitized: No null bytes found.")

        # 2. Use Qt Clipboard (Robust)
        clipboard = QApplication.clipboard()
        clipboard.setText(full_content)
        
        # 3. Verification Logic: Compare Buffer vs Clipboard
        copied_text = clipboard.text()
        if len(copied_text) == len(full_content):
            print("[COPY] ✅ Clipboard verification passed")
            self.stats_label.setText(f"✅ Copied {len(full_content):,} chars to clipboard!")
        else:
            print(f"[COPY] ❌ Verification FAILED. Expected {len(full_content)}, got {len(copied_text)}")
            self.stats_label.setText("❌ Copy Error (Check Console)")
    
    # Compatibility methods for existing main_window integration
    def set_manual_start_visible(self, visible, token_count=0):
        """Legacy method for manual start button"""
        pass
    
    def set_loading(self, is_loading):
        """Legacy method for loading state"""
        self.progress_bar.setVisible(is_loading)
        if not is_loading:
            self.btn_copy.setEnabled(True)
    
    def update_loading_text(self, text):
        """Legacy method for loading text"""
        self.stats_label.setText(text)
