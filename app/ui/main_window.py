"""Main application window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QVBoxLayout, QWidget

from app import __version__


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MANGO Downloader")
        self.setMinimumSize(600, 360)

        title = QLabel("MANGO Downloader")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 600;")
        message = QLabel(
            "Приложение готово к настройке подключения к MANGO OFFICE.\n\n"
            "Подключение к MANGO будет добавлено на следующем этапе."
        )
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        version = QLabel(f"Версия {__version__}")
        version.setAlignment(Qt.AlignmentFlag.AlignRight)

        layout = QVBoxLayout()
        layout.setContentsMargins(36, 36, 36, 20)
        layout.addStretch()
        layout.addWidget(title)
        layout.addSpacing(20)
        layout.addWidget(message)
        layout.addStretch()
        layout.addWidget(version)
        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
