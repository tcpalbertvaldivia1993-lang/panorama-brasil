"""Pruebas del dashboard: traducciones completas y la app funcionando en los tres idiomas."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.idiomas import FORMATO_FECHA, IDIOMAS, NOMBRES_SERIES, TEXTOS
from src.bcb_client import SERIES
from src.db import base_lista

APP = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


# ---------- Traducciones (no necesitan datos) ----------

def test_ingles_es_el_idioma_por_defecto():
    assert next(iter(IDIOMAS)) == "en"


@pytest.mark.parametrize("idioma", list(IDIOMAS))
def test_cada_idioma_tiene_los_mismos_textos_que_el_ingles(idioma):
    assert TEXTOS[idioma].keys() == TEXTOS["en"].keys()
    assert TEXTOS[idioma]["columnas"].keys() == TEXTOS["en"]["columnas"].keys()
    assert len(TEXTOS[idioma]["pestañas"]) == 3


@pytest.mark.parametrize("idioma", list(IDIOMAS))
def test_cada_idioma_nombra_todas_las_series(idioma):
    assert NOMBRES_SERIES[idioma].keys() == SERIES.keys()
    assert idioma in FORMATO_FECHA


# ---------- La app completa (necesita data/panorama.db; en CI se omite) ----------

necesita_datos = pytest.mark.skipif(
    not base_lista(), reason="sin data/panorama.db: cárgala con `python -m src.db`"
)


def abrir_app():
    return AppTest.from_file(APP, default_timeout=60).run()


@necesita_datos
@pytest.mark.parametrize("idioma", list(IDIOMAS))
def test_app_funciona_en_cada_idioma(idioma):
    at = abrir_app()
    at.selectbox(key="idioma").set_value(idioma).run()

    assert not at.exception
    assert not at.error
    assert at.title[0].value == TEXTOS[idioma]["titulo"]
    assert [pestaña.label for pestaña in at.tabs] == TEXTOS[idioma]["pestañas"]


@necesita_datos
def test_filtros_se_mantienen_al_cambiar_de_idioma():
    at = abrir_app()
    at.sidebar.multiselect[0].set_value([1]).run()
    at.sidebar.date_input[0].set_value((date(2020, 1, 1), date(2022, 12, 31))).run()

    at.selectbox(key="idioma").set_value("pt").run()

    assert at.sidebar.multiselect[0].value == [1]
    assert at.sidebar.date_input[0].value == (date(2020, 1, 1), date(2022, 12, 31))


@necesita_datos
def test_sin_series_elegidas_muestra_aviso():
    at = abrir_app()
    at.sidebar.multiselect[0].set_value([]).run()
    assert at.warning[0].value == TEXTOS["en"]["elige_serie"]
    assert not at.tabs
