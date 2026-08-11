# MANGO Downloader

Каркас portable desktop-приложения для Windows 10/11 x64. В PR1 реализованы только GUI и инфраструктура путей, локальных настроек, логирования и сборки. Подключения к MANGO OFFICE API пока нет.

## Структура

- `app/main.py` — запуск приложения и обработка критических ошибок;
- `app/core/` — пути, JSON-настройки и логирование;
- `app/ui/` — окно PySide6;
- `tests/` — инфраструктурные тесты;
- `scripts/build_portable.ps1` — воспроизводимая сборка embedded Python runtime;
- `Start.bat` — единственная точка запуска готового дистрибутива.

## Разработка

Требуется Python 3.12 x64:

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements\dev.txt
.venv\Scripts\python -m app.main
.venv\Scripts\python -m pytest
```

## Portable-сборка

На Windows запустите `Build-Portable.bat`. Скрипт загружает официальный Python Embedded Distribution зафиксированной версии, устанавливает зафиксированные runtime-зависимости внутрь `runtime/`, копирует приложение и создаёт:

```text
dist/MangoDownloader/
dist/MangoDownloader-portable.zip
```

Конечному пользователю нужен только ZIP: после распаковки приложение запускается через `Start.bat` и не обращается к системному Python или `PATH`. Инструкция ручного smoke-теста находится в `scripts/SMOKE_TEST.md`.

При запуске каталоги создаются рядом с приложением. Настройки находятся в `data/settings.json`, журнал — в `logs/app.log`.
