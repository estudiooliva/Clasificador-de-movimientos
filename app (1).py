import sys
import subprocess

# Instala openpyxl automáticamente si no está instalado
try:
    import openpyxl
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl"])

import pandas as pd
import streamlit as st
import io

# Configuración general
st.set_page_config(page_title="Clasificador de Movimientos – Principado Ciudad Náutica", page_icon="💰", layout="wide")
st.title("💰 Clasificador de Movimientos – Principado Ciudad Náutica")
st.markdown("Subí tu archivo Excel o CSV con los movimientos bancarios y descargá el informe clasificado.")

# Subir archivo
uploaded_file = st.file_uploader("📎 Subí tu archivo (.xlsx o .csv)", type=["xlsx", "csv"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            # Detección automática del delimitador
            try:
                df = pd.read_csv(uploaded_file, encoding="latin-1", delimiter=";", engine="python")

