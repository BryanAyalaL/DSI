# Consulta de cuentas médicas radicadas

Proceso en Python que lee el CSV diario de cuentas radicadas por la clínica, consulta cada
identificador en el sistema externo y genera un Excel consolidado para el equipo de auditoría.
Está pensado para correr solo, de madrugada, sin nadie mirando: ningún identificador que falle
detiene el proceso, y se puede relanzar las veces que haga falta sin repetir consultas ni duplicar filas.

---

## Qué hace

1. **Lee** `cuentas.csv` tal como llega (sin corregirlo a mano) y limpia cada valor en memoria.
2. **Separa** los valores consultables de los que no lo son (vacíos, no numéricos) y agrupa los repetidos.
3. **Consulta** cada ID único pendiente en `https://jsonplaceholder.typicode.com/posts/{id}`,
   con reintentos y espera creciente solo cuando tiene sentido.
4. **Guarda** cada resultado en SQLite apenas llega (estado persistente).
5. **Genera** `resultado_cuentas.xlsx` completo desde SQLite y escribe un **resumen** en consola y log.

---

## Requisitos

- **Python 3.11 o superior** (usa `tomllib`, incluido desde 3.11). Desarrollado y probado con **Python 3.14.6** en Windows 11.
- Dependencias (en `requirements.txt`):
  - `httpx`: cliente HTTP con timeout por defecto y excepciones que distinguen timeout / red / HTTP.
  - `pandas` + `openpyxl`: lectura del CSV y escritura del Excel.
- Acceso a internet hacia `jsonplaceholder.typicode.com`.

## Instalación

```powershell
git clone <url-del-repo>
cd DSI
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Ejecución

```powershell
python main.py                      # usa config.toml junto a main.py
python main.py C:\ruta\otra.toml    # usa otra configuración
```

Las rutas relativas de la configuración se resuelven **desde la carpeta del archivo de configuración**,
no desde donde se lanza el comando. Así funciona igual desde el Programador de tareas de Windows,
que suele lanzar los procesos desde `C:\Windows\System32`.

### Programarlo de madrugada (ejemplo con el Programador de tareas)

```powershell
schtasks /Create /TN "DSI Cuentas" /SC DAILY /ST 03:00 `
  /TR "C:\Proyectos\DSI\.venv\Scripts\python.exe C:\Proyectos\DSI\main.py"
```

### Códigos de salida

| Código | Significado | Qué hacer |
|---|---|---|
| `0` | Todo resuelto | Nada |
| `1` | Terminó, pero quedan IDs con error técnico | Relanzar más tarde (ver runbook) |
| `2` | Error fatal: no pudo empezar o no pudo escribir el Excel | Revisar el log (ver runbook) |

---

## Configuración (`config.toml`)

Todo lo que puede cambiar entre ambientes está fuera del código.

| Sección | Clave | Valor actual | Para qué |
|---|---|---|---|
| `[entrada]` | `archivo` | `cuentas.csv` | CSV de entrada |
| | `columna` | `id_cuenta` | Columna con los identificadores |
| `[salida]` | `excel` | `resultado_cuentas.xlsx` | Excel de salida |
| | `log` | `proceso.log` | Archivo de log (se acumula entre ejecuciones) |
| `[api]` | `url_base` | `https://jsonplaceholder.typicode.com/posts` | Sistema externo |
| | `timeout_segundos` | `10` | Tiempo máximo de espera por llamada |
| `[reintentos]` | `max_reintentos` | `3` | Reintentos después del primer intento (hasta 4 llamadas) |
| | `espera_base_segundos` | `2` | Espera creciente: 2 s, 4 s, 8 s |
| | `codigos_reintentables` | `[429, 500, 502, 503, 504]` | Códigos HTTP que se reintentan |
| `[estado]` | `archivo` | `estado.sqlite3` | Base con el resultado de cada consulta |

---

## Salidas

### `resultado_cuentas.xlsx`: una hoja, "Resultados"

Una fila por ID único y una por cada valor descartado, **en el orden del CSV** (por la primera línea
donde aparece), para que auditoría pueda seguir el archivo de la clínica. Tiene encabezado fijo y filtros.

