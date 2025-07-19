# --- File: isolated_background_scanner.py ---
"""
Completely isolated background scanner process that never interferes with the main window.
Runs in a separate process and only communicates essential updates when requested.
"""

import os
import time
import json
import multiprocessing as mp
from typing import List, Dict, Any, Optional
from pathlib import Path

# Windows multiprocessing protection
if __name__ == '__main__':
    mp.freeze_support()


def background_scanner_process(folder_path: str, settings: Dict, result_queue: mp.Queue, control_queue: mp.Queue):
    """
    Background scanner process that runs completely isolated from the main UI.
    
    Args:
        folder_path: Directory to scan
        settings: Scan settings
        result_queue: Queue to send results back to main process
        control_queue: Queue to receive control commands
    """
    print(f"[BG_SCANNER] 🚀 Background scanner process started for: {folder_path}")
    print(f"[BG_SCANNER] 📊 Process ID: {os.getpid()}")
    print(f"[BG_SCANNER] ⚙️ Settings: {settings}")
    
    try:
        # Import modules inside the process to avoid conflicts
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(__file__)))
        
        from core.helpers import calculate_tokens, MAX_FILE_SIZE_BYTES
        from core.smart_file_handler import SmartFileHandler
        
        # Scan directory structure first (fast)
        print(f"[BG_SCANNER] 📁 Starting directory structure scan...")
        structure_start = time.time()
        
        items = []
        file_paths_to_tokenize = []
        
        # Walk directory tree
        for root, dirs, files in os.walk(folder_path):
            # Filter ignored directories
            if settings.get('ignore_folders'):
                dirs[:] = [d for d in dirs if d not in settings['ignore_folders']]
            
            # Add directory items
            if root != folder_path:  # Skip root directory itself
                rel_path = os.path.relpath(root, folder_path)
                items.append((root, True, True, "", 0))  # (path, is_dir, is_valid, reason, token_count)
            
            # Add file items
            for file in files:
                file_path = os.path.join(root, file)
                
                try:
                    # Basic file validation
                    if not os.path.exists(file_path):
                        continue
                    
                    file_size = os.path.getsize(file_path)
                    
                    # Use smart file handler to determine strategy
                    strategy = SmartFileHandler.get_tokenization_strategy(file_path, file_size)
                    
                    if strategy == 'skip':
                        # File is skipped - add with 0 tokens and reason
                        _, reason = SmartFileHandler.get_file_display_info(file_path, file_size, strategy)
                        items.append((file_path, False, True, reason, 0))
                        print(f"[BG_SCANNER] ⏭️ Skipped {os.path.basename(file_path)}: {reason}")
                    else:
                        # File will be tokenized - add with -1 (loading) for now
                        items.append((file_path, False, True, "", -1))
                        file_paths_to_tokenize.append(file_path)
                        print(f"[BG_SCANNER] 📝 Queued for tokenization: {os.path.basename(file_path)} ({file_size//1024}KB)")
                
                except Exception as e:
                    print(f"[BG_SCANNER] ❌ Error processing {file_path}: {e}")
                    items.append((file_path, False, False, f"Error: {str(e)[:50]}", 0))
        
        structure_time = (time.time() - structure_start) * 1000
        print(f"[BG_SCANNER] ✅ Directory structure scan completed in {structure_time:.2f}ms")
        print(f"[BG_SCANNER] 📊 Found {len(items)} items, {len(file_paths_to_tokenize)} files to tokenize")
        
        # Send initial structure to main process (OPTIONAL - main process can ignore this)
        try:
            result_queue.put({
                'type': 'structure_complete',
                'items': items,
                'files_to_tokenize': len(file_paths_to_tokenize),
                'timestamp': time.time()
            }, timeout=1)  # Short timeout - if main process is busy, just continue
            print(f"[BG_SCANNER] 📤 Sent initial structure to main process")
        except:
            print(f"[BG_SCANNER] ⚠️ Main process busy - continuing without sending structure")
        
        # Start tokenization in background (completely independent)
        if file_paths_to_tokenize:
            print(f"[BG_SCANNER] 🧮 Starting background tokenization of {len(file_paths_to_tokenize)} files...")
            tokenization_start = time.time()
            
            completed_count = 0
            for file_path in file_paths_to_tokenize:
                # Check for stop command (non-blocking)
                try:
                    if not control_queue.empty():
                        command = control_queue.get_nowait()
                        if command == 'stop':
                            print(f"[BG_SCANNER] 🛑 Stop command received, terminating...")
                            break
                except:
                    pass  # No command, continue
                
                try:
                    # Detailed timing for each file
                    file_start = time.time()
                    file_name = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    print(f"[BG_SCANNER] 🔄 START: {file_name} ({file_size//1024}KB) - {completed_count+1}/{len(file_paths_to_tokenize)}")
                    
                    # Tokenize file
                    with open(file_path, 'rb') as f:
                        raw_bytes = f.read(MAX_FILE_SIZE_BYTES + 1)
                    
                    content = raw_bytes[:MAX_FILE_SIZE_BYTES].decode('utf-8', errors='replace')
                    token_count = calculate_tokens(content)
                    
                    # Update items list
                    for i, (path, is_dir, is_valid, reason, old_count) in enumerate(items):
                        if path == file_path and not is_dir:
                            items[i] = (path, is_dir, is_valid, reason, token_count)
                            break
                    
                    completed_count += 1
                    file_time = (time.time() - file_start) * 1000
                    print(f"[BG_SCANNER] ✅ END: {file_name}: {token_count} tokens in {file_time:.2f}ms ({completed_count}/{len(file_paths_to_tokenize)})")
                    
                    # Send periodic updates (OPTIONAL - main process can ignore)
                    if completed_count % 10 == 0:  # Every 10 files
                        try:
                            result_queue.put({
                                'type': 'progress_update',
                                'completed': completed_count,
                                'total': len(file_paths_to_tokenize),
                                'latest_file': file_path,
                                'latest_tokens': token_count,
                                'timestamp': time.time()
                            }, timeout=0.1)  # Very short timeout
                        except:
                            pass  # Main process busy, continue
                
                except Exception as e:
                    print(f"[BG_SCANNER] ❌ Error tokenizing {file_path}: {e}")
                    # Update with error
                    for i, (path, is_dir, is_valid, reason, old_count) in enumerate(items):
                        if path == file_path and not is_dir:
                            items[i] = (path, is_dir, False, f"Error: {str(e)[:50]}", 0)
                            break
                    completed_count += 1
            
            tokenization_time = (time.time() - tokenization_start) * 1000
            print(f"[BG_SCANNER] 🎉 Tokenization completed in {tokenization_time:.2f}ms")
        
        # Send final results (OPTIONAL)
        try:
            result_queue.put({
                'type': 'scan_complete',
                'items': items,
                'completed_files': completed_count,
                'total_files': len(file_paths_to_tokenize),
                'timestamp': time.time()
            }, timeout=1)
            print(f"[BG_SCANNER] 📤 Sent final results to main process")
        except:
            print(f"[BG_SCANNER] ⚠️ Main process busy - results available but not sent")
        
        print(f"[BG_SCANNER] ✅ Background scanner process completed successfully")
        
    except Exception as e:
        print(f"[BG_SCANNER] 💥 Critical error in background scanner: {e}")
        try:
            result_queue.put({
                'type': 'error',
                'error': str(e),
                'timestamp': time.time()
            }, timeout=1)
        except:
            pass

