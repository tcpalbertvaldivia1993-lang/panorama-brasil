"""Pruebas de la base SQLite. Usan una base temporal; nunca tocan data/panorama.db."""

import sqlite3
import time
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


@pytest.fixture
def sin_respaldo(tmp_path):
    """Ruta de un respaldo que no existe: obliga a crear_base a usar la API (simulada)."""
    return tmp_path / "no_existe.csv.gz"


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

def test_crear_base_carga_todas_las_series(monkeypatch, ruta, sin_respaldo):
    monkeypatch.setattr(db, "descargar_serie", lambda codigo, inicio: filas(codigo, [1.0, 2.0]))
    db.crear_base(ruta, sin_respaldo)

    assert db.base_lista(ruta)
    assert contar(ruta) == 2 * len(db.SERIES)
    assert not ruta.with_suffix(".tmp").exists()


def test_crear_base_si_falla_no_deja_base_incompleta(monkeypatch, ruta, sin_respaldo):
    def descarga_que_falla(codigo, inicio):
        if codigo == 433:
            raise RuntimeError("API caída")
        return filas(codigo, [1.0])

    monkeypatch.setattr(db, "descargar_serie", descarga_que_falla)
    with pytest.raises(RuntimeError):
        db.crear_base(ruta, sin_respaldo)
    assert not ruta.exists()


def test_crear_base_si_falla_conserva_la_base_anterior(monkeypatch, ruta, sin_respaldo):
    monkeypatch.setattr(db, "descargar_serie", lambda codigo, inicio: filas(codigo, [1.0, 2.0, 3.0]))
    db.crear_base(ruta, sin_respaldo)
    filas_antes = contar(ruta)

    def descarga_que_falla(codigo, inicio):
        raise RuntimeError("API caída")

    monkeypatch.setattr(db, "descargar_serie", descarga_que_falla)
    with pytest.raises(RuntimeError):
        db.crear_base(ruta, sin_respaldo)
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


# ---------- Respaldo CSV ----------

@pytest.fixture
def base_con_datos(ruta):
    conexion = db.conectar(ruta)
    db.guardar(conexion, pd.concat([filas(1, [4.8516, 4.9008]), filas(433, [0.42, -0.21])]))
    yield conexion
    conexion.close()


def test_respaldo_ida_y_vuelta_conserva_los_datos(base_con_datos, tmp_path):
    respaldo = tmp_path / "respaldo.csv.gz"
    assert db.exportar_respaldo(base_con_datos, respaldo) == 4

    otra = db.conectar(tmp_path / "otra.db")
    assert db.cargar_respaldo(otra, respaldo) == 4
    consulta = "SELECT codigo, nombre, fecha, valor FROM series ORDER BY codigo, fecha"
    assert otra.execute(consulta).fetchall() == base_con_datos.execute(consulta).fetchall()
    otra.close()


def test_respaldo_no_cambia_si_los_datos_no_cambian(base_con_datos, tmp_path):
    """Si el archivo cambiara en cada exportación, el Action haría un commit inútil cada día."""
    respaldo = tmp_path / "respaldo.csv.gz"  # mismo nombre: gzip guarda el nombre en la cabecera
    db.exportar_respaldo(base_con_datos, respaldo)
    antes = respaldo.read_bytes()
    time.sleep(1.1)  # gzip también guarda la hora, salvo que se fije mtime=0
    db.exportar_respaldo(base_con_datos, respaldo)
    assert respaldo.read_bytes() == antes


def test_crear_base_con_respaldo_no_usa_la_api(monkeypatch, base_con_datos, ruta, tmp_path):
    respaldo = tmp_path / "respaldo.csv.gz"
    db.exportar_respaldo(base_con_datos, respaldo)

    def api_caida(codigo, inicio):
        raise RuntimeError("la API no debería usarse")

    monkeypatch.setattr(db, "descargar_serie", api_caida)
    nueva = tmp_path / "nueva.db"
    db.crear_base(nueva, respaldo)
    assert contar(nueva) == 4


def test_esta_vacia(ruta):
    conexion = db.conectar(ruta)
    assert db.esta_vacia(conexion)
    db.guardar(conexion, filas(1, [5.0]))
    assert not db.esta_vacia(conexion)
    conexion.close()


def test_respaldo_del_repositorio_es_valido():
    """El respaldo que se sube a GitHub debe tener las tres series y datos recientes."""
    df = pd.read_csv(db.RUTA_RESPALDO)
    assert list(df.columns) == ["codigo", "nombre", "fecha", "valor"]
    assert set(df["codigo"]) == set(db.SERIES)
    assert not df.duplicated(["codigo", "fecha"]).any()
    assert df["fecha"].min() <= "2000-01-03"
    assert df["valor"].notna().all()
