# --- File: smart_file_handler.py ---
"""
Smart file handling for performance optimization.
Handles large files, known problematic files, and implements intelligent tokenization strategies.
"""

import os
import pathlib
from typing import Tuple, Set

# File patterns that should be skipped for tokenization (known to be large/unnecessary)
SKIP_TOKENIZATION_PATTERNS = {
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    'Gemfile.lock',
    'Pipfile.lock',
    'poetry.lock',
    'composer.lock',
    'go.sum',
    'Cargo.lock',
    '*.min.js',
    '*.min.css',
    '*.bundle.js',
    '*.bundle.css',
    '*.map',
    '*.woff',
    '*.woff2',
    '*.ttf',
    '*.eot',
    '*.ico',
    '*.png',
    '*.jpg',
    '*.jpeg',
    '*.gif',
    '*.bmp',
    '*.tiff',
    '*.webp',
    '*.svg',
    '*.pdf',
    '*.zip',
    '*.tar',
    '*.gz',
    '*.rar',
    '*.7z',
    '*.exe',
    '*.dll',
    '*.so',
    '*.dylib',
    # Additional files to skip for UI responsiveness
    '*.log',
    '*.tmp',
    '*.cache',
    '*.bak',
    '*.backup',
    '*.old',
    '*.orig',
    '*.swp',
    '*.swo',
    '*.DS_Store',
    'Thumbs.db',
    '*.sqlite',
    '*.db',
    '*.csv',  # Large CSV files can be problematic
    '*.xml',  # Large XML files
    '*.json'  # Large JSON files (like package-lock.json)
}

# File size thresholds (in bytes) - AGGRESSIVE for UI responsiveness
IMMEDIATE_TOKENIZATION_THRESHOLD = 20 * 1024  # 20KB - tokenize immediately (small files only)
DEFER_TOKENIZATION_THRESHOLD = 50 * 1024      # 50KB - defer to background
SKIP_TOKENIZATION_THRESHOLD = 50 * 1024       # 50KB - skip entirely (USER REQUEST)

class SmartFileHandler:
    """Handles intelligent file processing decisions for performance optimization."""
    
    @staticmethod
    def should_skip_tokenization(file_path: str, file_size: int) -> Tuple[bool, str]:
        """
        Determine if a file should skip tokenization entirely.
        Returns (should_skip, reason)
        """
        file_name = os.path.basename(file_path).lower()
        file_ext = pathlib.Path(file_path).suffix.lower()
        
        # Check file size threshold
        if file_size > SKIP_TOKENIZATION_THRESHOLD:
            return True, f"File too large ({file_size // 1024}KB)"
        
        # Check known problematic file patterns
        for pattern in SKIP_TOKENIZATION_PATTERNS:
            if pattern.startswith('*'):
                # Handle wildcard patterns
                if file_name.endswith(pattern[1:]) or file_ext == pattern[1:]:
                    return True, f"Skipped {pattern} file"
            else:
                # Handle exact filename matches
                if file_name == pattern:
                    return True, f"Skipped {pattern}"
        
        return False, ""
    
    @staticmethod
    def get_tokenization_strategy(file_path: str, file_size: int) -> str:
        """
        Determine the tokenization strategy for a file.
        Returns: 'immediate', 'defer', or 'skip'
        """
        should_skip, _ = SmartFileHandler.should_skip_tokenization(file_path, file_size)
        
        if should_skip:
            return 'skip'
        elif file_size <= IMMEDIATE_TOKENIZATION_THRESHOLD:
            return 'immediate'
        elif file_size <= DEFER_TOKENIZATION_THRESHOLD:
            return 'defer'
        else:
            return 'skip'
    
    @staticmethod
    def get_file_display_info(file_path: str, file_size: int, strategy: str) -> Tuple[int, str]:
        """
        Get display information for a file based on its tokenization strategy.
        Returns (token_count, status_reason)
        """
        if strategy == 'skip':
            should_skip, reason = SmartFileHandler.should_skip_tokenization(file_path, file_size)
            return 0, reason or f"Large file ({file_size // 1024}KB)"
        elif strategy == 'defer':
            return -1, ""  # -1 indicates "loading..."
        else:  # immediate
            return -2, ""  # -2 indicates "calculate now"
    
    @staticmethod
    def is_likely_text_file(file_path: str) -> bool:
        """Quick check if a file is likely to be a text file worth tokenizing."""
        file_ext = pathlib.Path(file_path).suffix.lower()
        
        # Known text file extensions
        text_extensions = {
            '.txt', '.md', '.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.htm', 
            '.css', '.scss', '.sass', '.less', '.json', '.xml', '.yaml', '.yml',
            '.toml', '.ini', '.cfg', '.conf', '.sh', '.bash', '.zsh', '.fish',
            '.ps1', '.cmd', '.bat', '.sql', '.r', '.rb', '.php', '.java', '.c',
            '.cpp', '.cc', '.cxx', '.h', '.hpp', '.cs', '.go', '.rs', '.swift',
            '.kt', '.scala', '.clj', '.hs', '.elm', '.dart', '.vue', '.svelte',
            '.astro', '.dockerfile', '.gitignore', '.gitattributes', '.editorconfig',
            '.prettierrc', '.eslintrc', '.babelrc', '.env', '.log'
        }
        
        return file_ext in text_extensions or file_ext == ''  # Files without extension might be text
    
    @staticmethod
    def get_performance_stats() -> dict:
        """Get performance statistics for monitoring."""
        return {
            'immediate_threshold_kb': IMMEDIATE_TOKENIZATION_THRESHOLD // 1024,
            'defer_threshold_kb': DEFER_TOKENIZATION_THRESHOLD // 1024,
            'skip_threshold_kb': SKIP_TOKENIZATION_THRESHOLD // 1024,
            'skip_patterns_count': len(SKIP_TOKENIZATION_PATTERNS)
        }
