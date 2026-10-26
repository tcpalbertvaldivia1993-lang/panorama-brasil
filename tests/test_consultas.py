"""Pruebas de las consultas SQL y del cálculo Selic vs. IPCA."""

import pandas as pd
import pytest

from src import consultas, db


def test_cargar_consultas_encuentra_todas_por_nombre():
    nombres = consultas.cargar_consultas()
    assert {"promedio_anual", "maximos_minimos", "variacion_mensual", "ipca_anual"} <= set(nombres)
    assert all(sql.strip() for sql in nombres.values())


def test_ejecutar_consulta_inexistente_da_error_claro():
    with pytest.raises(KeyError, match="No existe la consulta"):
        consultas.ejecutar("no_existe")


@pytest.fixture
def base_de_prueba(tmp_path, monkeypatch):
    """Base temporal con dos años de Selic e IPCA, usada por ejecutar()."""
    ruta = tmp_path / "prueba.db"
    conexion = db.conectar(ruta)
    meses = pd.date_range("2023-01-01", "2024-12-01", freq="MS").strftime("%Y-%m-%d")
    datos = pd.concat([
        pd.DataFrame({"codigo": 432, "nombre": "Selic", "fecha": meses, "valor": 10.0}),
        pd.DataFrame({"codigo": 433, "nombre": "IPCA", "fecha": meses, "valor": 0.5}),
    ])
    db.guardar(conexion, datos)
    conexion.close()
    monkeypatch.setattr(consultas, "RUTA_DB", ruta)
    return ruta


@pytest.mark.parametrize("nombre", ["promedio_anual", "maximos_minimos", "variacion_mensual", "ipca_anual"])
def test_todas_las_consultas_se_ejecutan_sin_error(base_de_prueba, nombre):
    resultado = consultas.ejecutar(nombre)
    assert isinstance(resultado, pd.DataFrame)
    assert not resultado.empty


def test_leer_series_convierte_la_fecha(base_de_prueba):
    df = consultas.leer_series()
    assert pd.api.types.is_datetime64_any_dtype(df["fecha"])
    assert len(df) == 48


def test_selic_vs_ipca_acumula_doce_meses():
    meses = pd.date_range("2024-01-01", "2024-12-01", freq="MS")
    series = pd.concat([
        pd.DataFrame({"codigo": 433, "fecha": meses, "valor": 1.0}),   # 1 % cada mes
        pd.DataFrame({"codigo": 432, "fecha": meses, "valor": 13.75}),
    ])
    mensual = consultas.selic_vs_ipca(series)

    # Solo hay un mes con 12 meses de IPCA acumulado: diciembre
    assert list(mensual.index) == [pd.Timestamp("2024-12-01")]
    esperado = (1.01 ** 12 - 1) * 100  # 12,68 %, no 12 %: la inflación se compone
    assert mensual["ipca_12m"].iloc[0] == pytest.approx(esperado)
    assert mensual["tasa_real"].iloc[0] == pytest.approx(13.75 - esperado)


def test_selic_vs_ipca_toma_la_selic_del_ultimo_dia_del_mes():
    dias = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    selic = pd.DataFrame({"codigo": 432, "fecha": dias, "valor": 11.75})
    selic.loc[selic["fecha"] >= "2024-12-15", "valor"] = 12.25  # el Copom subió la tasa a mitad de mes
    ipca = pd.DataFrame({"codigo": 433, "fecha": pd.date_range("2024-01-01", "2024-12-01", freq="MS"),
                         "valor": 0.4})
    mensual = consultas.selic_vs_ipca(pd.concat([selic, ipca]))
    assert mensual["selic"].iloc[-1] == 12.25
