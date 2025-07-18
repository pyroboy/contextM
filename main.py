# --- File: main.py (Bootstrap) ---
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Import the new main window
from ui.main_window import MainWindow

def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    
    # For high-resolution displays
    app.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling)

    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == '__main__':
    main()