# Arquitectura: motor de reglas declarativo + runner multi-fuente

Este documento explica **cómo funciona el sistema y cómo extenderlo**, sin
necesidad de leer el código directamente. Si vas a agregar un dominio nuevo,
una regla nueva, o un tipo de origen nuevo, empieza aquí. Si lo que buscas
es levantar las VMs (laboratorio o producción), ver `docs/DEPLOYMENT.md`;
si es correr el pipeline en tu máquina, ver `docs/COMMANDS-PIPELINE.md`.

## Por qué existe esto

El primer dominio implementado (Business Partners, ver
`docs/REGLAS-NEGOCIO.md`) se construyó originalmente con reglas escritas a
mano en Python, una función por regla, específicas de esa tabla. Funciona,
pero no escala a cientos de tablas / varios motores de origen que se
planean a futuro: cada tabla nueva implicaría escribir un módulo Python
nuevo desde cero.

Este diseño separa dos cosas que antes estaban mezcladas:

1. **El motor** (`transforms/rule_engine.py`) y **el runner**
   (`run_pipeline.py`): no saben nada de "business_partners" ni de ningún
   dominio de negocio. Son el código que se reutiliza para cualquier tabla,
   de cualquier dominio, de cualquier motor de origen soportado.
2. **El contenido de negocio** (`contracts/<dominio>.json`,
   `sources/<dominio>.yaml`, `transforms/domains/<dominio>/`): la
   semántica real (qué formato tiene un documento tributario válido, qué
   formato tiene un número de celular en el mercado de destino) es
   inherentemente específica de un dominio y una jurisdicción. Eso nunca va
   a ser genérico, y está bien que no lo sea — lo que sí es genérico es el
   *intérprete* de esas reglas.

**Decisión explícita:** no se intentó construir un motor de validación
"universal para cualquier modelo de base de datos" en el sentido de
adivinar reglas automáticamente. Para eso ya existen herramientas OSS
maduras (Great Expectations, Soda, los tests declarativos de dbt) — si en
algún momento el catálogo de operadores declarativos de aquí se vuelve
insuficiente, la alternativa correcta es adoptar una de esas herramientas,
no construir una versión propia más grande.

## Mapa de carpetas

```structure
sources/<dominio>.yaml          # manifiesto: qué extraer, a dónde, con qué contrato
contracts/<dominio>.json         # contrato declarativo: campos, checks, grupos
transforms/
  rule_engine.py                 # motor genérico (no tocar para agregar reglas de negocio)
  contract_utils.py              # resolución de alias / fail-fast de columnas
  bigquery_gold.py                # helper genérico para crear vistas gold
  source_builders/
    sql.py                        # MSSQL/PostgreSQL/MySQL (mismo código, distinto driver)
  domains/<dominio>/
    plugins.py                    # lógica bespoke que no es expresable como reglas declarativas
    views.py                      # SQL de las vistas gold de ese dominio
run_pipeline.py                  # runner único: python run_pipeline.py --manifest sources/<dominio>.yaml
tests/                           # pytest del motor + regresión por dominio
```

## El contrato (`contracts/<dominio>.json`)

Tres secciones:

### `fields`

Declara qué columnas existen, si son obligatorias, sus alias permitidos (ver
"Convención de Normalización de Columnas" en `docs/REGLAS-NEGOCIO.md`), y si
el campo no existe todavía en el origen (`available_in_source: false`) — en
ese caso el motor emite automáticamente una alerta en cualquier check que
dependa de ese campo, sin que haga falta codificar nada más.

```json
"mobile_phone": { "required": false, "aliases": ["contact_phone"] }
```

### `groups`

Orden de evaluación. Cada grupo puede detener la evaluación de los
siguientes si falla (`stop_on_fail: true`) — replica el patrón de
"categorías con detención temprana" de `docs/REGLAS-NEGOCIO.md`, pero ahora
es una propiedad del contrato, no código.

```json
{ "id": 1, "name": "IDENTIDAD_DOCUMENTACION", "stop_on_fail": true }
```

### `checks`

Cada uno produce una columna de validación. Lee uno o más campos
(`inputs`) y se resuelve de dos formas:

**a) Reglas declarativas** — catálogo de operadores genéricos:

