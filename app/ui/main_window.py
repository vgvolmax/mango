"""Responsive Qt user interface for calls and downloads."""

from datetime import datetime, time
from dataclasses import dataclass
import logging
from pathlib import Path
import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, Slot
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDateEdit, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QProgressBar, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app import __version__
from app.core.credentials import CredentialsStore
from app.core.paths import AppPaths
from app.core.settings import SettingsStore
from app.mango.client import MangoClient
from app.services.calls import CallService
from app.services.downloads import DownloadHistory, DownloadService, format_duration

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerError:
    exception: Exception
    traceback: str


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(object)
    progress = Signal(int, int)


class Worker(QRunnable):
    def __init__(self, function, *args, progress=False):
        super().__init__(); self.function, self.args, self.signals = function, args, WorkerSignals(); self.with_progress = progress

    @Slot()
    def run(self):
        try:
            kwargs = {"progress": self.signals.progress.emit} if self.with_progress else {}
            self.signals.result.emit(self.function(*self.args, **kwargs))
        except Exception as exc:
            self.signals.error.emit(WorkerError(exc, traceback.format_exc()))


class MainWindow(QMainWindow):
    def __init__(self, paths=None, settings=None, credentials=None) -> None:
        super().__init__()
        self.paths = paths or AppPaths.discover(); self.paths.ensure_directories()
        self.settings_store = settings or SettingsStore(self.paths.settings_file)
        self.credentials = credentials or CredentialsStore(self.paths.credentials_file)
        self.settings = self.settings_store.load(); self.calls = []
        self.pool = QThreadPool.globalInstance(); self._workers = set()
        self.setWindowTitle(f"MANGO Downloader {__version__}"); self.resize(980, 680)
        self._build_ui(); self._load_values()

    def _build_ui(self):
        root = QVBoxLayout(); connection = QGroupBox("Подключение к MANGO"); form = QFormLayout(connection)
        self.api_key = QLineEdit(); self.api_salt = QLineEdit(); self.api_salt.setEchoMode(QLineEdit.EchoMode.Password)
        self.remember = QCheckBox("Запомнить ключи на этом компьютере"); self.remember.setChecked(True)
        self.check_button = QPushButton("Проверить подключение"); self.connection_status = QLabel()
        row = QHBoxLayout(); row.addWidget(self.check_button); row.addWidget(self.connection_status); row.addStretch()
        form.addRow("API Key", self.api_key); form.addRow("API Salt", self.api_salt); form.addRow(self.remember); form.addRow(row); root.addWidget(connection)
        period = QGroupBox("Период"); prow = QHBoxLayout(period); self.from_date = QDateEdit(); self.to_date = QDateEdit()
        for widget in (self.from_date, self.to_date): widget.setCalendarPopup(True); widget.setDisplayFormat("dd.MM.yyyy"); widget.setDate(widget.date().currentDate())
        self.find_button = QPushButton("Найти звонки"); prow.addWidget(QLabel("С:")); prow.addWidget(self.from_date); prow.addWidget(QLabel("По:")); prow.addWidget(self.to_date); prow.addStretch(); prow.addWidget(self.find_button); root.addWidget(period)
        self.table = QTableWidget(0, 7); self.table.setHorizontalHeaderLabels(["Выбор", "Дата и время", "Тип", "Сотрудник", "Номер", "Разговор", "Записи"]); self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection); self.table.horizontalHeader().setStretchLastSection(True); root.addWidget(self.table)
        self.select_all = QPushButton("Выбрать все"); root.addWidget(self.select_all)
        folder = QHBoxLayout(); folder.addWidget(QLabel("Сохранить в:")); self.directory = QLineEdit(); self.browse = QPushButton("Обзор..."); folder.addWidget(self.directory); folder.addWidget(self.browse); root.addLayout(folder)
        bottom = QHBoxLayout(); self.progress = QProgressBar(); self.progress.hide(); self.download_button = QPushButton("Скачать выбранные"); bottom.addWidget(self.progress); bottom.addWidget(self.download_button); root.addLayout(bottom)
        version = QLabel(f"Версия {__version__}"); version.setAlignment(Qt.AlignmentFlag.AlignRight); root.addWidget(version)
        container = QWidget(); container.setLayout(root); self.setCentralWidget(container)
        self.check_button.clicked.connect(self._check); self.find_button.clicked.connect(self._find); self.select_all.clicked.connect(self._select_all); self.browse.clicked.connect(self._browse); self.download_button.clicked.connect(self._download)

    def _load_values(self):
        saved = self.credentials.load()
        if saved: self.api_key.setText(saved[0]); self.api_salt.setText(saved[1])
        self.directory.setText(self.settings.get("download_directory") or str(self.paths.downloads_dir))

    def _client(self):
        return MangoClient(self.api_key.text().strip(), self.api_salt.text())

    def _save_credentials(self):
        if self.remember.isChecked(): self.credentials.save(self.api_key.text().strip(), self.api_salt.text())
        else: self.credentials.delete()

    def _run(self, function, success, failure, *args, progress=False):
        worker = Worker(function, *args, progress=progress); self._workers.add(worker)
        worker.signals.result.connect(success); worker.signals.error.connect(failure)
        worker.signals.result.connect(lambda _: self._workers.discard(worker)); worker.signals.error.connect(lambda _: self._workers.discard(worker))
        if progress: worker.signals.progress.connect(self._progress)
        self.pool.start(worker)

    def _check(self):
        self.check_button.setEnabled(False); self.connection_status.setText("Проверяем...")
        self._run(self._client().check_credentials, self._check_ok, self._check_error)

    def _check_ok(self, _):
        self.check_button.setEnabled(True); self.connection_status.setText("✓ Подключение установлено")
        try: self._save_credentials()
        except OSError: QMessageBox.warning(self, "MANGO Downloader", "Не удалось безопасно сохранить ключи.")

    def _check_error(self, error):
        logger.error("Connection check failed: %s\n%s", error.exception, error.traceback)
        self.check_button.setEnabled(True); self.connection_status.clear(); QMessageBox.warning(self, "MANGO Downloader", "Не удалось подключиться к MANGO.\n\nПроверьте API Key и API Salt.")

    def _find(self):
        start, end = self.from_date.date().toPython(), self.to_date.date().toPython()
        if start > end or (end - start).days >= 31:
            QMessageBox.warning(self, "MANGO Downloader", "Выбран слишком большой или некорректный период.\n\nЗа один запрос можно получить звонки максимум за один месяц."); return
        self.find_button.setEnabled(False); self.find_button.setText("Получаем звонки...")
        service = CallService(self._client()); self._run(service.get_calls, self._calls_ok, self._calls_error, datetime.combine(start, time.min), datetime.combine(end, time.max.replace(microsecond=0)))

    def _calls_ok(self, calls):
        self.find_button.setEnabled(True); self.find_button.setText("Найти звонки"); self.calls = calls; self.table.setRowCount(len(calls))
        for row, call in enumerate(calls):
            checkbox = QTableWidgetItem(); checkbox.setFlags(Qt.ItemFlag.ItemIsUserCheckable | (Qt.ItemFlag.ItemIsEnabled if call.recording_ids else Qt.ItemFlag.NoItemFlags)); checkbox.setCheckState(Qt.CheckState.Unchecked); self.table.setItem(row, 0, checkbox)
            values = [call.started_at.strftime("%d.%m.%Y %H:%M:%S") if call.started_at else "—", call.direction.label, ", ".join(call.employee_names) or "—", call.external_number or "—", format_duration(call.talk_duration_seconds), str(len(call.recording_ids)) if call.recording_ids else "Нет"]
            for column, value in enumerate(values, 1): self.table.setItem(row, column, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def _calls_error(self, error):
        logger.error("Call search failed: %s\n%s", error.exception, error.traceback)
        self.find_button.setEnabled(True); self.find_button.setText("Найти звонки"); QMessageBox.warning(self, "MANGO Downloader", "MANGO не вернул список звонков.\nПопробуйте повторить запрос.")

    def _select_all(self):
        for row, call in enumerate(self.calls):
            if call.recording_ids: self.table.item(row, 0).setCheckState(Qt.CheckState.Checked)

    def _browse(self):
        selected = QFileDialog.getExistingDirectory(self, "Папка для записей", self.directory.text())
        if selected: self.directory.setText(selected); self.settings["download_directory"] = selected; self.settings_store.save(self.settings)

    def _download(self):
        selected = [call for row, call in enumerate(self.calls) if self.table.item(row, 0).checkState() == Qt.CheckState.Checked]
        if not selected: QMessageBox.information(self, "MANGO Downloader", "Выберите звонки с доступными записями."); return
        self.download_button.setEnabled(False); self.download_button.setText("Скачиваем записи..."); self.progress.setRange(0, sum(len(x.recording_ids) for x in selected)); self.progress.setValue(0); self.progress.show()
        service = DownloadService(self._client(), DownloadHistory(self.paths.download_history_file)); self._run(service.download, self._download_ok, self._download_error, selected, Path(self.directory.text()), progress=True)

    def _progress(self, done, total): self.progress.setMaximum(total); self.progress.setValue(done); self.progress.setFormat(f"Скачано {done} из {total}")
    def _download_ok(self, summary):
        self.download_button.setEnabled(True); self.download_button.setText("Скачать выбранные"); QMessageBox.information(self, "MANGO Downloader", f"Скачивание завершено.\n\nСкачано: {summary.downloaded}\nПропущено: {summary.skipped}\nОшибок: {summary.errors}")
    def _download_error(self, error):
        logger.error("Download operation failed: %s\n%s", error.exception, error.traceback)
        self.download_button.setEnabled(True); self.download_button.setText("Скачать выбранные"); QMessageBox.warning(self, "MANGO Downloader", "Не удалось выполнить скачивание. Подробности записаны в журнал.")
