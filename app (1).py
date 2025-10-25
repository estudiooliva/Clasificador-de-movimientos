
import io
import unicodedata
import re
import pandas as pd
import streamlit as st

# ---------- Helpers ----------

def _slug(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s.lower()).strip("_")
    return s

def _first_col(df, candidates):
    cols = { _slug(c): c for c in df.columns }
    for cand in candidates:
        if cand in cols:
            return cols[cand]
    return None

def _to_datetime(series):
    def parse_one(x):
        if pd.isna(x):
            return pd.NaT
        if isinstance(x, pd.Timestamp):
            return x
        s = str(x).strip()
        for fmt in [None, "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
            try:
                return pd.to_datetime(s, format=fmt, dayfirst=True, errors="raise") if fmt else pd.to_datetime(s, dayfirst=True, errors="raise")
            except Exception:
                continue
        return pd.NaT
    return series.apply(parse_one)

def _to_number(series):
    import re
    def parse_num(x):
        if pd.isna(x):
            return 0.0
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x)
        s = s.replace(" ", "")
        if re.search(r"\d+,\d{3}", s) and "." not in s:
            s = s.replace(",", "")
        else:
            s = s.replace(".", "").replace(",", ".")
        try:
            return float(s)
        except Exception:
            try:
                return pd.to_numeric(s, errors="coerce")
            except Exception:
                return 0.0
    return series.apply(parse_num).fillna(0.0)

def detect_direction_and_amount(df, col_importe, col_credito, col_debito, col_tipo):
    if col_credito and col_debito:
        credito = _to_number(df[col_credito])
        debito  = _to_number(df[col_debito])
        importe = credito - debito
    elif col_importe is not None:
        importe = _to_number(df[col_importe])
    else:
        importe = pd.Series([0.0]*len(df))

    direction = pd.Series(["zero"]*len(df))
    if col_tipo:
        tipos = df[col_tipo].astype(str).str.lower()
        direction = tipos.apply(lambda t: "in" if any(k in t for k in ["credito","cr","ingreso","abono","deposito","dep","acred"])
                                         else ("out" if any(k in t for k in ["debito","db","egreso","pago","transferencia_saliente","extraccion","cheque"])
                                               else "zero"))
    sign_based = importe.apply(lambda v: "in" if v>0 else ("out" if v<0 else "zero"))
    direction = direction.mask(direction=="zero", sign_based)
    return importe, direction

def categorize_rows(df, detalle_col):
    detalle = df[detalle_col].astype(str).str.lower().fillna("")
    kw_comisiones = st.session_state.get("kw_comisiones", ["comision","comisión","gasto de mantenimiento","cargo","tarifa","servicio bancario","mantenimiento","seguro de cuenta"])
    kw_impuestos  = st.session_state.get("kw_impuestos",  ["impuesto","iva","i.v.a","retencion","retención","perc","percepcion","impuesto debitos y creditos","impuesto a los debitos","impuesto al cheque","ley 25413","idc"])

    is_comision = detalle.apply(lambda t: any(k in t for k in kw_comisiones))
    is_impuesto = detalle.apply(lambda t: any(k in t for k in kw_impuestos))
    return is_comision, is_impuesto

