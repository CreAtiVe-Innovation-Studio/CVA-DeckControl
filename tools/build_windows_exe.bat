@echo off
REM Baut eine eigenstaendige CVA-DeckControl.exe (siehe build_windows_exe.spec).
REM Verifiziert am 2026-09-03 - siehe Hinweis im .spec-Header. Bei Fehlern
REM bitte Log + Windows-/Python-Version als Issue melden.
REM
REM Ausfuehren: tools\build_windows_exe.bat  (im Projektordner, mit Python im PATH)

cd /d "%~dp0\.."

if not exist ".venv-build" (
    echo Lege Build-venv an...
    python -m venv .venv-build
)

call .venv-build\Scripts\activate.bat

echo Installiere Abhaengigkeiten...
pip install --upgrade pip >nul
pip install -r requirements.txt
pip install pyinstaller

echo Baue .exe...
pyinstaller tools\build_windows_exe.spec --distpath dist --workpath build --noconfirm

echo.
echo Fertig, falls keine Fehler oben stehen: dist\CVA-DeckControl\CVA-DeckControl.exe
echo Vor dem ersten Start: config\ (eigene profiles.yaml/location.yaml/ha_secrets.yaml)
echo nach dist\CVA-DeckControl\config\ kopieren, und assets\ als Geschwister-Ordner
echo von dist\CVA-DeckControl\ ablegen (siehe README "Fertige Windows-.exe").
