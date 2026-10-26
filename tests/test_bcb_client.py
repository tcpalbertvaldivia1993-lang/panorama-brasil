"""Pruebas del cliente de la API SGS. No se conectan a internet: simulan las respuestas."""

from datetime import date

import pytest
import requests

from src import bcb_client
from src.bcb_client import _pedir_tramo, _tramos, descargar_serie


# ---------- _tramos ----------

def test_tramos_rango_corto_es_un_solo_tramo():
    assert _tramos(date(2024, 1, 1), date(2024, 6, 30)) == [(date(2024, 1, 1), date(2024, 6, 30))]


def test_tramos_cubren_todo_el_rango_sin_huecos_ni_solapes():
    inicio, fin = date(2000, 1, 1), date(2026, 10, 26)
    tramos = _tramos(inicio, fin)

    assert tramos[0][0] == inicio
    assert tramos[-1][1] == fin
    for (_, hasta), (desde_siguiente, _) in zip(tramos, tramos[1:]):
        assert (desde_siguiente - hasta).days == 1


def test_tramos_no_superan_diez_años():
    for desde, hasta in _tramos(date(2000, 1, 1), date(2026, 10, 26)):
        assert hasta < desde.replace(year=desde.year + 10)


def test_tramos_empezando_un_29_de_febrero():
    tramos = _tramos(date(2000, 2, 29), date(2015, 1, 1))
    assert tramos[0] == (date(2000, 2, 29), date(2010, 2, 27))
    assert tramos[1][0] == date(2010, 2, 28)


# ---------- _pedir_tramo (con requests.get simulado) ----------

class RespuestaFalsa:
    """Imita lo mínimo de requests.Response que usa el cliente."""

    def __init__(self, status_code=200, datos=None, json_invalido=False):
        self.status_code = status_code
        self.datos = datos
        self.json_invalido = json_invalido

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")

    def json(self):
        if self.json_invalido:
            raise requests.JSONDecodeError("Expecting value", "", 0)
        return self.datos


@pytest.fixture
def sin_esperas(monkeypatch):
    """Evita los time.sleep de los reintentos para que las pruebas sean rápidas."""
    monkeypatch.setattr(bcb_client.time, "sleep", lambda segundos: None)


def simular_respuestas(monkeypatch, *respuestas):
    """Hace que requests.get devuelva (o lance) cada elemento en orden. Devuelve la lista de llamadas."""
    pendientes = list(respuestas)
    llamadas = []

    def get_falso(url, params, timeout):
        llamadas.append(params)
        respuesta = pendientes.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    monkeypatch.setattr(bcb_client.requests, "get", get_falso)
    return llamadas


def test_pedir_tramo_envia_fechas_en_formato_de_la_api(monkeypatch, sin_esperas):
    llamadas = simular_respuestas(monkeypatch, RespuestaFalsa(datos=[]))
    _pedir_tramo(432, date(2024, 1, 5), date(2024, 2, 7))
    assert llamadas[0]["dataInicial"] == "05/01/2024"
    assert llamadas[0]["dataFinal"] == "07/02/2024"


def test_pedir_tramo_404_significa_sin_datos(monkeypatch, sin_esperas):
    simular_respuestas(monkeypatch, RespuestaFalsa(status_code=404))
    assert _pedir_tramo(432, date(2024, 1, 1), date(2024, 1, 31)) == []


def test_pedir_tramo_reintenta_tras_errores_y_luego_funciona(monkeypatch, sin_esperas):
    datos = [{"data": "01/01/2024", "valor": "11.75"}]
    llamadas = simular_respuestas(
        monkeypatch,
        requests.Timeout("tardó demasiado"),
        RespuestaFalsa(status_code=503),
        RespuestaFalsa(json_invalido=True),  # p. ej. una página HTML en vez de JSON
        RespuestaFalsa(datos=datos),
    )
    assert _pedir_tramo(432, date(2024, 1, 1), date(2024, 1, 31)) == datos
    assert len(llamadas) == 4


def test_pedir_tramo_se_rinde_tras_agotar_los_reintentos(monkeypatch, sin_esperas):
    errores = [requests.ConnectionError("sin red")] * bcb_client.REINTENTOS
    simular_respuestas(monkeypatch, *errores)
    with pytest.raises(RuntimeError, match="No se pudo descargar la serie 432"):
        _pedir_tramo(432, date(2024, 1, 1), date(2024, 1, 31))


def test_pedir_tramo_respuesta_vacia_devuelve_lista_vacia(monkeypatch, sin_esperas):
    simular_respuestas(monkeypatch, RespuestaFalsa(datos=None))
    assert _pedir_tramo(432, date(2024, 1, 1), date(2024, 1, 31)) == []


# ---------- descargar_serie (con _pedir_tramo simulado) ----------

def test_descargar_serie_convierte_fechas_y_valores(monkeypatch, sin_esperas):
    monkeypatch.setattr(bcb_client, "_pedir_tramo", lambda codigo, desde, hasta: [
        {"data": "02/01/2024", "valor": "4.8516"},
        {"data": "03/01/2024", "valor": "4.9008"},
    ])
    df = descargar_serie(1, inicio=date(2024, 1, 1), fin=date(2024, 1, 31))

    assert list(df.columns) == ["codigo", "nombre", "fecha", "valor"]
    assert df["fecha"].tolist() == ["2024-01-02", "2024-01-03"]
    assert df["valor"].tolist() == [4.8516, 4.9008]
    assert df["valor"].dtype == "float64"
    assert (df["codigo"] == 1).all()
    assert (df["nombre"] == bcb_client.SERIES[1]).all()


def test_descargar_serie_quita_fechas_repetidas_entre_tramos(monkeypatch, sin_esperas):
    monkeypatch.setattr(bcb_client, "_pedir_tramo", lambda codigo, desde, hasta: [
        {"data": "01/01/2010", "valor": "8.75"},
    ])
    # Un rango de más de 10 años se pide en 2 tramos; ambos devuelven la misma fecha
    df = descargar_serie(432, inicio=date(2005, 1, 1), fin=date(2016, 1, 1))
    assert len(df) == 1


def test_descargar_serie_sin_datos_devuelve_dataframe_vacio(monkeypatch, sin_esperas):
    monkeypatch.setattr(bcb_client, "_pedir_tramo", lambda codigo, desde, hasta: [])
    df = descargar_serie(433, inicio=date(2024, 1, 1), fin=date(2024, 1, 31))
    assert df.empty
    assert list(df.columns) == ["codigo", "nombre", "fecha", "valor"]


def test_descargar_serie_valor_no_numerico_queda_como_nulo(monkeypatch, sin_esperas):
    monkeypatch.setattr(bcb_client, "_pedir_tramo", lambda codigo, desde, hasta: [
        {"data": "01/01/2024", "valor": ""},
    ])
    df = descargar_serie(433, inicio=date(2024, 1, 1), fin=date(2024, 1, 31))
    assert df["valor"].isna().all()
