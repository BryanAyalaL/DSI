"""Lectura y limpieza del CSV de cuentas que entrega la clínica.

El archivo llega tal cual desde producción (espacios, comillas, líneas
vacías, valores no numéricos, repetidos). Este módulo NO lo modifica:
lo lee, limpia cada valor en memoria y separa lo que se puede consultar
de lo que no.
"""

import pandas as pd

# Fila 1 del archivo es el encabezado; la primera fila de datos es la línea 2.
_LINEA_PRIMER_DATO = 2


def leer_cuentas(ruta: str, columna: str = "id_cuenta") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Lee el CSV y devuelve (validos, descartados).

    validos     -> una fila por ID único:
                   id_cuenta (int), veces_en_csv, lineas_csv, posible_duplicado
    descartados -> una fila por valor que no se puede consultar:
                   linea_csv, valor_original, causa
    """
    df = pd.read_csv(
        ruta,
        dtype=str,                # no dejar que pandas convierta a número por su cuenta
        keep_default_na=False,    # un vacío queda como "" y no como NaN
        skip_blank_lines=False,   # no borrar líneas vacías: hay que reportarlas
        encoding="utf-8-sig",     # tolera el BOM que agrega Excel si algún día viene así
    )

    # El encabezado puede traer espacios ("    id_cuenta").
    df.columns = df.columns.str.strip()
    if columna not in df.columns:
        raise ValueError(
            f"El CSV no tiene la columna '{columna}'. Columnas encontradas: {list(df.columns)}"
        )

    original = df[columna]
    linea = df.index + _LINEA_PRIMER_DATO

    # Limpieza SOLO de los bordes: espacios -> comillas -> espacios otra vez
    # (cubre casos como '  " 42 "  '). Nunca se borra nada del medio:
    # "1 2" debe ser inválido, no convertirse en 12.
    limpio = original.str.strip().str.strip('"').str.strip()

    # [0-9] y no \d: \d acepta dígitos Unicode como '٣' que no son IDs válidos.
    es_valido = limpio.str.fullmatch(r"[0-9]+")

    descartados = pd.DataFrame({
        "linea_csv": linea[~es_valido],
        "valor_original": original[~es_valido],
        "causa": limpio[~es_valido].map(lambda v: "vacío" if v == "" else "no numérico"),
    }).reset_index(drop=True)

    # int() une "007" y "7" en el mismo ID.
    ids = pd.DataFrame({
        "id_cuenta": limpio[es_valido].astype(int),
        "linea_csv": linea[es_valido],
    })

    # Una fila por ID, en el orden en que apareció por primera vez.
    validos = (
        ids.groupby("id_cuenta", sort=False)["linea_csv"]
        .agg(veces_en_csv="size", lineas_csv=lambda s: ", ".join(map(str, s)))
        .reset_index()
    )
    validos["posible_duplicado"] = validos["veces_en_csv"] > 1

    return validos, descartados
