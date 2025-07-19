import tiktoken

def count_tokens(file_path):
    """Counts the number of tokens in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        # Using 'cl100k_base' for gpt-4, gpt-3.5-turbo, and text-embedding-ada-002
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except FileNotFoundError:
        return 0
    except Exception as e:
        print(f"Error counting tokens for {file_path}: {e}")
        return 0
