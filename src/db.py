"""Crea la base SQLite y carga en ella las series del BCB."""

import argparse
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

from src.bcb_client import SERIES, descargar_serie

RAIZ = Path(__file__).resolve().parents[1]
RUTA_DB = RAIZ / "data" / "panorama.db"
RUTA_ESQUEMA = RAIZ / "sql" / "schema.sql"


def conectar(ruta: Path = RUTA_DB) -> sqlite3.Connection:
    """Abre la base (la crea si no existe) y aplica el esquema."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta)
    conexion.executescript(RUTA_ESQUEMA.read_text(encoding="utf-8"))
    return conexion


def guardar(conexion: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Inserta o actualiza las filas del DataFrame. Devuelve cuántas se escribieron."""
    filas = df[["codigo", "nombre", "fecha", "valor"]].itertuples(index=False, name=None)
    with conexion:
        cursor = conexion.executemany(
            "INSERT OR REPLACE INTO series (codigo, nombre, fecha, valor) VALUES (?, ?, ?, ?)",
            filas,
        )
    return cursor.rowcount


def resumen(conexion: sqlite3.Connection) -> pd.DataFrame:
    """Devuelve filas, primera y última fecha por serie."""
    consulta = """
        SELECT codigo, nombre, COUNT(*) AS filas, MIN(fecha) AS desde, MAX(fecha) AS hasta
        FROM series
        GROUP BY codigo, nombre
        ORDER BY codigo
    """
    return pd.read_sql_query(consulta, conexion)


def cargar_series(conexion: sqlite3.Connection, desde: date = date(2000, 1, 1)) -> None:
    """Descarga todas las series desde la fecha indicada y las guarda en la base."""
    for codigo, nombre in SERIES.items():
        print(f"Descargando {codigo} - {nombre}...")
        df = descargar_serie(codigo, inicio=desde)
        if df.empty:
            print("  Sin datos en el rango pedido.")
            continue
        print(f"  {guardar(conexion, df)} filas guardadas.")


def base_lista(ruta: Path = RUTA_DB) -> bool:
    """Indica si la base existe y su tabla series tiene datos (sin crear el archivo si falta)."""
    if not ruta.exists():
        return False
    try:
        with sqlite3.connect(f"file:{ruta}?mode=ro", uri=True) as conexion:
            return conexion.execute("SELECT COUNT(*) FROM series").fetchone()[0] > 0
    except sqlite3.Error:  # archivo vacío, roto o sin la tabla
        return False


def crear_base(ruta: Path = RUTA_DB) -> None:
    """Crea la base desde cero en un archivo temporal y lo renombra solo si la carga termina bien.

    Así, si la descarga falla a mitad de camino, no queda una base incompleta.
    """
    temporal = ruta.with_suffix(".tmp")
    temporal.unlink(missing_ok=True)
    conexion = conectar(temporal)
    try:
        cargar_series(conexion)
    finally:
        conexion.close()
    temporal.replace(ruta)


def main() -> None:
    """Descarga todas las series y las carga en data/panorama.db."""
    parser = argparse.ArgumentParser(description="Carga las series del BCB en SQLite.")
    parser.add_argument("--desde", type=date.fromisoformat, default=date(2000, 1, 1),
                        help="fecha inicial AAAA-MM-DD (por defecto 2000-01-01)")
    args = parser.parse_args()

    conexion = conectar()
    try:
        cargar_series(conexion, args.desde)
        print("\nContenido de la tabla series:")
        print(resumen(conexion).to_string(index=False))
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