def build_output_sheets(df, fecha_col, ref_col, nombre_col, cuit_col, detalle_col, importe_series, direction_series):
    fecha_out   = _to_datetime(df[fecha_col]) if fecha_col else pd.Series([pd.NaT]*len(df))
    ref_out     = df[ref_col] if ref_col else pd.Series([""]*len(df))
    nombre_out  = df[nombre_col] if nombre_col else pd.Series([""]*len(df))
    cuit_out    = df[cuit_col] if cuit_col else pd.Series([""]*len(df))
    detalle_out = df[detalle_col] if detalle_col else pd.Series([""]*len(df))
    importe_out = importe_series

    is_comision, is_impuesto = categorize_rows(df, detalle_col if detalle_col else ref_col if ref_col else df.columns[0])

    base = pd.DataFrame({
        "fecha": fecha_out,
        "referencia": ref_out.astype(str),
        "nombre": nombre_out.astype(str),
        "cuit": cuit_out.astype(str),
        "detalle": detalle_out.astype(str),
        "importe": importe_out
    })

    remaining = base[~(is_comision | is_impuesto)].copy()
    remaining["dir"] = direction_series

    sh1 = remaining[remaining["dir"]=="in"].copy()
    sh1 = sh1.rename(columns={
        "fecha":"fecha_de_recepcion",
        "nombre":"nombre_del_pagador",
        "cuit":"cuit_del_pagador",
        "importe":"importe_recibido"
    })[["fecha_de_recepcion","referencia","nombre_del_pagador","cuit_del_pagador","importe_recibido"]]

    sh2 = remaining[remaining["dir"]=="out"].copy()
    sh2 = sh2.rename(columns={
        "fecha":"fecha_de_pago",
        "nombre":"nombre_del_proveedor",
        "cuit":"cuit_del_proveedor",
        "importe":"importe_pagado"
    })[["fecha_de_pago","referencia","nombre_del_proveedor","cuit_del_proveedor","importe_pagado"]]

    sh3 = base[is_comision].copy()
    sh3 = sh3.rename(columns={
        "fecha":"fecha_del_debito",
        "detalle":"detalle",
        "importe":"importe_debitado"
    })[["fecha_del_debito","referencia","detalle","importe_debitado"]]

    sh4 = base[is_impuesto].copy()
    sh4 = sh4.rename(columns={
        "fecha":"fecha_del_debito",
        "detalle":"detalle",
        "importe":"importe_debitado"
    })[["fecha_del_debito","referencia","detalle","importe_debitado"]]

    sh5 = remaining[(remaining["dir"]=="zero") | (
            (remaining["nombre"].str.strip()=="") & (remaining["cuit"].str.strip()=="")
        )].copy()
    sh5 = sh5.rename(columns={
        "fecha":"fecha_del_debito",
        "importe":"importe_debitado"
    })
    sh5["detalle"] = "Sin Identificacion"
    sh5 = sh5[["fecha_del_debito","referencia","detalle","importe_debitado"]]

    def sort_if_date(df, date_col):
        if date_col in df.columns:
            return df.sort_values(by=[date_col, "referencia"], kind="stable", na_position="last")
        return df

    sh1 = sort_if_date(sh1, "fecha_de_recepcion")
    sh2 = sort_if_date(sh2, "fecha_de_pago")
    sh3 = sort_if_date(sh3, "fecha_del_debito")
    sh4 = sort_if_date(sh4, "fecha_del_debito")
    sh5 = sort_if_date(sh5, "fecha_del_debito")

    return sh1, sh2, sh3, sh4, sh5

def autosize_and_formats(writer, sheet_name, df, date_cols, money_cols):
    workbook  = writer.book
    worksheet = writer.sheets[sheet_name]
    header_fmt = workbook.add_format({"bold": True})
    for col_num, col_name in enumerate(df.columns):
        worksheet.write(0, col_num, col_name, header_fmt)
    for idx, col in enumerate(df.columns):
        max_len = max([len(str(col))] + [len(str(x)) for x in df[col].astype(str).head(1000)])
        worksheet.set_column(idx, idx, min(max_len + 2, 60))
    worksheet.autofilter(0, 0, max(len(df), 1), len(df.columns)-1)
    date_fmt  = workbook.add_format({"num_format": "dd/mm/yyyy"})
    money_fmt = workbook.add_format({"num_format": "#,##0.00"})
    for dc in date_cols:
        if dc in df.columns:
            col_idx = df.columns.get_loc(dc)
            worksheet.set_column(col_idx, col_idx, 12, date_fmt)
    for mc in money_cols:
        if mc in df.columns:
            col_idx = df.columns.get_loc(mc)
            worksheet.set_column(col_idx, col_idx, 14, money_fmt)

def guess_columns(df):
    slug_to_orig = { _slug(c): c for c in df.columns }
    def find(cands):
        for c in cands:
            if c in slug_to_orig:
                return slug_to_orig[c]
        return None
    fecha_col   = find(["fecha","fecha_operacion","fecha_mov","fecha_debito","fecha_credito","date","posting_date"])
    ref_col     = find(["referencia","n_operacion","nro_operacion","numero_operacion","n_referencia","detalle","descripcion","concepto","glosa","referencia_bancaria","ref","memo"])
    nombre_col  = find(["nombre","nombre_pagador","pagador","cliente","emisor","beneficiario","proveedor","titular","contraparte","razon_social"])
    cuit_col    = find(["cuit","cuil","dni","tax_id","doc","documento","id_fiscal"])
    detalle_col = find(["detalle","descripcion","concepto","glosa","referencia","observaciones"])
    credito_col = find(["credito","creditos","haber","entrada","ingreso","acreditacion","amount_in","in"])
    debito_col  = find(["debito","debitos","debe","salida","egreso","extraccion","amount_out","out"])
    importe_col = find(["importe","monto","importe_total","importe_neto","importe_bruto","importe_movimiento","monto_total","amount","transaction_amount"])
    tipo_col    = find(["tipo","tipo_movimiento","operacion","movimiento","cr_db","debe_haber"])
    if detalle_col is None:
        detalle_col = ref_col if ref_col else (list(df.columns)[0] if len(df.columns) else None)
    return fecha_col, ref_col, nombre_col, cuit_col, detalle_col, importe_col, credito_col, debito_col, tipo_col

