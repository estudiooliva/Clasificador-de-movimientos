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
            try:
                df = pd.read_csv(uploaded_file, encoding="latin-1", delimiter=";", engine="python")
            except Exception:
                df = pd.read_csv(uploaded_file, encoding="latin-1", engine="python")
        else:
            df = pd.read_excel(uploaded_file)
        st.success("✅ Archivo leído correctamente.")
        st.dataframe(df.head())
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        st.stop()

    # Normaliza columnas
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    if "concepto" not in df.columns or "importe" not in df.columns:
        st.error("❌ No se encuentran las columnas esperadas (debe haber 'concepto' e 'importe').")
        st.stop()

    df["concepto"] = df["concepto"].astype(str).str.lower().str.strip()

    comisiones_kw = ["comision", "cargo", "mantenimiento", "tarifa", "servicio bancario"]
    impuestos_kw = ["impuesto", "iva", "retencion", "retención", "perc", "percepcion", "ley 25.413", "cheque"]

    def es_comision(txt): return any(k in txt for k in comisiones_kw)
    def es_impuesto(txt): return any(k in txt for k in impuestos_kw)

    df["tipo"] = "Sin Identificacion"
    df.loc[df["concepto"].apply(es_comision), "tipo"] = "Comision"
    df.loc[df["concepto"].apply(es_impuesto), "tipo"] = "Impuesto"
    df.loc[df["importe"] > 0, "tipo"] = "Pago Recibido"
    df.loc[df["importe"] < 0, "tipo"] = "Pago Realizado"

    pagos_recibidos = df[df["tipo"] == "Pago Recibido"][["fecha", "referencia", "concepto", "importe"]].copy()
    pagos_recibidos.rename(columns={
        "fecha": "fecha_de_recepcion",
        "referencia": "referencia",
        "concepto": "nombre_del_pagador",
        "importe": "importe_recibido"
    }, inplace=True)
    pagos_recibidos["cuit_del_pagador"] = ""

    pagos_realizados = df[df["tipo"] == "Pago Realizado"][["fecha", "referencia", "concepto", "importe"]].copy()
    pagos_realizados.rename(columns={
        "fecha": "fecha_de_pago",
        "referencia": "referencia",
        "concepto": "nombre_del_proveedor",
        "importe": "importe_pagado"
    }, inplace=True)
    pagos_realizados["cuit_del_proveedor"] = ""

    comisiones = df[df["tipo"] == "Comision"][["fecha", "referencia", "concepto", "importe"]].copy()
    comisiones.rename(columns={"fecha": "fecha_del_debito", "referencia": "referencia",
                               "concepto": "detalle", "importe": "importe_debitado"}, inplace=True)

    impuestos = df[df["tipo"] == "Impuesto"][["fecha", "referencia", "concepto", "importe"]].copy()
    impuestos.rename(columns={"fecha": "fecha_del_debito", "referencia": "referencia",
                              "concepto": "detalle", "importe": "importe_debitado"}, inplace=True)

    sin_identificar = df[df["tipo"] == "Sin Identificacion"][["fecha", "referencia", "importe"]].copy()
    sin_identificar.rename(columns={"fecha": "fecha_del_debito", "referencia": "referencia",
                                    "importe": "importe_debitado"}, inplace=True)
    sin_identificar["detalle"] = "Sin Identificacion"

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pagos_recibidos.to_excel(writer, index=False, sheet_name="1 - Pagos Recibidos")
        pagos_realizados.to_excel(writer, index=False, sheet_name="2 - Pagos Realizados")
        comisiones.to_excel(writer, index=False, sheet_name="3 - Comisiones Bancarias")
        impuestos.to_excel(writer, index=False, sheet_name="4 - Impuestos e IVA")
        sin_identificar.to_excel(writer, index=False, sheet_name="5 - No Identificados")

        for sheet in writer.sheets.values():
            for i in range(5):
                sheet.set_column(i, i, 25)

    output.seek(0)
    st.download_button(
        label="⬇️ Descargar Excel clasificado",
        data=output,
        file_name="movimientos-clasificados-Principado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
