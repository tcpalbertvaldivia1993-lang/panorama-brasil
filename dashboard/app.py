"""Dashboard de Streamlit: panorama económico de Brasil.

Ejecutar desde la raíz del proyecto:
    venv/bin/streamlit run dashboard/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Streamlit ejecuta el script desde dashboard/: agregamos la raíz para importar src
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.bcb_client import SERIES  # noqa: E402
from src.consultas import leer_series, selic_vs_ipca  # noqa: E402
from src.db import RUTA_DB  # noqa: E402

COLORES = {432: "#1f77b4", 433: "#d62728", 1: "#2ca02c"}

st.set_page_config(page_title="Panorama Brasil", page_icon="📈", layout="wide")


@st.cache_data
def cargar_datos() -> pd.DataFrame:
    """Lee la tabla series una sola vez y la guarda en caché."""
    return leer_series()


def tarjetas(datos: pd.DataFrame, codigo: int) -> None:
    """Muestra último valor, cambio en el período, máximo y mínimo de una serie."""
    serie = datos[datos["codigo"] == codigo].sort_values("fecha")
    if serie.empty:
        st.info("Sin datos en el rango elegido.")
        return
    primero, ultimo = serie.iloc[0], serie.iloc[-1]
    maximo = serie.loc[serie["valor"].idxmax()]
    minimo = serie.loc[serie["valor"].idxmin()]

    # El dólar se compara en %, las tasas (Selic, IPCA) en puntos porcentuales
    if codigo == 1:
        cambio = f"{100 * (ultimo['valor'] / primero['valor'] - 1):+.2f} % en el período"
    else:
        cambio = f"{ultimo['valor'] - primero['valor']:+.2f} p.p. en el período"

    col1, col2, col3 = st.columns(3)
    col1.metric(f"Último ({ultimo['fecha']:%d/%m/%Y})", f"{ultimo['valor']:.4g}", cambio)
    col2.metric(f"Máximo ({maximo['fecha']:%d/%m/%Y})", f"{maximo['valor']:.4g}")
    col3.metric(f"Mínimo ({minimo['fecha']:%d/%m/%Y})", f"{minimo['valor']:.4g}")


# ---------- Datos ----------
if not RUTA_DB.exists():
    st.error("No se encontró data/panorama.db. Primero carga los datos con: "
             "`venv/bin/python -m src.db`")
    st.stop()

series = cargar_datos()

# ---------- Filtros (barra lateral) ----------
st.sidebar.header("Filtros")
elegidas = st.sidebar.multiselect(
    "Series",
    options=list(SERIES),
    default=list(SERIES),
    format_func=lambda codigo: f"{codigo} - {SERIES[codigo]}",
)
fecha_min, fecha_max = series["fecha"].min().date(), series["fecha"].max().date()
rango = st.sidebar.date_input(
    "Rango de fechas",
    value=(pd.Timestamp("2015-01-01").date(), fecha_max),
    min_value=fecha_min,
    max_value=fecha_max,
    format="DD/MM/YYYY",
)
# Mientras el usuario elige, date_input puede devolver una sola fecha
if len(rango) != 2:
    st.sidebar.warning("Elige fecha inicial y final.")
    st.stop()
desde, hasta = pd.Timestamp(rango[0]), pd.Timestamp(rango[1])

st.sidebar.caption(f"Datos: API SGS del Banco Central de Brasil · "
                   f"último dato {fecha_max:%d/%m/%Y}")

filtrado = series[series["codigo"].isin(elegidas) & series["fecha"].between(desde, hasta)]

# ---------- Encabezado ----------
st.title("📈 Panorama económico de Brasil")
st.caption(f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}")

if not elegidas:
    st.warning("Elige al menos una serie en la barra lateral.")
    st.stop()

pestaña_series, pestaña_real, pestaña_tabla = st.tabs(
    ["Series", "Selic vs. inflación", "Promedio anual y datos"]
)

# ---------- Pestaña 1: cada serie con sus tarjetas y gráfico ----------
with pestaña_series:
    for codigo in elegidas:
        st.subheader(SERIES[codigo])
        tarjetas(filtrado, codigo)
        datos_serie = filtrado[filtrado["codigo"] == codigo]
        tipo = px.bar if codigo == 433 else px.line  # el IPCA mensual se lee mejor en barras
        fig = tipo(datos_serie, x="fecha", y="valor",
                   color_discrete_sequence=[COLORES[codigo]],
                   labels={"fecha": "", "valor": SERIES[codigo]})
        fig.update_layout(height=320, margin={"t": 10, "b": 10})
        st.plotly_chart(fig, width="stretch")

# ---------- Pestaña 2: Selic vs. IPCA 12 meses ----------
with pestaña_real:
    mensual = selic_vs_ipca(series)
    mensual = mensual[(mensual.index >= desde) & (mensual.index <= hasta)]
    if mensual.empty:
        st.info("Sin datos de Selic e IPCA en el rango elegido.")
    else:
        ultimo = mensual.iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric("Selic meta", f"{ultimo['selic']:.2f} %")
        col2.metric("IPCA 12 meses", f"{ultimo['ipca_12m']:.2f} %")
        col3.metric("Tasa real aprox.", f"{ultimo['tasa_real']:.2f} p.p.")
        st.caption(f"Último mes con IPCA: {mensual.index[-1]:%m/%Y}. "
                   "Tasa real aprox. = Selic meta − IPCA acumulado en 12 meses.")

        fig = go.Figure()
        fig.add_scatter(x=mensual.index, y=mensual["selic"], name="Selic meta (% a.a.)",
                        line={"color": COLORES[432]})
        fig.add_scatter(x=mensual.index, y=mensual["ipca_12m"], name="IPCA 12 meses (%)",
                        line={"color": COLORES[433]})
        fig.add_bar(x=mensual.index, y=mensual["tasa_real"], name="Tasa real (p.p.)",
                    marker_color=["#d62728" if v < 0 else "#9ecae1" for v in mensual["tasa_real"]],
                    opacity=0.6)
        fig.update_layout(height=450, hovermode="x unified", yaxis_title="%",
                          legend={"orientation": "h", "y": 1.1})
        st.plotly_chart(fig, width="stretch")

# ---------- Pestaña 3: promedio anual y descarga ----------
with pestaña_tabla:
    st.subheader("Promedio anual")
    anual = (filtrado.assign(año=filtrado["fecha"].dt.year)
             .pivot_table(index="año", columns="nombre", values="valor", aggfunc="mean")
             .round(2))
    st.dataframe(anual, width="stretch")

    st.subheader("Datos filtrados")
    tabla = filtrado.assign(fecha=filtrado["fecha"].dt.strftime("%Y-%m-%d"))
    st.dataframe(tabla, width="stretch", hide_index=True, height=300)
    st.download_button(
        "Descargar CSV",
        data=tabla.to_csv(index=False).encode("utf-8"),
        file_name="panorama_brasil.csv",
        mime="text/csv",
    )
