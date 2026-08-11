# Ручной smoke-тест Windows

1. Запустить `Build-Portable.bat`.
2. Распаковать `dist/MangoDownloader-portable.zip` в `C:\Temp\Mango Downloader Test\`.
3. Запустить `Start.bat`, проверить окно и закрыть его.
4. Проверить наличие и работу каталогов `data/`, `logs/` и `downloads/` (после сохранения настроек должны появиться `data/settings.json` и `logs/app.log`).
5. Повторить шаги 2–4 в `C:\Temp\Тест Mango\`.
6. На машине без установленного Python убедиться, что результат тот же.
