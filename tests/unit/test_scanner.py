import pytest
from unittest.mock import MagicMock, patch
import os
import time

# Adjust path to import from 'core'
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core.directory_scanner import DirectoryScannerThread
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

def test_scanner_emits_correct_batch_format(temp_repo):
    """Verify the scanner emits a list of absolute file paths."""
    scanner = DirectoryScannerThread(str(temp_repo), MagicMock())
    
    with patch.object(scanner.signals.batch_processed, 'emit') as mock_emit:
        scanner.run()
        time.sleep(0.1) # Allow thread to run
        
        assert mock_emit.called
        call_args = mock_emit.call_args[0][0]
        assert isinstance(call_args, list)
        assert len(call_args) == 2
        assert all(os.path.isabs(p) for p in call_args)
        assert str(temp_repo / "file1.py") in call_args

def test_scanner_stops_on_request(temp_repo):
    """Verify the scanner thread terminates when stop() is called."""
    scanner = DirectoryScannerThread(str(temp_repo), MagicMock())
    scanner.start()
    assert scanner.isRunning()
    
    scanner.stop()
    scanner.wait(1000) # Wait for thread to finish
    
    assert not scanner.isRunning()

def test_scanner_error_on_unreadable_root():
    """Test that the 'error_occurred' signal is emitted for a bad path."""
    bad_path = "/path/to/non_existent_directory"
    scanner = DirectoryScannerThread(bad_path, MagicMock())
    
    with patch.object(scanner.signals.error_occurred, 'emit') as mock_emit:
        scanner.run()
        mock_emit.assert_called_once_with(f"Root directory '{bad_path}' not found or is not a directory.")
