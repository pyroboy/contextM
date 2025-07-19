# --- File: qt_thread_tokenizer.py ---
"""
Robust QThread-based tokenizer that's fully compatible with Qt and won't interfere with the main thread.
Replaces the problematic multiprocessing approach with Qt-native threading.
"""

import os
import time
from typing import List, Tuple
from PySide6.QtCore import QObject, Signal, QThread, QTimer
from PySide6.QtWidgets import QApplication


class TokenizerWorkerThread(QThread):
    """
    QThread worker that tokenizes files in batches without blocking the main thread.
    """
    
    # Signals
    file_tokenized = Signal(str, int, bool, str)  # file_path, token_count, is_valid, reason
    batch_completed = Signal(int, int)  # completed_count, total_count
    progress_update = Signal(str)  # status message
    
    def __init__(self, file_paths: List[str], batch_size: int = 5):
        super().__init__()
        self.file_paths = file_paths
        self.batch_size = batch_size
        self.should_stop = False
        self.completed_count = 0
        self.total_count = len(file_paths)
        
        print(f"[QT_TOKENIZER] 🧵 Created worker thread for {self.total_count} files (batch size: {batch_size})")
    
    def run(self):
        """Main thread execution - processes files in batches with yielding to keep UI responsive."""
        print(f"[QT_TOKENIZER] 🚀 Worker thread started, processing {self.total_count} files...")
        
        try:
            # Import inside thread to avoid issues
            from core.helpers import calculate_tokens, MAX_FILE_SIZE_BYTES
            from core.smart_file_handler import SmartFileHandler
            
            batch_count = 0
            for i in range(0, len(self.file_paths), self.batch_size):
                if self.should_stop:
                    print(f"[QT_TOKENIZER] ⏹️ Worker thread stopped by request")
                    break
                
                batch = self.file_paths[i:i + self.batch_size]
                batch_count += 1
                
                print(f"[QT_TOKENIZER] 📦 Processing batch {batch_count} ({len(batch)} files)...")
                self.progress_update.emit(f"Processing batch {batch_count}...")
                
                for file_path in batch:
                    if self.should_stop:
                        break
                    
                    try:
                        # Process single file
                        result = self._tokenize_single_file(file_path, calculate_tokens, MAX_FILE_SIZE_BYTES, SmartFileHandler)
                        file_path, token_count, is_valid, reason = result
                        
                        print(f"[QT_TOKENIZER] ✅ Tokenized {os.path.basename(file_path)}: {token_count} tokens")
                        
                        # Emit result
                        self.file_tokenized.emit(file_path, token_count, is_valid, reason)
                        self.completed_count += 1
                        
                        # Emit progress
                        self.batch_completed.emit(self.completed_count, self.total_count)
                        
                        # Yield to main thread every few files to keep UI responsive
                        if self.completed_count % 3 == 0:
                            self.msleep(10)  # Sleep for 10ms to yield to main thread
                            QApplication.processEvents()  # Process Qt events
                        
                    except Exception as e:
                        print(f"[QT_TOKENIZER] ❌ Error tokenizing {file_path}: {e}")
                        self.file_tokenized.emit(file_path, 0, False, f"Error: {str(e)[:50]}")
                        self.completed_count += 1
                
                # Yield between batches
                self.msleep(20)  # Longer sleep between batches
                print(f"[QT_TOKENIZER] 📊 Batch {batch_count} completed. Progress: {self.completed_count}/{self.total_count}")
            
            print(f"[QT_TOKENIZER] 🎉 All files processed! Total: {self.completed_count}/{self.total_count}")
            self.progress_update.emit(f"Completed: {self.completed_count}/{self.total_count} files")
            
        except Exception as e:
            print(f"[QT_TOKENIZER] 💥 Critical error in worker thread: {e}")
            self.progress_update.emit(f"Error: {str(e)}")
    
    def _tokenize_single_file(self, file_path: str, calculate_tokens, MAX_FILE_SIZE_BYTES, SmartFileHandler) -> Tuple[str, int, bool, str]:
        """Tokenize a single file and return results."""
        try:
            if not os.path.exists(file_path):
                return file_path, 0, False, "File not found"
            
            file_size = os.path.getsize(file_path)
            strategy = SmartFileHandler.get_tokenization_strategy(file_path, file_size)
            
            if strategy == 'skip':
                _, reason = SmartFileHandler.get_file_display_info(file_path, file_size, strategy)
                return file_path, 0, True, reason  # Valid but skipped
            
            # Read and tokenize the file
            with open(file_path, 'rb') as f:
                raw_bytes = f.read(MAX_FILE_SIZE_BYTES + 1)
            
            content = raw_bytes[:MAX_FILE_SIZE_BYTES].decode('utf-8', errors='replace')
            token_count = calculate_tokens(content)
            
            return file_path, token_count, True, ""
            
        except Exception as e:
            return file_path, 0, False, f"Error: {str(e)[:50]}"
    
    def stop(self):
        """Request the worker thread to stop gracefully."""
        print(f"[QT_TOKENIZER] 🛑 Stop requested for worker thread")
        self.should_stop = True