| Operador | Parámetros | Ejemplo |
| --- | --- | --- |
| `not_null` | — | `{"op": "not_null"}` |
| `regex` | `pattern` | `{"op": "regex", "pattern": "^[0-9]+$"}` |
| `length` | `eq` / `min` / `max` | `{"op": "length", "eq": 10}` |
| `range` | `min` / `max` (numérico) | `{"op": "range", "min": 0, "max": 100}` |
| `enum` | `values`, `case_insensitive` | `{"op": "enum", "values": ["A","B"]}` |
| `not_in` | `values`, `case_insensitive` | `{"op": "not_in", "values": ["no","x"]}` |
| `starts_with` | `prefix` | `{"op": "starts_with", "prefix": "3"}` |
| `not_ends_with` | `values` | `{"op": "not_ends_with", "values": [".con"]}` |
| `not_contains` | `values`, `case_insensitive` | `{"op": "not_contains", "values": ["gamil"]}` |
| `digits_only` | — | `{"op": "digits_only"}` |
| `alnum` | `extra_chars` | `{"op": "alnum", "extra_chars": "-"}` |
| `not_repeated_char` | — | detecta comodines tipo `"00000"` |
| `no_spaces` | — | — |

Cada regla acepta `"error_code"` opcional (si no se da, el motor genera uno
con el nombre del operador). Las reglas se evalúan en orden; la primera que
falla determina el código de error del check.

Si un campo llega vacío y ninguna regla del check es `not_null`, el motor
omite la evaluación de ese campo para ese check (ausencia tolerada por
defecto — igual que "el celular vacío no es un error de caracteres, es un
error de obligatoriedad que evalúa otro check").

**b) Plugin** — para lógica que depende de más de un campo de forma no
trivial (dispatch condicional, reglas cruzadas):

```json
{
  "name": "VALIDACION_DOC_ESTRUCTURA",
  "inputs": ["partner_id", "document_type"],
  "plugin": "transforms.domains.business_partners.plugins:validar_doc_estructura"
}
```

El motor importa la función dinámicamente y le pasa la fila completa;
debe devolver un código de estado string (`"OK"`, `"ERROR_..."`, o las
constantes `NOT_APPLICABLE`/`FIELD_NOT_IN_SOURCE` de `rule_engine.py`).

## Estados posibles de un check

- `OK` — pasó.
- `ERROR_<código>` — falló una regla o el plugin determinó un error.
- `NO_EVALUADO` — no se llegó a evaluar porque un grupo anterior detuvo el flujo.
- `NO_APLICA` (`NOT_APPLICABLE`) — el plugin decidió que esta regla no aplica a esta fila (no cuenta como fallo).
- `ALERTA_CAMPO_NO_DISPONIBLE_EN_ORIGEN` (`FIELD_NOT_IN_SOURCE`) — el campo de origen no existe todavía (no cuenta como fallo de grupo, pero sube el estado global a `ALERTA`).

Estado global de la fila (`estado_validacion_global`): `ERROR` si algún
grupo falló: `ALERTA` si no hubo errores pero sí algún `FIELD_NOT_IN_SOURCE`;
si no, `OK`.

## El manifiesto (`sources/<dominio>.yaml`)

Conecta todo: de dónde extraer, con qué credenciales, a qué tabla de BigQuery
cargar, y qué contrato aplicar.

```yaml
domain: business_partners
source_type: sql                          # ver SOURCE_BUILDERS en run_pipeline.py
credentials_section: sources.mssql_business_partners.credentials
tables: [countries, ..., business_partners]
contract: contracts/business_partners.json
rule_target_table: business_partners        # a qué tabla del listado se le aplican los checks
destination:
  dataset: business_partners_data
  write_disposition: replace
gold_views: [resumen_ejecucion_business_partners]
```

**Dominio "solo bronze" (sin reglas de negocio todavía):** `contract` y
`rule_target_table` son opcionales. Si no están, el runner carga las
tablas tal cual, sin pre-flight de columnas ni motor de reglas — útil
cuando el negocio aún no definió reglas para ese dominio. Agregar el
contrato después no requiere tocar el manifiesto salvo por sumar esas dos
claves. Ejemplo ilustrativo (no incluido en este repo, un dominio
hipotético nuevo):

```yaml
domain: orders
source_type: sql
credentials_section: sources.mssql_business_partners.credentials
tables: [order_items, order_statuses, ...]
destination:
  dataset: orders_data
  write_disposition: replace
# sin "contract" ni "rule_target_table": carga bronze pura
```

## Cómo agregar un dominio nuevo

1. Crear `contracts/<dominio>.json` (fields/groups/checks) — **omitir este
   paso y la clave `contract`/`rule_target_table` del manifiesto si el
   negocio todavía no definió reglas** (dominio "solo bronze", ver arriba).
2. Si hace falta lógica bespoke, crear `transforms/domains/<dominio>/plugins.py`.
3. Si hace falta una vista resumen, crear `transforms/domains/<dominio>/views.py`
   con un diccionario `GOLD_VIEWS = {"nombre_vista": "CREATE OR REPLACE VIEW ..."}`.
4. Crear `sources/<dominio>.yaml`.
5. `python run_pipeline.py --manifest sources/<dominio>.yaml`.

No hace falta tocar `run_pipeline.py` ni `rule_engine.py` para esto.

