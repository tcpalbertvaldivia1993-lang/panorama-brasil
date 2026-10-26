"""Carga y ejecuta por nombre las consultas de sql/consultas.sql."""

import re
import sqlite3

import pandas as pd

from src.db import RAIZ, RUTA_DB

RUTA_CONSULTAS = RAIZ / "sql" / "consultas.sql"


def cargar_consultas() -> dict[str, str]:
    """Lee consultas.sql y devuelve {nombre: sql} según los comentarios '-- nombre: ...'."""
    texto = RUTA_CONSULTAS.read_text(encoding="utf-8")
    partes = re.split(r"^-- nombre: (\w+)\s*$", texto, flags=re.MULTILINE)[1:]
    return {nombre: sql.strip() for nombre, sql in zip(partes[::2], partes[1::2])}


def ejecutar(nombre: str) -> pd.DataFrame:
    """Ejecuta la consulta indicada sobre data/panorama.db y devuelve un DataFrame."""
    consultas = cargar_consultas()
    if nombre not in consultas:
        raise KeyError(f"No existe la consulta '{nombre}'. Disponibles: {list(consultas)}")
    with sqlite3.connect(RUTA_DB) as conexion:
        return pd.read_sql_query(consultas[nombre], conexion)


def selic_vs_ipca(series: pd.DataFrame) -> pd.DataFrame:
    """Devuelve por mes la Selic meta al cierre, el IPCA acumulado en 12 meses y la tasa real."""
    ipca = series[series["codigo"] == 433].set_index("fecha")["valor"].sort_index()
    ipca_12m = ((1 + ipca / 100).rolling(12).apply(lambda x: x.prod(), raw=True) - 1) * 100
    selic = (series[series["codigo"] == 432].set_index("fecha")["valor"]
             .sort_index().resample("MS").last())
    mensual = pd.DataFrame({"selic": selic, "ipca_12m": ipca_12m}).dropna()
    mensual["tasa_real"] = mensual["selic"] - mensual["ipca_12m"]
    return mensual


def leer_series() -> pd.DataFrame:
    """Devuelve la tabla series completa con la fecha como datetime."""
    with sqlite3.connect(RUTA_DB) as conexion:
        df = pd.read_sql_query("SELECT codigo, nombre, fecha, valor FROM series", conexion)
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df
