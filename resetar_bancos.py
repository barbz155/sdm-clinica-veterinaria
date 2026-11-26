"""Apaga e recria os DOIS bancos (clínica e governo) com os dados fictícios iniciais.
Uso: python resetar_bancos.py   (com os serviços parados)"""
import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
for pasta in ("api_clinica", "api_governo"):
    shutil.rmtree(os.path.join(RAIZ, pasta, "data"), ignore_errors=True)
subprocess.run([sys.executable, "database.py"], cwd=os.path.join(RAIZ, "api_clinica"), check=True)
subprocess.run([sys.executable, "-c", "import app"], cwd=os.path.join(RAIZ, "api_governo"), check=True)
print("Bancos recriados: api_clinica/data/clinica.db e api_governo/data/governo.db")