| Columna | Contenido |
|---|---|
| `id_cuenta` | Identificador (vacío para descartados) |
| `estado` | `encontrado`, `no_existe`, `error_tecnico`, `descartado` (o `sin_consultar`, que no debería aparecer) |
| `detalle` | Mensaje del error técnico, o causa del descarte con el valor tal como llegó |
| `http_status` | Código HTTP de la última llamada (vacío si no hubo respuesta: timeout, red) |
| `user_id`, `titulo` | Datos del registro encontrado (el `body` se omite a propósito: no le sirve a auditoría) |
| `veces_en_csv` | Cuántas veces aparece el ID en el CSV |
| `lineas_csv` | En qué líneas del archivo aparece (ej. `2, 6, 18`) |
| `posible_duplicado` | `Sí` si aparece más de una vez |
| `intentos` | Llamadas realizadas, **acumuladas entre ejecuciones** |
| `fecha_consulta` | Fecha y hora de la última consulta |

### Resumen (consola y log, al final de cada ejecución)

```
RESUMEN - lote 3d4ea0adcf6e
Filas en el CSV: 21 -> 16 IDs únicos, 2 descartados
Consultados en esta ejecución: 16
  Encontrados:        13
  No existen (404):   3
  Error técnico:      0
  Descartados:        2
Descartados por causa:
  no numérico: 1
  vacío: 1
```

En una segunda ejecución con el mismo CSV, `Consultados en esta ejecución` es `0`.

### `proceso.log`

Log en UTF-8, con fecha y hora por línea; se acumula entre ejecuciones. Cada ejecución está entre
`===== Inicio de ejecución =====` y `===== Fin de ejecución =====`. Las URLs consultadas
aparecen en el log (no en el Excel).

---

## Cómo funciona

```
main.py               coordina: config -> log -> lector -> estado -> consultas -> Excel -> resumen
src/lector.py         lee y limpia el CSV; separa válidos / descartados; cuenta repetidos
src/cliente_api.py    consulta un ID con reintentos; nunca lanza excepción por fallas de API/red
src/estados.py        estado persistente en SQLite
src/reporte.py        arma la tabla, escribe el Excel y el resumen
config.toml           parámetros
```

### Re-ejecución: por qué no repite ni duplica

- **Lote = hash SHA-256 del CSV tal como llegó.** El mismo archivo siempre es el mismo lote; el CSV
  del día siguiente es un lote nuevo y se consulta completo.
- **SQLite es la fuente de verdad.** Tabla `consultas` con llave primaria `(lote, id_cuenta)`:
  la propia base impide filas duplicadas.
- **Cada resultado se guarda apenas llega** (un commit por ID). Si el proceso se cae en el ID 9,
  los 8 anteriores ya quedaron guardados.
- Al relanzar, **solo se consultan los IDs sin estado final** (`encontrado` o `no_existe`).
- Un estado final **nunca se sobrescribe**: el `UPDATE` solo aplica sobre filas en `error_tecnico`.
- **El Excel se regenera completo** desde SQLite en cada ejecución; nunca se le agregan filas.
  Se escribe a un temporal y se reemplaza, así una caída a mitad de escritura no deja un Excel corrupto.

---

## Decisiones

### Limpieza del CSV

El CSV se usa exactamente como lo entregaron, **incluida la sangría de 4 espacios** con la que venía
en el correo: el enunciado pide no arreglarlo a mano, y el programa tiene que lidiar con él.

- Se quitan **espacios y comillas solo de los bordes**. Nunca del medio: `1 2` es inválido, no se convierte en `12`.
- Solo se aceptan valores que, ya limpios, sean **dígitos ASCII** (`[0-9]+`). `abc`, `a1b2` o `٣` se descartan.
- `007` y `7` son el mismo ID.
- Se lee con `dtype=str`, `keep_default_na=False` y `skip_blank_lines=False` para que **pandas no decida
  por su cuenta**: por defecto borra las líneas vacías sin avisar y convierte tipos.
- Se lee con `utf-8-sig` para tolerar el BOM que agrega Excel si algún día el CSV viene guardado desde ahí.

### Valores descartados

