import sys
from PyQt6.QtWidgets import QApplication
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)

    # Set application-wide stylesheet
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f3f4f6;
        }
    """)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()