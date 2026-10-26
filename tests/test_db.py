"""Pruebas de la base SQLite. Usan una base temporal; nunca tocan data/panorama.db."""

import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

from src import db


def filas(codigo, valores):
    """Crea un DataFrame como el que devuelve descargar_serie."""
    return pd.DataFrame({
        "codigo": codigo,
        "nombre": f"serie {codigo}",
        "fecha": [f"2024-01-{dia:02d}" for dia in range(1, len(valores) + 1)],
        "valor": valores,
    })


@pytest.fixture
def ruta(tmp_path):
    return tmp_path / "prueba.db"


def contar(ruta):
    with sqlite3.connect(ruta) as conexion:
        return conexion.execute("SELECT COUNT(*) FROM series").fetchone()[0]


# ---------- conectar y guardar ----------

def test_conectar_crea_la_tabla_series(ruta):
    conexion = db.conectar(ruta)
    tablas = conexion.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    conexion.close()
    assert ("series",) in tablas


def test_guardar_dos_veces_no_duplica(ruta):
    conexion = db.conectar(ruta)
    db.guardar(conexion, filas(432, [11.75, 11.75, 11.25]))
    db.guardar(conexion, filas(432, [11.75, 11.75, 11.25]))
    conexion.close()
    assert contar(ruta) == 3


def test_guardar_actualiza_valores_corregidos(ruta):
    conexion = db.conectar(ruta)
    db.guardar(conexion, filas(433, [0.42]))
    db.guardar(conexion, filas(433, [0.44]))  # el BCB corrigió el dato
    valor = conexion.execute("SELECT valor FROM series").fetchone()[0]
    conexion.close()
    assert valor == 0.44


# ---------- base_lista ----------

def test_base_lista_falso_si_no_existe_y_no_crea_el_archivo(ruta):
    assert db.base_lista(ruta) is False
    assert not ruta.exists()


def test_base_lista_falso_si_el_archivo_esta_vacio(ruta):
    ruta.write_bytes(b"")
    assert db.base_lista(ruta) is False


def test_base_lista_falso_si_la_tabla_no_tiene_filas(ruta):
    db.conectar(ruta).close()
    assert db.base_lista(ruta) is False


def test_base_lista_verdadero_con_datos(ruta):
    conexion = db.conectar(ruta)
    db.guardar(conexion, filas(1, [4.85]))
    conexion.close()
    assert db.base_lista(ruta) is True


# ---------- crear_base (con la descarga simulada) ----------

def test_crear_base_carga_todas_las_series(monkeypatch, ruta):
    monkeypatch.setattr(db, "descargar_serie", lambda codigo, inicio: filas(codigo, [1.0, 2.0]))
    db.crear_base(ruta)

    assert db.base_lista(ruta)
    assert contar(ruta) == 2 * len(db.SERIES)
    assert not ruta.with_suffix(".tmp").exists()


def test_crear_base_si_falla_no_deja_base_incompleta(monkeypatch, ruta):
    def descarga_que_falla(codigo, inicio):
        if codigo == 433:
            raise RuntimeError("API caída")
        return filas(codigo, [1.0])

    monkeypatch.setattr(db, "descargar_serie", descarga_que_falla)
    with pytest.raises(RuntimeError):
        db.crear_base(ruta)
    assert not ruta.exists()


def test_crear_base_si_falla_conserva_la_base_anterior(monkeypatch, ruta):
    monkeypatch.setattr(db, "descargar_serie", lambda codigo, inicio: filas(codigo, [1.0, 2.0, 3.0]))
    db.crear_base(ruta)
    filas_antes = contar(ruta)

    def descarga_que_falla(codigo, inicio):
        raise RuntimeError("API caída")

    monkeypatch.setattr(db, "descargar_serie", descarga_que_falla)
    with pytest.raises(RuntimeError):
        db.crear_base(ruta)
    assert contar(ruta) == filas_antes


# ---------- Actualización incremental ----------

def test_ultima_fecha_sin_datos_es_none(ruta):
    conexion = db.conectar(ruta)
    assert db.ultima_fecha(conexion, 432) is None
    conexion.close()


def test_desde_para_actualizar_serie_vacia_empieza_en_inicio(ruta):
    conexion = db.conectar(ruta)
    assert db.desde_para_actualizar(conexion, 432) == db.INICIO
    conexion.close()


def test_desde_para_actualizar_retrocede_el_margen(ruta):
    conexion = db.conectar(ruta)
    db.guardar(conexion, pd.DataFrame({"codigo": [1], "nombre": ["dólar"],
                                       "fecha": ["2026-10-23"], "valor": [5.4]}))
    assert db.ultima_fecha(conexion, 1) == date(2026, 10, 23)
    assert db.desde_para_actualizar(conexion, 1) == date(2026, 10, 23) - timedelta(days=db.MARGEN_DIAS)
    assert db.desde_para_actualizar(conexion, 432) == db.INICIO  # otra serie, todavía vacía
    conexion.close()


def test_actualizar_base_pide_solo_lo_nuevo_y_conserva_lo_anterior(monkeypatch, ruta):
    conexion = db.conectar(ruta)
    for codigo in db.SERIES:
        db.guardar(conexion, pd.DataFrame({"codigo": codigo, "nombre": "x",
                                           "fecha": ["2000-01-03", "2026-09-01"], "valor": 1.0}))
    conexion.close()

    pedidos = {}

    def descarga_nueva(codigo, inicio):
        pedidos[codigo] = inicio
        return pd.DataFrame({"codigo": [codigo], "nombre": ["x"], "fecha": ["2026-10-01"], "valor": [2.0]})

    monkeypatch.setattr(db, "descargar_serie", descarga_nueva)
    db.actualizar_base(ruta)

    esperado = date(2026, 9, 1) - timedelta(days=db.MARGEN_DIAS)
    assert pedidos == {codigo: esperado for codigo in db.SERIES}
    assert contar(ruta) == 3 * len(db.SERIES)  # 2 filas viejas + 1 nueva por serie


def test_cargar_series_con_desde_ignora_lo_que_ya_hay(monkeypatch, ruta):
    conexion = db.conectar(ruta)
    db.guardar(conexion, filas(432, [11.75]))
    pedidos = {}

    def descarga(codigo, inicio):
        pedidos[codigo] = inicio
        return filas(codigo, [1.0])

    monkeypatch.setattr(db, "descargar_serie", descarga)
    db.cargar_series(conexion, desde=date(2015, 1, 1))
    conexion.close()
    assert set(pedidos.values()) == {date(2015, 1, 1)}