No se consultan a la API, pero **quedan registrados en el Excel** con `estado = descartado`, la línea
del archivo y el valor tal como llegó (`no numérico: "    abc"`). Auditoría debe saber que la clínica
envió algo que no se pudo procesar; descartarlo en silencio lo ocultaría.

### Identificadores repetidos

**Se consulta una sola vez cada ID y aparece una sola fila**, con `veces_en_csv`, `lineas_csv` y
`posible_duplicado = Sí`.

Por qué:
- Consultar el mismo ID tres veces en la misma ejecución devuelve lo mismo tres veces: es carga
  innecesaria sobre el sistema externo y tres filas idénticas para revisar.
- Pero borrar los repetidos sin dejar rastro ocultaría información: una cuenta médica radicada
  dos veces puede ser un **error de radicación** de la clínica, y eso le interesa a auditoría.
  Por eso se conserva cuántas veces y en qué líneas apareció, y se marca para que se pueda filtrar.

### Cuándo un ID "no existe"

**Decide el código HTTP 404**, no un rango fijo de IDs. El sistema externo crece; si hoy tiene
100 registros, mañana puede tener 200, y un límite en el código quedaría desactualizado.
`0`, `101` y `150` son números válidos: se consultan y la API responde 404.

Un **200 con un cuerpo que no es un registro válido** (vacío, HTML de un proxy o de una página de
mantenimiento) se registra como `error_tecnico`, no como `encontrado`: darlo por bueno sería informarle mal a auditoría.

---

## Frontera de reintentos

La regla: **se reintenta solo lo que puede dar una respuesta distinta si se vuelve a preguntar.**

| Respuesta | ¿Reintenta? | Estado | Por qué |
|---|---|---|---|
| `200` | — | `encontrado` (final) | — |
| `404` | ❌ | `no_existe` (final, **caso de negocio**) | El ID no existe; preguntar otra vez da lo mismo |
| `500`, `502`, `503`, `504` | ✅ | `error_tecnico` | Falla del servidor; suele ser temporal |
| `429` | ✅ | `error_tecnico` | Demasiadas peticiones; esperar y volver a intentar |
| Timeout | ✅ | `error_tecnico` | La red o el servidor pueden recuperarse |
| Error de conexión / DNS | ✅ | `error_tecnico` | La red puede volver |
| Otros `4xx` (`400`, `401`, `403`) | ❌ | `error_tecnico` | Repetir no lo arregla: hay que revisar la configuración |
| `200` con respuesta inválida | ❌ | `error_tecnico` | Respuesta anómala; se revisa, no se insiste |

- **Espera creciente**: `espera_base × 2^(intento-1)`, es decir 2 s, 4 s, 8 s.
- **Dentro de una ejecución**, un `error_tecnico` se reintenta hasta `max_reintentos` (o nada, si no es reintentable).
- **Entre ejecuciones**, todo `error_tecnico` queda **pendiente** y se vuelve a consultar al relanzar
  (incluido un 403: si alguien corrigió la configuración, ahora puede funcionar).
- El 404 es la única frontera de "no reintentar nunca": es la respuesta de negocio.
- `max_reintentos`, la espera base y los códigos reintentables están en `config.toml`.

---

## Runbook: falla a las 3 a.m. y te llaman

**Primero, mira el final del log:**

```powershell
Get-Content C:\Proyectos\DSI\proceso.log -Tail 40 -Encoding utf8
```

Busca la última línea `===== Inicio de ejecución =====` y el `RESUMEN`.

> **Regla de oro:** relanzar `python main.py` **siempre es seguro**. No repite consultas ya resueltas
> ni duplica filas. Ante la duda, corrige la causa y relanza.

### Terminó con código `1`: quedan errores técnicos

En el resumen, sección `Errores técnicos por causa`:

