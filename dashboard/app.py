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

from dashboard.idiomas import FORMATO_FECHA, IDIOMAS, NOMBRES_SERIES, TEXTOS  # noqa: E402
from src.bcb_client import SERIES  # noqa: E402
from src.consultas import leer_series, selic_vs_ipca  # noqa: E402
from src.db import base_lista, crear_base  # noqa: E402

COLORES = {432: "#1f77b4", 433: "#d62728", 1: "#2ca02c"}

st.set_page_config(page_title="Panorama Brasil", page_icon="📈", layout="wide")


@st.cache_resource(show_spinner=False)
def preparar_base() -> None:
    """Si falta data/panorama.db (por ejemplo en Streamlit Cloud), descarga las series y la crea.

    cache_resource hace que se ejecute una sola vez, aunque haya varios visitantes a la vez.
    """
    if not base_lista():
        crear_base()


@st.cache_data
def cargar_datos() -> pd.DataFrame:
    """Lee la tabla series una sola vez y la guarda en caché."""
    return leer_series()


def tarjetas(datos: pd.DataFrame, codigo: int) -> None:
    """Muestra último valor, cambio en el período, máximo y mínimo de una serie."""
    serie = datos[datos["codigo"] == codigo].sort_values("fecha")
    if serie.empty:
        st.info(T["sin_datos"])
        return
    primero, ultimo = serie.iloc[0], serie.iloc[-1]
    maximo = serie.loc[serie["valor"].idxmax()]
    minimo = serie.loc[serie["valor"].idxmin()]

    # El dólar se compara en %, las tasas (Selic, IPCA) en puntos porcentuales
    if codigo == 1:
        cambio = T["cambio_pct"].format(valor=100 * (ultimo["valor"] / primero["valor"] - 1))
    else:
        cambio = T["cambio_pp"].format(valor=ultimo["valor"] - primero["valor"])

    col1, col2, col3 = st.columns(3)
    col1.metric(T["ultimo"].format(fecha=f"{ultimo['fecha']:{FECHA}}"), f"{ultimo['valor']:.4g}", cambio)
    col2.metric(T["maximo"].format(fecha=f"{maximo['fecha']:{FECHA}}"), f"{maximo['valor']:.4g}")
    col3.metric(T["minimo"].format(fecha=f"{minimo['fecha']:{FECHA}}"), f"{minimo['valor']:.4g}")


# ---------- Encabezado con selector de idioma ----------
col_titulo, col_idioma = st.columns([5, 1], vertical_alignment="bottom")
# Antes de dibujar el selector leemos el idioma guardado para traducir su etiqueta
idioma_previo = st.session_state.get("idioma", next(iter(IDIOMAS)))
idioma = col_idioma.selectbox(
    TEXTOS[idioma_previo]["idioma"],
    options=list(IDIOMAS),
    format_func=IDIOMAS.get,
    key="idioma",
)
T = TEXTOS[idioma]
NOMBRES = NOMBRES_SERIES[idioma]
FECHA = FORMATO_FECHA[idioma]
col_titulo.title(T["titulo"])

# ---------- Datos ----------
try:
    with st.spinner(T["descargando"]):
        preparar_base()
except RuntimeError as error:  # la API no respondió ni con reintentos
    st.error(T["error_descarga"].format(error=error))
    st.stop()

series = cargar_datos().assign(nombre=lambda df: df["codigo"].map(NOMBRES))

# ---------- Filtros (barra lateral) ----------
st.sidebar.header(T["filtros"])
# Una clave por idioma para que el navegador redibuje los nombres traducidos;
# la selección se guarda aparte para no perderla al cambiar de idioma
elegidas = st.sidebar.multiselect(
    T["series"],
    options=list(SERIES),
    default=st.session_state.get("series_elegidas", list(SERIES)),
    format_func=lambda codigo: f"{codigo} - {NOMBRES[codigo]}",
    key=f"series_{idioma}",
)
st.session_state["series_elegidas"] = elegidas
fecha_min, fecha_max = series["fecha"].min().date(), series["fecha"].max().date()
rango = st.sidebar.date_input(
    T["rango"],
    value=(pd.Timestamp("2015-01-01").date(), fecha_max),
    min_value=fecha_min,
    max_value=fecha_max,
    format="YYYY-MM-DD",  # formato fijo: si cambiara con el idioma, se perdería el rango elegido
    key="rango_fechas",
)
# Mientras el usuario elige, date_input puede devolver una sola fecha
if len(rango) != 2:
    st.sidebar.warning(T["elige_fechas"])
    st.stop()
