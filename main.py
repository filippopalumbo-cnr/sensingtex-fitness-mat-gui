# main.py
"""Main entry point for the Fitness Mat application."""

import sys
from PyQt5.QtWidgets import QApplication

# Import the main window class from its file
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())