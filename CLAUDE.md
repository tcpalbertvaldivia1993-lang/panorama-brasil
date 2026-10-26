# Panorama económico de Brasil

## Objetivo
Construir un proyecto de punta a punta con datos públicos del Banco Central de Brasil (BCB):
API → base de datos SQL → notebook de análisis → dashboard.
El resultado debe servir como pieza de portafolio en GitHub.

## Stack
- Python 3.11+
- requests, pandas, sqlite3 (biblioteca estándar), matplotlib o plotly
- Jupyter (notebooks)
- Streamlit (dashboard)

## Estructura de carpetas
```
panorama-brasil/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── .gitignore
├── src/
│   ├── bcb_client.py      # descarga de series desde la API SGS
│   └── db.py              # esquema SQL y carga de datos
├── sql/
│   ├── schema.sql
│   └── consultas.sql
├── notebooks/
│   └── analisis.ipynb
├── dashboard/
│   └── app.py
└── data/
    └── panorama.db        # SQLite (no subir a GitHub)
```

## Fuente de datos
- API SGS del BCB, sin registro ni credenciales.
- Endpoint: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json`
- Series iniciales: 432 (Selic meta), 433 (IPCA mensual), 1 (dólar venta).
- Las fechas vienen como `dd/mm/aaaa` y los valores como texto: convertir ambos al cargar.
- Para rangos largos, pedir por tramos con `dataInicial` y `dataFinal` (formato `dd/mm/aaaa`).

## Base de datos
Tabla `series`:
- `codigo` INTEGER
- `nombre` TEXT
- `fecha` TEXT (ISO `YYYY-MM-DD`)
- `valor` REAL
- Clave primaria compuesta (`codigo`, `fecha`) para evitar duplicados al recargar.

## Reglas de trabajo
- Trabajar por pasos pequeños y probar cada uno antes de seguir.
- Manejar errores de red (timeout, reintentos) y respuestas vacías.
- La carga debe ser idempotente: ejecutarla dos veces no duplica datos.
- No subir a GitHub: `data/*.db`, `.env`, `__pycache__/`, `.ipynb_checkpoints/`.
- Código y comentarios claros; funciones cortas con docstring.
- Explicar brevemente qué se hizo al terminar cada paso.

## Plan paso a paso
1. Crear la estructura de carpetas, `requirements.txt` y `.gitignore`.
2. `src/bcb_client.py`: función que descargue una serie y devuelva un DataFrame.
3. `sql/schema.sql` y `src/db.py`: crear la base y cargar las series.
4. `sql/consultas.sql`: promedio anual, máximos y mínimos, variación mensual.
5. `notebooks/analisis.ipynb`: gráficos y análisis (Selic vs. IPCA, evolución del dólar).
6. `dashboard/app.py`: Streamlit con selector de serie, rango de fechas y gráficos.
7. `README.md`: descripción, arquitectura, capturas y cómo ejecutarlo.
8. Subir a GitHub.

## Comandos
- Instalar: `pip install -r requirements.txt` (datos y dashboard) o `pip install -r requirements-dev.txt` (además notebook y pruebas)
- Cargar datos: `python -m src.db`
- Notebook (requiere `requirements-dev.txt`): `jupyter notebook notebooks/analisis.ipynb`
- Dashboard: `streamlit run dashboard/app.py`
- Pruebas: `pip install -r requirements-dev.txt` y luego `python -m pytest`

## Criterio de "terminado"
- Los datos se cargan con un solo comando.
- El notebook se ejecuta de principio a fin sin errores.
- El dashboard abre y los filtros funcionan.
- El README permite a otra persona reproducir el proyecto.