desde, hasta = pd.Timestamp(rango[0]), pd.Timestamp(rango[1])

st.sidebar.caption(T["fuente"].format(fecha=f"{fecha_max:{FECHA}}"))

filtrado = series[series["codigo"].isin(elegidas) & series["fecha"].between(desde, hasta)]

st.caption(T["periodo"].format(desde=f"{desde:{FECHA}}", hasta=f"{hasta:{FECHA}}"))

if not elegidas:
    st.warning(T["elige_serie"])
    st.stop()

pestaña_series, pestaña_real, pestaña_tabla = st.tabs(T["pestañas"])

# ---------- Pestaña 1: cada serie con sus tarjetas y gráfico ----------
with pestaña_series:
    for codigo in elegidas:
        st.subheader(NOMBRES[codigo])
        tarjetas(filtrado, codigo)
        datos_serie = filtrado[filtrado["codigo"] == codigo]
        tipo = px.bar if codigo == 433 else px.line  # el IPCA mensual se lee mejor en barras
        fig = tipo(datos_serie, x="fecha", y="valor",
                   color_discrete_sequence=[COLORES[codigo]],
                   labels={"fecha": "", "valor": NOMBRES[codigo]})
        fig.update_layout(height=320, margin={"t": 10, "b": 10})
        st.plotly_chart(fig, width="stretch")

# ---------- Pestaña 2: Selic vs. IPCA 12 meses ----------
with pestaña_real:
    mensual = selic_vs_ipca(series)
    mensual = mensual[(mensual.index >= desde) & (mensual.index <= hasta)]
    if mensual.empty:
        st.info(T["sin_datos_real"])
    else:
        ultimo = mensual.iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric(T["selic_meta"], f"{ultimo['selic']:.2f} %")
        col2.metric(T["ipca_12m"], f"{ultimo['ipca_12m']:.2f} %")
        col3.metric(T["tasa_real"], f"{ultimo['tasa_real']:.2f} {T['unidad_pp']}")
        st.caption(T["nota_real"].format(mes=f"{mensual.index[-1]:%m/%Y}"))

        fig = go.Figure()
        fig.add_scatter(x=mensual.index, y=mensual["selic"], name=T["linea_selic"],
                        line={"color": COLORES[432]})
        fig.add_scatter(x=mensual.index, y=mensual["ipca_12m"], name=T["linea_ipca"],
                        line={"color": COLORES[433]})
        fig.add_bar(x=mensual.index, y=mensual["tasa_real"], name=T["barra_real"],
                    marker_color=["#d62728" if v < 0 else "#9ecae1" for v in mensual["tasa_real"]],
                    opacity=0.6)
        fig.update_layout(height=450, hovermode="x unified", yaxis_title="%",
                          legend={"orientation": "h", "y": 1.1})
        st.plotly_chart(fig, width="stretch")

# ---------- Pestaña 3: promedio anual y descarga ----------
with pestaña_tabla:
    columnas = T["columnas"]
    st.subheader(T["promedio_anual"])
    anual = (filtrado.assign(año=filtrado["fecha"].dt.year)
             .pivot_table(index="año", columns="nombre", values="valor", aggfunc="mean")
             .round(2)
             .rename_axis(index=columnas["año"], columns=None))
    st.dataframe(anual, width="stretch")

    st.subheader(T["datos_filtrados"])
    tabla = (filtrado.assign(fecha=filtrado["fecha"].dt.strftime("%Y-%m-%d"))
             .rename(columns=columnas))
    st.dataframe(tabla, width="stretch", hide_index=True, height=300)
    st.download_button(
        T["descargar"],
        data=tabla.to_csv(index=False).encode("utf-8"),
        file_name="panorama_brasil.csv",
        mime="text/csv",
    )