class QtThreadTokenizer(QObject):
    """
    Qt-native tokenizer that uses QThread for robust, non-blocking tokenization.
    Fully compatible with Qt's event loop and lifecycle.
    """
    
    # Signals
    token_update = Signal(str, int)  # file_path, token_count
    file_validation_update = Signal(str, bool, str)  # file_path, is_valid, reason
    progress_update = Signal(int, int)  # current, total
    status_update = Signal(str)  # status message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker_thread = None
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setSingleShot(True)
        self._cleanup_timer.timeout.connect(self._cleanup_worker)
        
        print(f"[QT_TOKENIZER] 🏗️ QtThreadTokenizer created")
    
    def tokenize_files(self, file_paths: List[str], batch_size: int = 5):
        """Start tokenizing the given files using QThread."""
        if not file_paths:
            print(f"[QT_TOKENIZER] ⚠️ No files to tokenize")
            return
        
        # Clean up any existing worker
        self._cleanup_worker()
        
        print(f"[QT_TOKENIZER] 🚀 Starting tokenization of {len(file_paths)} files (batch size: {batch_size})")
        
        # Create and start worker thread
        self._worker_thread = TokenizerWorkerThread(file_paths, batch_size)
        
        # Connect signals
        self._worker_thread.file_tokenized.connect(self._on_file_tokenized)
        self._worker_thread.batch_completed.connect(self.progress_update)
        self._worker_thread.progress_update.connect(self.status_update)
        self._worker_thread.finished.connect(self._on_worker_finished)
        
        # Start the worker thread
        self._worker_thread.start()
        print(f"[QT_TOKENIZER] ✅ Worker thread started successfully")
    
    def _on_file_tokenized(self, file_path: str, token_count: int, is_valid: bool, reason: str):
        """Handle a single file being tokenized."""
        print(f"[QT_TOKENIZER] 📥 Received result: {os.path.basename(file_path)} -> {token_count} tokens")
        
        if is_valid and not reason:  # Normal tokenization
            self.token_update.emit(file_path, token_count)
        else:  # Validation issue or skipped file
            self.file_validation_update.emit(file_path, is_valid, reason)
            if is_valid and reason:  # Valid but skipped
                self.token_update.emit(file_path, 0)
    
    def _on_worker_finished(self):
        """Handle worker thread completion."""
        print(f"[QT_TOKENIZER] 🏁 Worker thread finished")
        self.status_update.emit("Tokenization completed")
        
        # Schedule cleanup after a short delay to ensure all signals are processed
        self._cleanup_timer.start(1000)  # 1 second delay
    
    def _cleanup_worker(self):
        """Safely clean up the worker thread."""
        if self._worker_thread and self._worker_thread.isRunning():
            print(f"[QT_TOKENIZER] 🧹 Cleaning up running worker thread...")
            self._worker_thread.stop()
            self._worker_thread.wait(3000)  # Wait up to 3 seconds
            if self._worker_thread.isRunning():
                print(f"[QT_TOKENIZER] ⚠️ Worker thread didn't stop gracefully, terminating...")
                self._worker_thread.terminate()
                self._worker_thread.wait(1000)
        
        if self._worker_thread:
            print(f"[QT_TOKENIZER] 🗑️ Deleting worker thread object")
            self._worker_thread.deleteLater()
            self._worker_thread = None
    
    def stop(self):
        """Stop the tokenization process gracefully."""
        print(f"[QT_TOKENIZER] 🛑 Stop requested")
        self._cleanup_timer.stop()
        self._cleanup_worker()
    
    def __del__(self):
        """Destructor - ensure clean shutdown."""
        try:
            print(f"[QT_TOKENIZER] 🔚 QtThreadTokenizer destructor called")
            self.stop()
        except:
            pass  # Ignore errors during destruction
