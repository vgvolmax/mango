# MANGO Downloader

Desktop-приложение для Windows 10/11 x64 для скачивания записей звонков MANGO OFFICE.

## Что умеет программа

- проверяет подключение к MANGO OFFICE;
- получает расширенную статистику звонков за выбранный период;
- скачивает доступные записи в MP3 с защитой от повторной загрузки.

## Где взять credentials

Откройте **MANGO OFFICE → Виртуальная АТС → Интеграции → API коннектор**. Там доступны `vpbx_api_key` и `vpbx_api_salt`. Salt хранится только в защищённом Windows DPAPI файле текущего пользователя, а не в `settings.json`.

## Запуск

Пользовательский one-click launcher находится в процессе миграции на source-ZIP архитектуру.

Целевой контракт: Code → Download ZIP → распаковать → `Start.bat`.

До завершения launcher migration текущий `main` не считается готовым пользовательским дистрибутивом.

## Для разработки

Нужен Python 3.12 x64 с pip. Установите `requirements/dev.txt`, затем запускайте `python -m app.main` или `python -m pytest`.
