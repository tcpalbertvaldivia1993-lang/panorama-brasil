"""Cliente para descargar series de la API SGS del Banco Central de Brasil."""

import time
from datetime import date

import pandas as pd
import requests

URL_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"

# Series del proyecto: código SGS -> nombre
SERIES = {
    432: "Selic meta (% a.a.)",
    433: "IPCA mensual (%)",
    1: "Dólar venta (BRL/USD)",
}

# La API limita las series diarias a 10 años por consulta
AÑOS_POR_TRAMO = 10
TIMEOUT = 90  # la API del BCB a veces tarda más de 30 s en responder
REINTENTOS = 5
PAUSA = 1  # segundos entre consultas


def _tramos(inicio: date, fin: date) -> list[tuple[date, date]]:
    """Divide el rango [inicio, fin] en tramos de como máximo 10 años."""
    tramos = []
    desde = inicio
    while desde <= fin:
        try:
            hasta = desde.replace(year=desde.year + AÑOS_POR_TRAMO)
        except ValueError:  # 29 de febrero
            hasta = desde.replace(year=desde.year + AÑOS_POR_TRAMO, day=28)
        hasta = min(date.fromordinal(hasta.toordinal() - 1), fin)
        tramos.append((desde, hasta))
        desde = date.fromordinal(hasta.toordinal() + 1)
    return tramos


def _pedir_tramo(codigo: int, desde: date, hasta: date) -> list[dict]:
    """Pide un tramo a la API, con reintentos ante errores de red."""
    params = {
        "formato": "json",
        "dataInicial": desde.strftime("%d/%m/%Y"),
        "dataFinal": hasta.strftime("%d/%m/%Y"),
    }
    url = URL_BASE.format(codigo=codigo)

    for intento in range(1, REINTENTOS + 1):
        try:
            respuesta = requests.get(url, params=params, timeout=TIMEOUT)
            # La API responde 404 cuando no hay datos en el rango
            if respuesta.status_code == 404:
                return []
            respuesta.raise_for_status()
            # A veces la API devuelve una respuesta vacía o que no es JSON: se reintenta
            return respuesta.json() or []
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError,
                requests.JSONDecodeError) as error:
            if intento == REINTENTOS:
                raise RuntimeError(
                    f"No se pudo descargar la serie {codigo} "
                    f"({params['dataInicial']} - {params['dataFinal']}): {error}"
                ) from error
            time.sleep(5 * intento)  # la API a veces responde 503 si está saturada
    return []


def descargar_serie(codigo: int, inicio: date = date(2000, 1, 1), fin: date | None = None) -> pd.DataFrame:
    """Descarga una serie SGS y devuelve un DataFrame con codigo, nombre, fecha y valor.

    Las fechas se convierten a texto ISO (AAAA-MM-DD) y los valores a número.
    """
    fin = fin or date.today()
    registros = []
    for desde, hasta in _tramos(inicio, fin):
        registros.extend(_pedir_tramo(codigo, desde, hasta))
        time.sleep(PAUSA)  # no saturar la API

    columnas = ["codigo", "nombre", "fecha", "valor"]
    if not registros:
        return pd.DataFrame(columns=columnas)

    df = pd.DataFrame(registros)
    df["fecha"] = pd.to_datetime(df["data"], format="%d/%m/%Y").dt.strftime("%Y-%m-%d")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df["codigo"] = codigo
    df["nombre"] = SERIES.get(codigo, str(codigo))
    return df[columnas].drop_duplicates(subset=["codigo", "fecha"]).reset_index(drop=True)


if __name__ == "__main__":
    for codigo in SERIES:
        datos = descargar_serie(codigo, inicio=date(2024, 1, 1))
        print(f"Serie {codigo}: {len(datos)} filas")
        print(datos.tail(3), "\n")
