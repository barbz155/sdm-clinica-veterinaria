#!/usr/bin/env bash
# ==== SDM Clínica Veterinária - inicia os dois serviços (Linux/macOS) ====
cd "$(dirname "$0")"
python3 -m pip install -r requirements.txt --quiet 2>/dev/null || pip3 install -r requirements.txt --quiet
(cd api_governo && python3 app.py) &
GOV=$!
sleep 2
(cd api_clinica && python3 app.py) &
CLI=$!
echo "Clínica + frontend: http://127.0.0.1:5000  |  API governamental: http://127.0.0.1:5001"
echo "Ctrl+C para encerrar."
trap "kill $GOV $CLI 2>/dev/null" INT TERM
wait
