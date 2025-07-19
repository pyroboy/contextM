# --- File: worker_process_tokenizer.py ---
"""
Worker process-based tokenizer for true parallel processing without blocking the main UI.
Uses multiprocessing instead of threading for better performance on large repositories.
"""

import os
import multiprocessing as mp
from typing import List, Tuple
from PySide6.QtCore import QObject, Signal, QTimer
import time

def tokenize_file_worker(file_path: str) -> Tuple[str, int, bool, str]:
    """
    Worker function that runs in a separate process to tokenize a single file.
    Returns (file_path, token_count, is_valid, reason)
    """
    try:
        # Import inside worker to avoid issues with multiprocessing
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        
        from core.helpers import calculate_tokens, MAX_FILE_SIZE_BYTES
        from core.smart_file_handler import SmartFileHandler
        
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


class WorkerProcessTokenizer(QObject):
    """
    Process-based tokenizer that uses multiple worker processes for true parallelism.
    This prevents any blocking of the main UI thread.
    """
    
    # Signals
    file_tokenized = Signal(str, int, bool, str)  # file_path, token_count, is_valid, reason
    batch_completed = Signal(int, int)  # completed_count, total_count
    all_completed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = None
        self._pending_results = []
        self._completed_count = 0
        self._total_count = 0
        self._check_timer = QTimer()
        self._check_timer.timeout.connect(self._check_results)
        
    def start_tokenization(self, file_paths: List[str], max_workers: int = None):
        """
        Start tokenizing files using worker processes.
        
        Args:
            file_paths: List of file paths to tokenize
            max_workers: Maximum number of worker processes (default: CPU count)
        """
        if not file_paths:
            self.all_completed.emit()
            return
            
        self._total_count = len(file_paths)
        self._completed_count = 0
        
        # Determine optimal number of workers
        if max_workers is None:
            max_workers = min(mp.cpu_count(), len(file_paths), 4)  # Cap at 4 to avoid overwhelming
            
        print(f"[WORKER_PROCESS] Starting tokenization of {len(file_paths)} files using {max_workers} worker processes")
        
        # Create process pool
        self._pool = mp.Pool(processes=max_workers)
        
        # Submit all files for processing
        start_time = time.time()
        self._pending_results = []
        
        for file_path in file_paths:
            result = self._pool.apply_async(tokenize_file_worker, (file_path,))
            self._pending_results.append(result)
        
        submit_time = (time.time() - start_time) * 1000
        print(f"[WORKER_PROCESS] Submitted {len(file_paths)} files to worker pool in {submit_time:.2f}ms")
        
        # Start checking for completed results
        self._check_timer.start(50)  # Check every 50ms
        
    def _check_results(self):
        """Check for completed tokenization results."""
        if not self._pending_results:
            print(f"[WORKER_PROCESS] ⚠️ _check_results called but no pending results")
            return
            
        print(f"[WORKER_PROCESS] 🔍 Checking {len(self._pending_results)} pending results...")
        
        # Check for completed results
        completed_results = []
        remaining_results = []
        
        for result in self._pending_results:
            if result.ready():
                completed_results.append(result)
                print(f"[WORKER_PROCESS] ✅ Found completed result")
            else:
                remaining_results.append(result)
        
        print(f"[WORKER_PROCESS] 📊 {len(completed_results)} completed, {len(remaining_results)} remaining")
        
        # Process completed results
        for result in completed_results:
            try:
                file_path, token_count, is_valid, reason = result.get()
                print(f"[WORKER_PROCESS] 📤 Emitting result: {file_path} -> {token_count} tokens")
                self.file_tokenized.emit(file_path, token_count, is_valid, reason)
                self._completed_count += 1
                print(f"[WORKER_PROCESS] ✅ Signal emitted successfully")
            except Exception as e:
                print(f"[WORKER_PROCESS] ❌ Error processing result: {e}")
                self._completed_count += 1
        
        # Update pending results
        self._pending_results = remaining_results
        
        # Emit progress update
        if completed_results:
            self.batch_completed.emit(self._completed_count, self._total_count)
            print(f"[WORKER_PROCESS] Progress: {self._completed_count}/{self._total_count} files completed")
        
        # Check if all done
        if not self._pending_results:
            self._check_timer.stop()
            self._cleanup_pool()
            print(f"[WORKER_PROCESS] ✅ All {self._total_count} files tokenized!")
            self.all_completed.emit()
    
    def _cleanup_pool(self):
        """Clean up the process pool."""
        if self._pool:
            self._pool.close()
            self._pool.join()
            self._pool = None
    
    def stop_tokenization(self):
        """Stop the tokenization process."""
        if self._check_timer.isActive():
            self._check_timer.stop()
        
        if self._pool:
            print(f"[WORKER_PROCESS] Stopping tokenization...")
            self._pool.terminate()
            self._pool.join()
            self._pool = None
        
        self._pending_results.clear()
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        self.stop_tokenization()


class NonBlockingTokenizer(QObject):
    """
    Non-blocking tokenizer that uses worker processes for tokenization.
    Integrates with the existing optimistic loading system.
    """
    
    # Signals
    token_update = Signal(str, int)  # file_path, token_count
    file_validation_update = Signal(str, bool, str)  # file_path, is_valid, reason
    progress_update = Signal(int, int)  # current, total
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = WorkerProcessTokenizer(self)
        
        # Connect worker signals
        self._worker.file_tokenized.connect(self._on_file_tokenized)
        self._worker.batch_completed.connect(self.progress_update)
        self._worker.all_completed.connect(self._on_all_completed)
    
    def tokenize_files(self, file_paths: List[str]):
        """Start tokenizing the given files."""
        if not file_paths:
            return
            
        print(f"[NON_BLOCKING] Starting non-blocking tokenization of {len(file_paths)} files")
        self._worker.start_tokenization(file_paths)
    
    def _on_file_tokenized(self, file_path: str, token_count: int, is_valid: bool, reason: str):
        """Handle a single file being tokenized."""
        if is_valid and not reason:  # Normal tokenization
            self.token_update.emit(file_path, token_count)
        else:  # Validation issue or skipped file
            self.file_validation_update.emit(file_path, is_valid, reason)
            if is_valid and reason:  # Valid but skipped
                self.token_update.emit(file_path, 0)
    
    def _on_all_completed(self):
        """Handle completion of all tokenization."""
        print(f"[NON_BLOCKING] ✅ All files tokenized!")
    
    def stop(self):
        """Stop the tokenization process."""
        self._worker.stop_tokenization()
