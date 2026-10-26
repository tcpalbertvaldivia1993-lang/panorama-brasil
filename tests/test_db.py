"""Pruebas de la base SQLite. Usan una base temporal; nunca tocan data/panorama.db."""

import sqlite3

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
