-- Esquema de la base panorama.db
CREATE TABLE IF NOT EXISTS series (
    codigo INTEGER NOT NULL,   -- código de la serie en el SGS
    nombre TEXT    NOT NULL,   -- nombre legible de la serie
    fecha  TEXT    NOT NULL,   -- fecha ISO AAAA-MM-DD
    valor  REAL,               -- valor numérico
    PRIMARY KEY (codigo, fecha)
);