## Cómo agregar una regla a un dominio existente

Editar el contrato JSON: agregar un check nuevo, o agregar una regla a la
lista `rules` de un check existente. No se toca código Python a menos que la
regla necesite un plugin.

## Cómo agregar un tipo de origen nuevo

Hoy solo existe `transforms/source_builders/sql.py` (cubre MSSQL,
PostgreSQL y MySQL, porque `sql_database()` de dlt es agnóstico al motor vía
SQLAlchemy — solo cambia `drivername` en las credenciales). Los siguientes
tipos están identificados como necesarios a futuro (MySQL/PostgreSQL ya
cubiertos por `sql.py`; CSV, XLSX, XML, JSON, REST API pendientes) pero
deliberadamente no se implementan hasta que exista un caso real — evita
construir conectores sin pruebas para fuentes que aún no existen.

Para agregar uno (ejemplo con CSV vía `dlt.sources.filesystem`):

1. Crear `transforms/source_builders/filesystem_csv.py` con una función
   `build_source(manifest: dict) -> tuple[source, columnas_reales]`, igual
   forma que `sql.py`:

   ```python
   from dlt.sources.filesystem import filesystem, read_csv

   def build_source(manifest: dict):
       files = filesystem(bucket_url=manifest["path"], file_glob=manifest["file_glob"])
       source = files | read_csv()
       columnas_reales = set(manifest["expected_columns"])  # o inspeccionar el primer archivo
       return source, columnas_reales
   ```

2. Registrar en `run_pipeline.py`:

   ```python
   SOURCE_BUILDERS = {
       "sql": "transforms.source_builders.sql:build_source",
       "filesystem_csv": "transforms.source_builders.filesystem_csv:build_source",
   }
   ```

3. En el manifiesto del dominio, `source_type: filesystem_csv` + los
   parámetros que ese builder necesite (`path`, `file_glob`, etc.).

Para XLSX (sin soporte nativo en dlt): el builder envuelve
`pandas.read_excel` + `openpyxl` en un `@dlt.resource` generador. Para una
API REST: usar `dlt.sources.rest_api` o `dlt.sources.helpers.rest_client`
dentro del builder, siguiendo el mismo contrato de entrada/salida.

## Capa de transformación (dbt)

dlt deja `business_partners_data` en bronze con las columnas `VALIDACION_*`
y `estado_validacion_global`/`detalle_validacion` ya inyectadas por
`transforms/rule_engine.py`. La capa dbt (`dbt/`) vive un nivel arriba: no
recalcula ninguna regla de negocio, solo enriquece y agrega lo que bronze ya
produjo.

```text
dbt/
  dbt_project.yml
  profiles.yml.example          # copiar a profiles.yml (gitignored) o a ~/.dbt/
  macros/
    generate_schema_name.sql    # +schema del modelo = dataset exacto en BigQuery
  models/
    staging/<dominio>/          # silver: casting, joins de catálogos
      _<dominio>__sources.yml   # declara las tablas bronze que lee este dominio
      stg_<dominio>__<tabla>.sql
    marts/<dominio>/            # gold: agregados, reemplazo de las gold_views dinámicas
      <dominio>__<reporte>.sql
```

**Convención de datasets:** cada capa/dominio tiene su propio dataset en
BigQuery (`staging_business_partners`, `curated_business_partners`, ...), no
se reutiliza `{dominio}_data` con prefijos de tabla — simplifica los
permisos IAM por capa. Esto lo fija `+schema` en `dbt_project.yml` junto con
el override de `generate_schema_name` (sin él, dbt concatenaría el dataset
del profile con el `+schema` del modelo).

**Autenticación:** `profiles.yml` usa `method: oauth` (ADC), igual
convención que `.dlt/secrets.toml` — sin claves JSON de cuenta de servicio.

### Cómo agregar la capa dbt de un dominio nuevo

1. Crear `dbt/models/staging/<dominio>/_<dominio>__sources.yml` declarando
   las tablas bronze que dlt ya escribió para ese dominio.
2. Crear `dbt/models/staging/<dominio>/stg_<dominio>__<tabla>.sql`: casting,
   normalización, joins de catálogos. Sin lógica de negocio nueva — eso ya
   vive en el contrato del lado de dlt.
3. Si hace falta un reporte agregado, crear
   `dbt/models/marts/<dominio>/<dominio>__<reporte>.sql` sobre `ref()` del
   modelo de staging (nunca sobre `source()` directo).
4. Agregar el bloque `+schema` correspondiente en `dbt_project.yml`.
5. `dbt run --select path:models/staging/<dominio>`.

### Criterio para retirar una `gold_view` dinámica existente

Una vista de `transforms/domains/<dominio>/views.py` se retira cuando su
modelo `marts/` equivalente produce el mismo conteo y los mismos valores
agregados durante varias corridas consecutivas — evita mantener dos fuentes
de verdad para el mismo reporte mientras se valida el reemplazo.

