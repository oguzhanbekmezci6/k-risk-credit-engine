@echo off
setlocal
cd /d "%~dp0"
echo.
echo K-RISK V14 - Karar Motoru TR
echo ================================================
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
if not exist ".venv\Scripts\python.exe" (
  echo Ilk calistirma: yerel Python ortami olusturuluyor...
  %PY% -m venv .venv || goto :error
)
if not exist ".venv\.deps_ok" (
  echo K-Risk paketleri kuruluyor / guncelleniyor...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :error
  echo ok> ".venv\.deps_ok"
)
set KRISK_MODE=demo
set KRISK_COOKIE_SECURE=false
echo K-Risk baslatiliyor. Varsayilan adres http://127.0.0.1:8765; port doluysa otomatik bos porta gecer...
".venv\Scripts\python.exe" run.py
goto :eof
:error
echo.
echo Baslatma basarisiz. Python 3.11+ ve internet baglantisini kontrol edin.
pause
