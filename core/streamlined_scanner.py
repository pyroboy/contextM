"""
Streamlined scanner that uses ONLY the efficient background_scanner_process.
No threads, no complex initialization - just fast file listing and tokenization.
"""

import multiprocessing as mp
import time
import os
from typing import Dict, List, Tuple, Optional
from PySide6.QtCore import QObject, Signal, QTimer

from .bg_scanner import background_scanner_process


class StreamlinedScanner(QObject):
    """
    Ultra-fast scanner that uses only the efficient background_scanner_process.
    No complex initialization, no unnecessary threads - just get file list and tokens.
    """
    
    # Signals for UI updates
    scan_started = Signal()
    scan_progress = Signal(int, int)  # completed, total
    scan_complete = Signal(list)  # items list
    scan_error = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_process = None
        self.result_queue = None
        self.control_queue = None
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._check_results)
        self.update_timer.setSingleShot(False)
        self.scan_completed = False  # Flag to prevent processing after completion
        self.scan_start_time = None  # Track scan timing
        
    def start_scan(self, folder_path: str, settings: Dict) -> bool:
        """
        Start scanning using only the efficient background_scanner_process.
        Returns True if scan started successfully, False otherwise.
        """
        self.scan_start_time = time.time()
        print(f"[STREAMLINED] 🚀 Starting streamlined scan for: {folder_path} (T+0.00ms)")
        start_time = time.time()
        
        # Stop any existing scan
        self.stop_scan()
        stop_time = (time.time() - self.scan_start_time) * 1000
        print(f"[STREAMLINED] 🛑 Existing scan stopped (T+{stop_time:.2f}ms)")
        
        # Reset completion flag for new scan
        self.scan_completed = False
        
        try:
            # Create multiprocessing queues
            queue_time = (time.time() - self.scan_start_time) * 1000
            self.result_queue = mp.Queue()
            self.control_queue = mp.Queue()
            print(f"[STREAMLINED] 📋 Queues created (T+{queue_time:.2f}ms)")
            
            # Start the efficient background scanner process
            process_create_time = (time.time() - self.scan_start_time) * 1000
            self.current_process = mp.Process(
                target=background_scanner_process,
                args=(folder_path, settings, self.result_queue, self.control_queue)
            )
            print(f"[STREAMLINED] 🏠 Process created (T+{process_create_time:.2f}ms)")
            
            self.current_process.start()
            process_start_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] ✅ Background process started (PID: {self.current_process.pid}) (T+{process_start_time:.2f}ms)")
            
            # Start checking for results
            timer_start_time = (time.time() - self.scan_start_time) * 1000
            self.update_timer.start(100)  # Check every 100ms for fast updates
            print(f"[STREAMLINED] ⏱️ Timer started (T+{timer_start_time:.2f}ms)")
            
            # Emit scan started signal
            signal_time = (time.time() - self.scan_start_time) * 1000
            self.scan_started.emit()
            print(f"[STREAMLINED] 📡 Scan started signal emitted (T+{signal_time:.2f}ms)")
            
            setup_time = (time.time() - start_time) * 1000
            total_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] ⚡ Scan setup completed in {setup_time:.2f}ms (Total: T+{total_time:.2f}ms)")
            return True
            
        except Exception as e:
            print(f"[STREAMLINED] ❌ Failed to start scan: {e}")
            self.scan_error.emit(str(e))
            return False
    
    def stop_scan(self):
        """Stop any running scan."""
        if self.current_process and self.current_process.is_alive():
            print(f"[STREAMLINED] 🛑 Stopping scan process...")
            
            # Send stop command
            if self.control_queue:
                try:
                    self.control_queue.put('stop', timeout=0.1)
                except:
                    pass
            
            # Terminate process if needed
            self.current_process.terminate()
            self.current_process.join(timeout=1.0)
            
            if self.current_process.is_alive():
                print(f"[STREAMLINED] ⚠️ Force killing process...")
                self.current_process.kill()
                self.current_process.join()
            
            print(f"[STREAMLINED] ✅ Process stopped")
        
        # Stop timer
        if self.update_timer.isActive():
            self.update_timer.stop()
        
        # Clean up
        self.current_process = None
        self.result_queue = None
        self.control_queue = None
    
    def _check_results(self):
        """Check for results from background process."""
        if not self.result_queue or self.scan_completed:
            return
        
        # Process only essential results - skip progress updates if scan is nearly done
        results_processed = 0
        
        while results_processed < 50:  # Moderate limit for efficiency
            try:
                result = self.result_queue.get_nowait()
                result_type = result.get('type', 'unknown')
                
                # Only process scan_complete and structure_complete - skip progress updates
                if result_type in ['scan_complete', 'structure_complete']:
                    self._process_result(result)
                elif result_type == 'progress_update' and not self.scan_completed:
                    # Only process progress if scan not completed yet
                    self._process_result(result)
                
                results_processed += 1
                
                # If scan completed, stop immediately without draining
                if self.scan_completed:
                    print(f"[STREAMLINED] ⚡ Scan completed - stopping immediately")
                    return
                    
            except:
                break  # No more results
        
        # Check if process is still alive (backup check)
        if self.current_process and not self.current_process.is_alive():
            if not self.scan_completed:  # Only print if we haven't already stopped
                print(f"[STREAMLINED] 🏁 Background process completed")
                self.update_timer.stop()
    
    def _process_result(self, result: Dict):
        """Process a single result from the background scanner."""
        result_type = result.get('type', 'unknown')
        
        if result_type == 'structure_complete':
            # Structure scan complete - show file tree immediately
            items = result.get('items', [])
            files_to_tokenize = result.get('files_to_tokenize', 0)
            structure_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] 📁 Structure ready: {len(items)} items, {files_to_tokenize} files to tokenize (T+{structure_time:.2f}ms)")
            
        elif result_type == 'progress_update':
            # Progress update
            start_time = time.time()
            completed = result.get('completed', 0)
            total = result.get('total', 0)
            progress_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] 📈 Progress: {completed}/{total} (T+{progress_time:.2f}ms)")
            self.scan_progress.emit(completed, total)
            end_time = time.time()
            print(f"[STREAMLINED] ⏱️ Progress update processed in {(end_time - start_time) * 1000:.2f}ms")
            
        elif result_type == 'scan_complete':
            # Final results - this is what we want!
            items = result.get('items', [])
            completed_files = result.get('completed_files', 0)
            total_files = result.get('total_files', 0)
            
            scan_complete_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] 🎉 Scan complete: {len(items)} items, {completed_files}/{total_files} files tokenized (T+{scan_complete_time:.2f}ms)")
            
            # Set completion flag to stop further processing
            self.scan_completed = True
            flag_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] 🏴 Completion flag set (T+{flag_time:.2f}ms)")
            
            # IMMEDIATELY stop timer to prevent further queue processing
            timer_stop_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] 🛑 STOPPING TIMER - No more queue processing (T+{timer_stop_time:.2f}ms)")
            self.update_timer.stop()
            
            # Emit final results in batches to prevent Qt signal lag
            emit_start_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] 📡 Emitting {len(items)} items in batches to prevent lag (T+{emit_start_time:.2f}ms)")
            
            # Emit immediately without batching for now - the issue is in the UI processing
            self.scan_complete.emit(items)
            
            final_time = (time.time() - self.scan_start_time) * 1000
            print(f"[STREAMLINED] ✅ Final results emission completed (T+{final_time:.2f}ms)")
            
        elif result_type == 'error':
            # Error occurred
            error = result.get('error', 'Unknown error')
            print(f"[STREAMLINED] ❌ Scan error: {error}")
            self.scan_error.emit(error)
            self.update_timer.stop()
    
    def cleanup(self):
        """Clean up resources."""
        self.stop_scan()
