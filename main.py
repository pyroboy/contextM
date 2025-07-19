# --- File: main.py (Bootstrap) ---
import sys
import multiprocessing as mp
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Import the new main window
from ui.main_window import MainWindow

def main():
    """Application entry point."""
    print("[MAIN] 🚀 Starting application...")
    app = QApplication(sys.argv)
    print("[MAIN] ✅ QApplication created")
    
    # For high-resolution displays
    app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)
    print("[MAIN] ✅ High DPI scaling set")

    print("[MAIN] 🏗️ Creating MainWindow...")
    try:
        window = MainWindow()
        print("[MAIN] ✅ MainWindow created")
        
        print("[MAIN] 👁️ Showing window...")
        window.show()
        print("[MAIN] ✅ Window.show() called")
    except Exception as e:
        print(f"[MAIN] ❌ ERROR creating MainWindow: {e}")
        print(f"[MAIN] ❌ Error type: {type(e).__name__}")
        import traceback
        print(f"[MAIN] ❌ Traceback:")
        traceback.print_exc()
        return
    
    print("[MAIN] 🔄 Starting event loop...")
    sys.exit(app.exec())

if __name__ == '__main__':
    # Windows multiprocessing support
    mp.freeze_support()
    main()