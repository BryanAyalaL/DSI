# Bitácora de uso de IA

## 1. Qué herramienta de IA usé y para qué

Claude. La usé primero para dividir todo el trabajo en 3 partes: solo me decía los pasos y, con ella, tomé decisiones sobre qué se haría, cómo se haría y por qué descartaba o elegía unas u otras cosas. También la usé para programar: aunque en el pasado he usado pandas y por eso lo volví a usar aquí, la sintaxis no la recuerdo, pero sí puedo leerlo sin complicaciones.

## 2. Los 3 prompts que más me sirvieron

Los que más me sirvieron fueron en los que le dije qué decisiones tomé o qué iba a hacer.

- ya cree cuentas.csv, verifícalo, deje los espaciops de sangria ya que dijieron no tocar los datos y lo que trae la api es:
  {
    "userId": 1,
    "id": 7,
    "title": "magnam facilis autem",
    "body": "dolore placeat quibusdam ea quo vitae\nmagni quis enim qui quis quo nemo aut saepe\nquidem repellat excepturi ut quia\nsunt ut sequi eos ea sed quas"
  }
1: si o si debe ser sin espacios y sin comillas 2: solo numeros y 3: quiero que autoamricamente lea si el json ezta vacio decirle que es invalido, en vez de definir un limite mumerico para las ids

-  todos los espacios menos los saltos y tienes razon, mejor espacios y comillas de ñps bordes, cuando es 500 pues se maneja de forma diferente, se lanza un mensaje diciendo que hubo un eror de servidor o de red y que no es por el codigo si no de donde viene o que piensas que sea le mehjor opcion? y estoy de acuerdo con: Te sugiero que devuelva dos cosas: Válidos: una fila por ID con id_cuenta (como número) y veces_en_csv. Descartados: con el valor original tal como llegó, el número de fila del CSV y la causa (vacío, no numérico). Guarda el original y no el limpio: auditoría tiene que ver el abc exactamente como lo mandó la clínica.

- leido todo eso quiero que sea mi asistente en ese trabajo, no que lo ahags, si no dcirme como empezar y que desiciones yo debo tomar y yo decir lo que se hara, ademas tambien porque neceisto saber todo lo que se hace, dame los 3 primeros pasos iniciales

## 3. Algo que la IA me entregó mal o incompleto

La IA solo programa cuando ya estoy seguro; tal vez lo que entregó incompleto fue al inicio, donde deducía cómo se iba a hacer este programa, pero yo le dije cuáles eran las decisiones, como qué cosas usar: pandas, httpx, SQLite, etc.

## 4. Qué decidí yo sin consultarle

Antes de preguntarle a la IA ya había decidido:

- **Usar pandas** para limpiar los datos, porque ya lo había usado antes.
- **Usar httpx y un `config.toml`**, y **separar el código en módulos** (`lector.py`, `cliente_api.py`, `estados.py`, `reporte.py` y `main.py`). La IA me había listado opciones en el primer paso, pero elegí sin pedirle una recomendación; cuando le pedí revisar el proyecto, eso ya estaba creado.
- **Dejar la sangría que trae el CSV en el correo**, porque el enunciado dice que no se arregle a mano: el programa tiene que lidiar con el archivo tal como llega.
- **Saber si un ID no existe por la respuesta de la API, y no con un límite fijo de IDs**, porque los IDs son autoincrementables y cualquier límite quedaría desactualizado.

Otras decisiones las tomé yo eligiendo entre opciones que la IA me presentó: SQLite para guardar el estado, el lote calculado con el hash del archivo, una sola fila por ID repetido con el conteo de veces, registrar los descartados en el Excel en vez de borrarlos, que el 404 decida si un ID no existe, guardar solo `userId` y `title` (sin `body`), acumular los intentos entre ejecuciones y usar una sola hoja en el Excel.