## Orquestación (Airflow)

Puesta en marcha del stack (`docker-compose.yml` + `Dockerfile`, VM-02):
ver `docs/COMMANDS-PIPELINE.md` sección 11.

`airflow/dags/medallion_dag_factory.py` lee cada `sources/<dominio>.yaml` y
construye un DAG de 3 fases — no hay un DAG escrito a mano por dominio,
mismo principio que `run_pipeline.py` del lado de dlt:

```text
extract_bronze (SSHOperator -> VM-01, corre run_pipeline.py)
        ↓
transform_staging (BashOperator -> dbt run --select path:models/staging/<dominio>, en VM-02)
        ↓
transform_curated (BashOperator -> dbt run --select path:models/marts/<dominio>, en VM-02)
```

`transform_staging`/`transform_curated` solo se agregan si existe la
carpeta `dbt/models/staging/<dominio>/` o `dbt/models/marts/<dominio>/`
respectivamente — un dominio "solo bronze" (sin contrato ni modelos dbt
todavía, ver el ejemplo `orders` más arriba) obtiene automáticamente un DAG
de una sola fase, sin configuración adicional.

### Bloque opcional `orchestration` en el manifiesto

```yaml
orchestration:
  schedule: null  # cron string, ej. "0 2 * * *"; null = solo trigger manual
```

Mismo principio que `contract`: omitirlo no rompe nada, el DAG queda con
`schedule=None` (disparo manual) y pausado al crearse, para no ejecutar
nada por accidente antes de revisarlo en la UI de Airflow.

### Configuración de infraestructura (Airflow Variables, no en el manifiesto)

La ruta del repo/venv en cada VM y la conexión SSH son infraestructura
compartida por todos los dominios, no contenido de negocio — viven en
Airflow Variables/Connections, no en `sources/<dominio>.yaml`:

| Variable | Default si no está configurada |
| --- | --- |
| `vm01_ssh_conn_id` | `vm01_extraccion` |
| `vm01_project_root` | `/opt/dlt-medallion-pipeline` |
| `vm01_python_bin` | `/opt/dlt-medallion-pipeline/dlt_env/bin/python` |
| `dbt_project_dir` | `<repo_root>/dbt` |
| `dbt_profiles_dir` | igual a `dbt_project_dir` |
| `dbt_bin` | `dbt` |

Los defaults existen para que el parseo del DAG no falle si todavía no se
configuraron en la UI de Airflow (el scheduler reparsea los DAGs
periódicamente) — deben sobrescribirse con los valores reales de cada VM
antes de ejecutar en serio.

## Gaps conocidos

### Una tabla con muchas FKs auto-referenciales no se puede reflejar con SQLAlchemy

Al intentar cargar (con `sql_database()`) una tabla real con ~18 foreign
key constraints, varias de ellas auto-referenciales (columnas de la propia
tabla apuntando a su propia clave primaria), SQLAlchemy falla con:

```text
sqlalchemy.exc.ArgumentError: ForeignKeyConstraint with duplicate source
column references are not supported
```

Esto ocurre incluso reflejando *solo* esa tabla (`MetaData.reflect(only=[...])`),
con `resolve_fks=False`, y con cualquier `reflection_level` de dlt
(`minimal`, `without_primary_key`) — ninguno de esos parámetros desactiva el
parseo de FKs que SQLAlchemy hace internamente al autoload de un `Table()`.
Es un bug/limitación del dialecto MSSQL de SQLAlchemy frente a ese patrón de
esquema puntual, no algo causado por este proyecto. Se confirmó que los
datos sí son legibles con SQL crudo
(`engine.connect().exec_driver_sql("SELECT * FROM <tabla>")`, bypaseando el
autoload de `Table()` por completo).

**Decisión:** excluir esa tabla del manifiesto del dominio afectado por
ahora, en vez de construir un recurso a medida, cuando el dominio todavía
está en fase bronze-only y esa tabla puntual no es indispensable para esa
fase. Si más adelante se necesita, la opción validada es un `@dlt.resource`
propio en `transforms/source_builders/sql.py` (o uno específico del
dominio) que lea la tabla vía `exec_driver_sql` en lugar de pasar por
`table_names` de `sql_database()`.

## Qué pasó con el código anterior

`business_partners_pipeline.py` y `transforms/business_partners_rules.py`
(la primera versión, con las 15 reglas escritas a mano en Python) fueron
reemplazados por `run_pipeline.py` + `contracts/business_partners.json` +
`transforms/domains/business_partners/`. El comportamiento es idéntico —
verificado contra un set de casos de regresión en
`tests/test_business_partners_contract.py` — solo cambió dónde vive cada
pieza.
