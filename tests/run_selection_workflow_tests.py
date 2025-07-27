#!/usr/bin/env python3
"""
Test runner for selection workflow integration tests.

This script runs all the tests that verify the complete selection workflow:
- Checking/unchecking files updates the selection manager's dirty state
- Switching between selection groups properly saves and restores selections
- Parent folder checkbox states are correctly calculated
- The cache remains synchronized during all operations
- Selection persistence works across application restarts
"""

import sys
import os
import subprocess
from pathlib import Path

def main():
    """Run the selection workflow integration tests."""
    # Get the project root directory
    project_root = Path(__file__).parent.parent
    
    # Add the project root to Python path
    sys.path.insert(0, str(project_root))
    
    # Change to project root directory
    os.chdir(project_root)
    
    print("Running Selection Workflow Integration Tests")
    print("=" * 50)
    
    # List of test files to run
    test_files = [
        "tests/test_selection_workflow_integration.py",
        "tests/test_selection_manager_panel.py",
        "tests/test_selection_manager.py",
        "tests/unit/test_tree_panel.py"
    ]
    
    # Check which test files exist
    existing_tests = []
    for test_file in test_files:
        if Path(test_file).exists():
            existing_tests.append(test_file)
            print(f"✓ Found: {test_file}")
        else:
            print(f"✗ Missing: {test_file}")
    
    if not existing_tests:
        print("\nNo test files found!")
        return 1
    
    print(f"\nRunning {len(existing_tests)} test files...")
    print("-" * 30)
    
    # Run pytest with the existing test files
    try:
        # Run with verbose output and show local variables on failure
        cmd = [
            sys.executable, "-m", "pytest", 
            "-v",  # verbose
            "-s",  # don't capture output
            "--tb=short",  # shorter traceback format
            "--color=yes",  # colored output
        ] + existing_tests
        
        print(f"Command: {' '.join(cmd)}")
        print()
        
        result = subprocess.run(cmd, cwd=project_root)
        return result.returncode
        
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