def process_dataframe(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    fecha_col, ref_col, nombre_col, cuit_col, detalle_col, importe_col, credito_col, debito_col, tipo_col = guess_columns(df)
    importe, direction = detect_direction_and_amount(df, importe_col, credito_col, debito_col, tipo_col)
    sh1, sh2, sh3, sh4, sh5 = build_output_sheets(df, fecha_col, ref_col, nombre_col, cuit_col, detalle_col, importe, direction)
    return sh1, sh2, sh3, sh4, sh5

def to_excel_bytes(sheets):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        names = [
            "1 - Pagos recibidos",
            "2 - Pagos realizados",
            "3 - Comisiones bancarias",
            "4 - Impuestos y IVA",
            "5 - No identificados",
        ]
        date_cols = [
            ["fecha_de_recepcion"],
            ["fecha_de_pago"],
            ["fecha_del_debito"],
            ["fecha_del_debito"],
            ["fecha_del_debito"],
        ]
        money_cols = [
            ["importe_recibido"],
            ["importe_pagado"],
            ["importe_debitado"],
            ["importe_debitado"],
            ["importe_debitado"],
        ]
        for df, name, dcs, mcs in zip(sheets, names, date_cols, money_cols):
            df = df.copy()
            df.to_excel(writer, index=False, sheet_name=name)
            autosize_and_formats(writer, name, df, dcs, mcs)
    output.seek(0)
    return output.getvalue()

# ---------- UI ----------

st.set_page_config(page_title="Clasificador de Movimientos Bancarios", page_icon="💼")

st.title("💼 Clasificador de Movimientos Bancarios → Excel")
st.write("Subí un **CSV** o **Excel** con los movimientos bancarios y te devolvemos un Excel con 5 hojas, con formato profesional.")
st.markdown("""
1. **Pagos recibidos** (fecha, referencia, nombre del pagador, CUIT del pagador, importe recibido)  
2. **Pagos realizados** (fecha, referencia, nombre del proveedor, CUIT del proveedor, importe pagado)  
3. **Comisiones bancarias** (fecha del débito, referencia, detalle, importe debitado)  
4. **Impuestos e IVA** (fecha del débito, referencia, detalle, importe debitado)  
5. **No identificados** (fecha del débito, referencia, detalle = "Sin Identificacion", importe debitado)
""")

with st.expander("⚙️ Palabras clave (opcional)"):
    kw_comisiones = st.text_input("Palabras clave para **Comisiones** (separadas por coma)", 
                                  "comision,comisión,gasto de mantenimiento,cargo,tarifa,servicio bancario,mantenimiento,seguro de cuenta")
    kw_impuestos  = st.text_input("Palabras clave para **Impuestos/IVA** (separadas por coma)", 
                                  "impuesto,iva,i.v.a,retencion,retención,perc,percepcion,impuesto debitos y creditos,impuesto a los debitos,impuesto al cheque,ley 25413,idc")
    st.session_state["kw_comisiones"] = [k.strip().lower() for k in kw_comisiones.split(",") if k.strip()]
    st.session_state["kw_impuestos"]  = [k.strip().lower() for k in kw_impuestos.split(",") if k.strip()]

uploaded = st.file_uploader("Elegí el archivo", type=["csv","xlsx","xls"])

if uploaded is not None:
    try:
        if uploaded.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded, engine="openpyxl")
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        st.stop()

    st.success(f"Archivo cargado: **{uploaded.name}** ({len(df)} filas)")
    st.dataframe(df.head(20))

    sh1, sh2, sh3, sh4, sh5 = process_dataframe(df)

    st.subheader("Vistas previas")
    tabs = st.tabs(["1) Pagos recibidos", "2) Pagos realizados", "3) Comisiones", "4) Impuestos/IVA", "5) No identificados"])
    for t, d in zip(tabs, [sh1, sh2, sh3, sh4, sh5]):
        with t:
            st.dataframe(d)

    excel_bytes = to_excel_bytes([sh1, sh2, sh3, sh4, sh5])
    st.download_button(
        "⬇️ Descargar Excel clasificado",
        data=excel_bytes,
        file_name="movimientos-clasificados-Principado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.caption("Incluye formato: encabezados en negrita, columnas autoajustadas y formatos de fecha y moneda. No se excluyen transferencias.")
