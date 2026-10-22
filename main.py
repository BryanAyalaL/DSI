"""Punto de entrada: coordina lector -> consultas -> estado -> Excel -> resumen.

Uso:
    python main.py                  # usa config.toml junto a este archivo
    python main.py otra_config.toml # usa otra configuración

Las rutas relativas de la configuración se resuelven desde la carpeta del
archivo de configuración, no desde donde se lanza el comando (el Programador
de tareas de Windows suele lanzar desde C:\\Windows\\System32).

Códigos de salida:
    0 = todo resuelto
    1 = terminó, pero quedan errores técnicos pendientes (relanzar más tarde)
    2 = error fatal: no pudo empezar o no pudo escribir el Excel
"""

import logging
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path

from src import estados, reporte
from src.cliente_api import ClienteAPI, Resultado
from src.lector import leer_cuentas

SALIDA_OK = 0
SALIDA_PENDIENTES = 1
SALIDA_FATAL = 2

log = logging.getLogger("proceso")


def configurar_log(ruta_log: Path) -> None:
    formato = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    # Si la consola no soporta un carácter (ej. '٣' en cp1252), se reemplaza
    # en vez de tumbar el proceso.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    archivo = logging.FileHandler(ruta_log, mode="a", encoding="utf-8")  # acumula
    consola = logging.StreamHandler(sys.stdout)
    for h in (archivo, consola):
        h.setFormatter(formato)

    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    raiz.handlers = [archivo, consola]
    logging.getLogger("httpx").setLevel(logging.WARNING)  # quita su línea por request


def main() -> int:
    ruta_config = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("config.toml")
    base = ruta_config.resolve().parent

    # 1. Configuración y log. Si esto falla no hay log aún: se avisa por consola.
    try:
        # utf-8-sig: tolera el BOM que agregan algunos editores de Windows
        # (tomllib.load lo rechaza con "Invalid statement").
        cfg = tomllib.loads(ruta_config.read_text(encoding="utf-8-sig"))
        configurar_log(base / cfg["salida"]["log"])
    except Exception as e:
        print(f"ERROR FATAL: no se pudo cargar la configuración '{ruta_config}': {e}",
              file=sys.stderr)
        return SALIDA_FATAL

    log.info("===== Inicio de ejecución =====")
    try:
        return ejecutar(cfg, base)
    except Exception:
        # Algo que no se esperaba (disco lleno, base bloqueada...): queda en el log.
        log.exception("ERROR FATAL: la ejecución se detuvo")
        return SALIDA_FATAL
    finally:
        log.info("===== Fin de ejecución =====")


def ejecutar(cfg: dict, base: Path) -> int:
    ruta_csv = base / cfg["entrada"]["archivo"]
    ruta_excel = base / cfg["salida"]["excel"]
    ruta_db = base / cfg["estado"]["archivo"]

    # 2. Leer el CSV y abrir el estado.
    validos, descartados = leer_cuentas(ruta_csv, cfg["entrada"]["columna"])
    lote = estados.calcular_lote(ruta_csv)
    conn = estados.abrir(ruta_db)

    cliente = ClienteAPI(
        url_base=cfg["api"]["url_base"],
        timeout_segundos=cfg["api"]["timeout_segundos"],
        max_reintentos=cfg["reintentos"]["max_reintentos"],
        espera_base_segundos=cfg["reintentos"]["espera_base_segundos"],
        codigos_reintentables=cfg["reintentos"]["codigos_reintentables"],
    )

    try:
        # 3. Consultar solo lo que no tiene estado final en este lote.
        resueltos = estados.ids_resueltos(conn, lote)
        # .tolist() da int de Python; sqlite3 no acepta el int64 de numpy.
        pendientes = [i for i in validos["id_cuenta"].tolist() if i not in resueltos]
        log.info("Lote %s | %d IDs únicos | %d ya resueltos | %d por consultar | %d descartados",
                 lote[:12], len(validos), len(resueltos), len(pendientes), len(descartados))

        for id_cuenta in pendientes:
            try:
                resultado = cliente.consultar(id_cuenta)
            except Exception as e:
                # Un error de programación con un ID no debe detener los demás.
                log.exception("ID %s: error inesperado", id_cuenta)
                resultado = Resultado("error_tecnico", 1,
                                      mensaje_error=f"Error inesperado: {type(e).__name__}: {e}")
            # Se guarda apenas llega: si el proceso se cae, lo hecho no se pierde.
            estados.guardar_resultado(conn, lote, id_cuenta, **asdict(resultado))

        # 4. Excel y resumen, siempre desde SQLite.
        tabla = reporte.armar_tabla(validos, descartados, estados.leer_lote(conn, lote))
        log.info("\n%s", reporte.armar_resumen(tabla, lote, len(pendientes)))

        try:
            reporte.escribir_excel(tabla, str(ruta_excel))
        except PermissionError:
            log.error("No se pudo escribir '%s': el archivo está abierto o bloqueado. "
                      "Los resultados SÍ están guardados en '%s'. "
                      "Cierre el Excel y vuelva a ejecutar (no repetirá consultas).",
                      ruta_excel, ruta_db)
            return SALIDA_FATAL
        log.info("Excel generado: %s", ruta_excel)
    finally:
        cliente.cerrar()
        conn.close()

    if tabla["estado"].isin(["error_tecnico", "sin_consultar"]).any():
        log.warning("Quedan IDs pendientes por error técnico. Relanzar más tarde.")
        return SALIDA_PENDIENTES
    return SALIDA_OK


if __name__ == "__main__":
    sys.exit(main())
