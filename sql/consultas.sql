-- Consultas de análisis sobre la tabla series.
-- Cada consulta empieza con "-- nombre: ..." para poder cargarlas por nombre
-- desde el notebook o el dashboard.


-- nombre: promedio_anual
-- Promedio, mínimo y máximo de cada serie por año.
SELECT
    codigo,
    nombre,
    substr(fecha, 1, 4)  AS anio,
    ROUND(AVG(valor), 4) AS promedio,
    MIN(valor)           AS minimo,
    MAX(valor)           AS maximo,
    COUNT(*)             AS observaciones
FROM series
GROUP BY codigo, nombre, anio
ORDER BY codigo, anio;


-- nombre: maximos_minimos
-- Valor máximo y mínimo histórico de cada serie y la primera fecha en que ocurrió.
WITH ordenado AS (
    SELECT
        codigo, nombre, fecha, valor,
        ROW_NUMBER() OVER (PARTITION BY codigo ORDER BY valor DESC, fecha) AS puesto_max,
        ROW_NUMBER() OVER (PARTITION BY codigo ORDER BY valor ASC,  fecha) AS puesto_min
    FROM series
    WHERE valor IS NOT NULL
)
SELECT codigo, nombre, 'máximo' AS tipo, fecha, valor FROM ordenado WHERE puesto_max = 1
UNION ALL
SELECT codigo, nombre, 'mínimo' AS tipo, fecha, valor FROM ordenado WHERE puesto_min = 1
ORDER BY codigo, tipo;


-- nombre: variacion_mensual
-- Valor al cierre de cada mes (último dato del mes) y su variación % frente al mes anterior.
-- Se aplica a Selic (432) y dólar (1). El IPCA (433) ya es una variación mensual.
WITH cierre_mes AS (
    SELECT codigo, substr(fecha, 1, 7) AS mes, MAX(fecha) AS fecha
    FROM series
    WHERE codigo IN (1, 432)
    GROUP BY codigo, mes
),
valores AS (
    SELECT
        s.codigo, s.nombre, c.mes, s.valor,
        LAG(s.valor) OVER (PARTITION BY s.codigo ORDER BY c.mes) AS valor_anterior
    FROM cierre_mes AS c
    JOIN series AS s ON s.codigo = c.codigo AND s.fecha = c.fecha
)
SELECT
    codigo, nombre, mes, valor, valor_anterior,
    ROUND(100.0 * (valor / valor_anterior - 1), 2) AS variacion_pct
FROM valores
ORDER BY codigo, mes;


-- nombre: ipca_anual
-- IPCA acumulado en cada año (se multiplican los factores mensuales 1 + v/100),
-- comparado con la Selic meta promedio del mismo año. La tasa real usa la ecuación
-- de Fisher: (1 + Selic) / (1 + IPCA) − 1.
WITH RECURSIVE ipca AS (
    SELECT
        substr(fecha, 1, 4) AS anio,
        fecha,
        1 + valor / 100.0 AS factor,
        ROW_NUMBER() OVER (PARTITION BY substr(fecha, 1, 4) ORDER BY fecha) AS n
    FROM series
    WHERE codigo = 433
),
acumulado AS (
    SELECT anio, n, factor AS producto FROM ipca WHERE n = 1
    UNION ALL
    SELECT i.anio, i.n, a.producto * i.factor
    FROM acumulado AS a
    JOIN ipca AS i ON i.anio = a.anio AND i.n = a.n + 1
),
ipca_anio AS (
    -- Nos quedamos con el producto del último mes disponible de cada año
    SELECT a.anio, a.n AS meses, ROUND(100.0 * (a.producto - 1), 2) AS ipca_acumulado_pct
    FROM acumulado AS a
    WHERE a.n = (SELECT MAX(n) FROM ipca WHERE ipca.anio = a.anio)
),
selic_anio AS (
    SELECT substr(fecha, 1, 4) AS anio, ROUND(AVG(valor), 2) AS selic_promedio
    FROM series
    WHERE codigo = 432
    GROUP BY anio
)
SELECT
    i.anio, i.meses, i.ipca_acumulado_pct, s.selic_promedio,
    ROUND(100.0 * ((1 + s.selic_promedio / 100.0) / (1 + i.ipca_acumulado_pct / 100.0) - 1), 2)
        AS tasa_real_pct
FROM ipca_anio AS i
LEFT JOIN selic_anio AS s ON s.anio = i.anio
ORDER BY i.anio;
