"""Estado persistente del proceso, guardado en SQLite.

Es lo que hace al proceso re-ejecutable:
- Cada resultado se guarda apenas llega (commit por ID). Si el proceso
  se cae en el ID 9, los 8 anteriores ya quedaron guardados.
- Al relanzar, solo se consultan los IDs que no tienen estado final.
- La llave (lote, id_cuenta) impide filas duplicadas a nivel de base.

Un "lote" es el hash SHA-256 del CSV tal como llegó: el mismo archivo
siempre es el mismo lote; un archivo nuevo es un lote nuevo.
"""

import hashlib
import sqlite3
from datetime import datetime

import pandas as pd

ESTADOS_FINALES = ("encontrado", "no_existe")

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS consultas (
    lote           TEXT    NOT NULL,
    id_cuenta      INTEGER NOT NULL,
    estado         TEXT    NOT NULL
                   CHECK (estado IN ('encontrado', 'no_existe', 'error_tecnico')),
    http_status    INTEGER,
    mensaje_error  TEXT,
    intentos       INTEGER NOT NULL,
    user_id        INTEGER,
    titulo         TEXT,
    fecha_consulta TEXT    NOT NULL,
    PRIMARY KEY (lote, id_cuenta)
)
"""

# Inserta el resultado; si el ID ya existe en el lote, lo actualiza.
# - intentos se ACUMULA entre ejecuciones (consultas.intentos + nuevos).
# - El WHERE final protege un estado final: un resultado "encontrado"
#   o "no_existe" nunca se sobrescribe, ni por error del código.
_GUARDAR = """
INSERT INTO consultas (lote, id_cuenta, estado, http_status, mensaje_error,
                       intentos, user_id, titulo, fecha_consulta)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (lote, id_cuenta) DO UPDATE SET
    estado         = excluded.estado,
    http_status    = excluded.http_status,
    mensaje_error  = excluded.mensaje_error,
    intentos       = consultas.intentos + excluded.intentos,
    user_id        = excluded.user_id,
    titulo         = excluded.titulo,
    fecha_consulta = excluded.fecha_consulta
WHERE consultas.estado = 'error_tecnico'
"""


def calcular_lote(ruta_csv: str) -> str:
    """Huella SHA-256 de los bytes del CSV, tal como llegó."""
    h = hashlib.sha256()
    with open(ruta_csv, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def abrir(ruta_db: str) -> sqlite3.Connection:
    """Abre (o crea) la base y la tabla si no existen."""
    conn = sqlite3.connect(ruta_db)
    with conn:
        conn.execute(_ESQUEMA)
    return conn


def ids_resueltos(conn: sqlite3.Connection, lote: str) -> set[int]:
    """IDs del lote con estado final: no hay que volver a consultarlos."""
    filas = conn.execute(
        "SELECT id_cuenta FROM consultas WHERE lote = ? AND estado IN (?, ?)",
        (lote, *ESTADOS_FINALES),
    )
    return {fila[0] for fila in filas}


def guardar_resultado(
    conn: sqlite3.Connection,
    lote: str,
    id_cuenta: int,
    estado: str,
    intentos: int,
    http_status: int | None = None,
    mensaje_error: str | None = None,
    user_id: int | None = None,
    titulo: str | None = None,
) -> None:
    """Guarda un resultado y hace commit en el momento."""
    fecha = datetime.now().isoformat(timespec="seconds")
    with conn:  # commit al salir; rollback si algo falla
        conn.execute(
            _GUARDAR,
            (lote, id_cuenta, estado, http_status, mensaje_error,
             intentos, user_id, titulo, fecha),
        )


def leer_lote(conn: sqlite3.Connection, lote: str) -> pd.DataFrame:
    """Todos los resultados del lote, para armar el Excel."""
    return pd.read_sql_query(
        "SELECT id_cuenta, estado, http_status, mensaje_error, intentos,"
        "       user_id, titulo, fecha_consulta"
        "  FROM consultas WHERE lote = ?",
        conn,
        params=(lote,),
    )
