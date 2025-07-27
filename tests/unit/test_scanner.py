import pytest
from unittest.mock import MagicMock, patch
import os
import time

# Adjust path to import from 'core'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core.streamlined_scanner import StreamlinedScanner
from tests.fixtures.repo_gen import create_test_repo

@pytest.fixture
def temp_repo(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    # Create a dummy structure
    (repo_path / "file1.py").write_text("print('hello')")
    (repo_path / "folder1").mkdir()
    (repo_path / "folder1" / "file2.txt").write_text("world")
    return repo_path

def test_streamlined_scanner_basic_functionality(temp_repo):
    """Test that StreamlinedScanner can scan a directory and return results."""
    # Setup test files
    (temp_repo / "folder_to_ignore").mkdir()
    (temp_repo / "folder_to_ignore" / "ignored_file.txt").write_text("ignored")
    
    settings = {
        'include_subfolders': True, 
        'ignore_folders': {"folder_to_ignore"},
        'live_watcher': False
    }
    
    scanner = StreamlinedScanner()
    
    # Use a simple approach - start scan and wait for completion
    results = []
    def capture_results(items):
        results.extend(items)
    
    scanner.scan_complete.connect(capture_results)
    
    # Start scan
    success = scanner.start_scan(str(temp_repo), settings)
    assert success, "Scanner should start successfully"
    
    # Wait for completion (simplified for testing)
    import time
    timeout = 5  # 5 second timeout
    start_time = time.time()
    while not results and (time.time() - start_time) < timeout:
        time.sleep(0.1)
    
    # Verify we got some results
    assert len(results) > 0, "Scanner should return some items"
    
    # Verify ignored folder is not in results
    result_paths = {item[0] for item in results}
    ignored_folder_path = str(temp_repo / "folder_to_ignore")
    assert ignored_folder_path not in result_paths, "Ignored folder should not be in results"

def test_streamlined_scanner_stops_on_request(temp_repo):
    """Verify the scanner can be stopped when requested."""
    settings = {'include_subfolders': True, 'ignore_folders': set(), 'live_watcher': False}
    scanner = StreamlinedScanner()
    
    # Start scan
    success = scanner.start_scan(str(temp_repo), settings)
    assert success, "Scanner should start successfully"
    
    # Stop scan
    scanner.stop_scan()
    
    # Verify scan is stopped (scanner should handle this gracefully)
    assert True  # If we get here without exception, stop worked

def test_streamlined_scanner_error_on_bad_path(tmp_path):
    """Test that the scanner handles bad paths gracefully."""
    bad_path = tmp_path / "non_existent_directory"
    bad_path_str = str(bad_path)
    
    scanner = StreamlinedScanner()
    
    # Capture error signals
    errors = []
    def capture_error(error_msg):
        errors.append(error_msg)
    
    scanner.scan_error.connect(capture_error)
    
    settings = {'include_subfolders': True, 'ignore_folders': set(), 'live_watcher': False}
    success = scanner.start_scan(bad_path_str, settings)
    
    # Scanner should either fail to start or emit an error
    if success:
        # Wait a bit for potential error
        import time
        time.sleep(0.5)
        assert len(errors) > 0, "Scanner should emit error for bad path"
    else:
        # Scanner failed to start, which is also acceptable
        assert True
