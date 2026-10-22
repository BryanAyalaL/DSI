"""Excel de salida y resumen de la ejecución.

El Excel se regenera COMPLETO en cada ejecución a partir de:
- el lector (orden del CSV, repetidos, descartados) y
- SQLite (resultado de cada consulta).
Nunca se le agregan filas, así que no puede duplicarlas.
"""

import os

import pandas as pd

COLUMNAS = [
    "id_cuenta", "estado", "detalle", "http_status", "user_id", "titulo",
    "veces_en_csv", "lineas_csv", "posible_duplicado", "intentos", "fecha_consulta",
]
_ENTEROS = ["id_cuenta", "http_status", "user_id", "veces_en_csv", "intentos"]
_ANCHO_MAX = 60


def armar_tabla(validos: pd.DataFrame, descartados: pd.DataFrame,
                resultados: pd.DataFrame) -> pd.DataFrame:
    """Une lector + SQLite en una sola tabla, en el orden del CSV."""
    # how="left": todo ID del CSV aparece, aunque no tenga resultado en SQLite.
    val = validos.merge(resultados, on="id_cuenta", how="left")
    val["estado"] = val["estado"].fillna("sin_consultar")
    val["detalle"] = val["mensaje_error"]
    val["_orden"] = val["lineas_csv"].str.split(",").str[0].astype(int)

    desc = pd.DataFrame({
        "estado": "descartado",
        # Se muestra el valor tal como llegó, entre comillas para que se vean los espacios.
        "detalle": [
            causa if causa == "vacío" else f'{causa}: "{valor}"'
            for causa, valor in zip(descartados["causa"], descartados["valor_original"])
        ],
        "veces_en_csv": 1,
        "lineas_csv": descartados["linea_csv"].astype(str),
        "posible_duplicado": False,
        "intentos": 0,
        "_orden": descartados["linea_csv"],
    })

    tabla = pd.concat([val, desc], ignore_index=True).sort_values("_orden")
    tabla["posible_duplicado"] = tabla["posible_duplicado"].map({True: "Sí", False: "No"})
    # Int64 (con I mayúscula) = entero que acepta vacíos; evita que salga 1.0
    tabla[_ENTEROS] = tabla[_ENTEROS].astype("Int64")
    return tabla[COLUMNAS].reset_index(drop=True)


def escribir_excel(tabla: pd.DataFrame, ruta: str) -> None:
    """Escribe el Excel en un archivo temporal y luego lo reemplaza.

    Si el proceso se cae a mitad de la escritura, el Excel anterior
    queda intacto en vez de quedar un archivo corrupto.
    """
    temporal = ruta + ".tmp.xlsx"
    with pd.ExcelWriter(temporal, engine="openpyxl") as writer:
        tabla.to_excel(writer, sheet_name="Resultados", index=False)
        hoja = writer.sheets["Resultados"]
        hoja.freeze_panes = "A2"               # encabezado fijo al bajar
        hoja.auto_filter.ref = hoja.dimensions  # filtro en cada columna
        for columna in hoja.columns:
            ancho = max(len(str(c.value)) if c.value is not None else 0 for c in columna)
            hoja.column_dimensions[columna[0].column_letter].width = min(ancho + 2, _ANCHO_MAX)
    os.replace(temporal, ruta)  # reemplazo atómico


def armar_resumen(tabla: pd.DataFrame, lote: str, consultados_ahora: int) -> str:
    """Texto del resumen: cuántos se resolvieron y cuántos fallaron, por causa."""
    conteo = tabla["estado"].value_counts()
    filas_csv = int(tabla["veces_en_csv"].sum())

    def n(estado):
        return int(conteo.get(estado, 0))

    lineas = [
        f"RESUMEN - lote {lote[:12]}",
        f"Filas en el CSV: {filas_csv} -> {len(tabla) - n('descartado')} IDs únicos, "
        f"{n('descartado')} descartados",
        f"Consultados en esta ejecución: {consultados_ahora}",
        f"  Encontrados:        {n('encontrado')}",
        f"  No existen (404):   {n('no_existe')}",
        f"  Error técnico:      {n('error_tecnico')}",
        f"  Descartados:        {n('descartado')}",
    ]
    if n("sin_consultar"):
        lineas.append(f"  Sin consultar:      {n('sin_consultar')}")

    # Agrupado por causa: errores técnicos y descartados.
    for estado, titulo in (("error_tecnico", "Errores técnicos"), ("descartado", "Descartados")):
        detalle = tabla.loc[tabla["estado"] == estado, "detalle"]
        if detalle.empty:
            continue
        if estado == "descartado":
            detalle = detalle.str.split(":").str[0]  # solo la causa, sin el valor
        lineas.append(f"{titulo} por causa:")
        for causa, cantidad in detalle.value_counts().items():
            lineas.append(f"  {causa}: {cantidad}")

    return "\n".join(lineas)