| Causa en el log | Qué significa | Qué hacer |
|---|---|---|
| `Timeout tras 10 s` | El sistema externo no responde a tiempo | Abrir la URL del log en el navegador. Si responde, relanzar. Si no, esperar y relanzar más tarde |
| `Error de red: ConnectError ... getaddrinfo failed` | No hay DNS o internet en la máquina | Revisar la conexión del servidor (`ping jsonplaceholder.typicode.com`). Relanzar cuando vuelva |
| `HTTP 500/502/503/504` | El sistema externo está caído o en mantenimiento | No es del proceso. Relanzar más tarde; si persiste, escalar al dueño del sistema externo |
| `HTTP 429` | Se está consultando demasiado rápido | Relanzar más tarde; si se repite, subir `espera_base_segundos` |
| `HTTP 401/403` | Acceso denegado | Revisar `url_base` en `config.toml` o si el sistema externo cambió su acceso |
| `HTTP 400` o `HTTP 200 con respuesta inesperada` | El sistema externo cambió o la URL está mal | Revisar `url_base`; abrir la URL del log y ver qué devuelve |

Al relanzar, solo se consultan los pendientes.

### Terminó con código `2`: error fatal

| Mensaje en el log / consola | Qué hacer |
|---|---|
| `ERROR FATAL: no se pudo cargar la configuración` | `config.toml` no existe o tiene un error de sintaxis; el mensaje indica la línea |
| `FileNotFoundError: ... No such file or directory: '...cuentas.csv'` | La clínica no entregó el archivo o quedó en otra ruta. Verificar `[entrada] archivo` |
| `El CSV no tiene la columna 'id_cuenta'` | La clínica cambió el formato. El mensaje muestra las columnas que llegaron. Confirmar con la clínica antes de cambiar `columna` |
| `No se pudo escribir '...xlsx': el archivo está abierto o bloqueado` | Alguien dejó el Excel abierto. **Los resultados ya están en SQLite**: cerrar el Excel y relanzar |
| `database is locked` | Otra ejecución está corriendo al mismo tiempo (o un programa tiene abierto `estado.sqlite3`). Esperar a que termine y relanzar |
| `ERROR FATAL: la ejecución se detuvo` + traza | Error no previsto (disco lleno, permisos). La traza completa está en el log |

### Consultas útiles al estado

```powershell
# IDs pendientes (error técnico) de todos los lotes
python -c "import sqlite3; print(sqlite3.connect('estado.sqlite3').execute('select lote, id_cuenta, intentos, mensaje_error from consultas where estado=?', ('error_tecnico',)).fetchall())"
```

### Reprocesar un lote desde cero

Solo si se necesita volver a consultar **todo** (por ejemplo, el sistema externo corrigió datos):
renombrar `estado.sqlite3` (no borrarlo, para conservar la historia) y relanzar.

---

## Pendiente y limitaciones conocidas

Lo que no se alcanzó a hacer, y por qué no bloquea el uso:

- **Cortar antes si la API está totalmente caída.** Hoy, con la configuración por defecto, cada ID
  agota sus reintentos: unos 14 s por ID si no hay red (solo las esperas 2+4+8) y hasta ~54 s si son
  timeouts (4 × 10 s + esperas). Con 16 IDs, entre 4 y 15 minutos. Termina igual con código `1` y todo
  queda pendiente; solo tarda más de lo necesario. Mejora: detener la ronda tras N fallos técnicos seguidos.
- **No se respeta el encabezado `Retry-After` del 429.** El 429 se reintenta con la espera creciente normal.
- **No hay pruebas automatizadas en el repo.** Los casos (503 seguidos, timeouts, red caída, 200 vacío,
  Excel bloqueado, CSV con BOM, valores como `1 2` o `٣`) se probaron manualmente durante el desarrollo;
  el siguiente paso es llevarlos a `pytest`. `ClienteAPI` ya acepta un transporte y una función de espera
  inyectables para poder probarlo sin red y sin esperar.
- **No se impide que corran dos ejecuciones a la vez.** SQLite evita datos corruptos, pero no hay un
  archivo de bloqueo que lo prevenga explícitamente.
- **El lote depende de los bytes exactos del archivo.** Si la clínica reenvía el mismo contenido con un
  cambio mínimo (un salto de línea al final), se trata como un lote nuevo.
- **El log y la base crecen sin límite.** No hay rotación del log ni limpieza de lotes antiguos.

---

## Uso de inteligencia artificial

Ver [`BITACORA.md`](BITACORA.md).
