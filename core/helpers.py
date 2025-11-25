# --- File: helpers.py ---
# --- Configuration used by the scanner (also patchable in tests) ---
MAX_FILE_SIZE_KB = 200
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_KB * 1024
SCAN_BATCH_SIZE = 100
import os
import pathlib
import traceback

# --- magic import ---
# HACK: Temporarily disable python-magic to avoid libmagic dependency issues
MAGIC_AVAILABLE = False
# try:
#     import magic
#     MAGIC_AVAILABLE = True
# except ImportError:
#     MAGIC_AVAILABLE = False
#     print("Warning: python-magic library not found or libmagic is missing.")
#     print("Install it ('pip install python-magic' or 'pip install python-magic-bin')")
#     print("and ensure libmagic C library is installed on your system.")
#     print("Falling back to content-based text file detection.")

# --- tiktoken import ---
_tokenizer = None

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False
    print("Warning: tiktoken library not found. Token counts will not be available.")
    print("Install it using: pip install tiktoken")

def get_tokenizer():
    """Returns a singleton tokenizer instance."""
    global _tokenizer
    if TIKTOKEN_AVAILABLE and _tokenizer is None:
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    return _tokenizer


BINARY_CHECK_CHUNK_SIZE = 1024 # For is_text_file fallback check
TOKEN_ENCODING_NAME = "cl100k_base"

# --- Helper Functions ---

def is_text_file(file_path):
    """
    Checks if a file is likely text-based using python-magic (if available)
    or by inspecting the initial bytes as a fallback.
    """
    if MAGIC_AVAILABLE:
        try:
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(file_path)
            # Common text types + JSON/XML often treated as text
            if mime_type.startswith("text/") or mime_type in [
                "application/json", "application/xml", "application/javascript",
                "application/x-sh", "application/x-shellscript", "inode/x-empty" # Empty files are ok
            ]:
                return True
            # If magic identifies it as clearly binary, return False early
            if "binary" in mime_type or "octet-stream" in mime_type or "application/" not in mime_type:
                 if not mime_type.startswith("application/"): # Broad catch-all
                    return False
        except magic.MagicException as e:
            print(f"Warning: python-magic failed for {file_path}: {e}. Falling back.")
        except Exception as e: # Catch other potential magic errors
            print(f"Warning: Unexpected error using python-magic for {file_path}: {e}. Falling back.")
            # Fall through to content check

    # Fallback: check content manually if magic unavailable or failed/inconclusive
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(BINARY_CHECK_CHUNK_SIZE)
            if not chunk: # Empty file is considered text
                return True
            # Check for null bytes - strong indicator of binary
            if b'\0' in chunk:
                return False
            # Try decoding as UTF-8 (most common text encoding)
            try:
                chunk.decode('utf-8')
                return True
            except UnicodeDecodeError:
                # If UTF-8 fails, it *might* still be text in another encoding
                # but for aggregating code, lack of UTF-8 is a reasonable filter.
                return False
    except IOError: # Handle file not found or permission errors during fallback read
        return False
    except Exception as e:
        print(f"Unexpected error during fallback text check for {file_path}: {e}")
        return False


def calculate_tokens(text: str, encoding_name: str = TOKEN_ENCODING_NAME) -> int:
    """Calculates the number of tokens in a string using tiktoken."""
    if not TIKTOKEN_AVAILABLE or not text: return 0
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        tokens = encoding.encode(text, disallowed_special=()) # Allow special tokens for more accurate count
        return len(tokens)
    except Exception as e:
        print(f"Warning: Could not calculate tokens using '{encoding_name}': {e}")
        return 0


def count_tokens_in_file(file_path: str) -> int:
    """Open a file and return its token count using calculate_tokens.

    Uses UTF-8 with replacement for decoding errors and returns 0 on any
    exception to provide a safe, centralized file token counting helper.
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        return calculate_tokens(content)
    except Exception as e:
        print(f"Warning: Error counting tokens for '{file_path}': {e}")
        return 0