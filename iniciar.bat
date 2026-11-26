@echo off
REM ==== SDM Clinica Veterinaria - inicia os dois servicos (Windows) ====
cd /d "%~dp0"
echo Instalando dependencias (Flask e requests)...
python -m pip install -r requirements.txt --quiet
echo.
echo Iniciando API Governamental Simulada em http://127.0.0.1:5001 ...
start "API Governamental (5001)" cmd /k "cd api_governo && python app.py"
timeout /t 2 /nobreak >nul
echo Iniciando API da Clinica + Frontend em http://127.0.0.1:5000 ...
start "API Clinica (5000)" cmd /k "cd api_clinica && python app.py"
timeout /t 3 /nobreak >nul
start http://127.0.0.1:5000
echo.
echo Pronto! Feche as janelas dos servicos para encerrar.
