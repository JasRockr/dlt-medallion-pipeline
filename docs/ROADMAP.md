# ROADMAP — trabajo pendiente y contexto de continuación

> **Qué es este documento.** El plan completo de lo que falta para que este
> repositorio sea un proyecto de portafolio ejecutable, multi-fuente y
> escalable. Está escrito para **retomarse en otra máquina, en otra sesión,
> sin memoria previa de cómo se llegó hasta acá** — incluyendo sesiones de
> Claude Code arrancando en frío sobre el repo clonado.
>
> Última actualización del estado: **2026-08-29**.

---

## 0. Cómo usar este documento

1. **Es autocontenido a propósito.** El análisis que lo originó comparó este
   repo contra un proyecto laboral privado que **no estará disponible** en la
   máquina personal y **no debe referenciarse ni citarse**. Todos los patrones
   que hay que implementar están descritos acá en forma neutral y completa: no
   hace falta ningún otro repo para ejecutar este plan.
2. **Regla de oro, no negociable:** este repositorio es público/personal. Nunca
   entra un nombre de tabla, esquema, dominio, IP, host, proyecto GCP, cliente
   o razón social provenientes de un entorno laboral. Todo dato es sintético y
   todo nombre es genérico. Ante la duda, el nombre se inventa.
3. **Estructura:** §1 es el estado verificado; §2–§4 son el diseño destino;
   §5 es el backlog ejecutable (fases `F0`–`F6`, ítems `F#.#` referenciables);
   §6–§9 son referencia de apoyo.
4. **Al cerrar un ítem:** marcar su casilla, y actualizar §1 si cambió el
   estado general. Este documento es la fuente de verdad del avance.

---

## 1. Estado actual verificado

Inventario real del repo a la fecha de arriba (verificado, no asumido).

### 1.1 Lo que existe y funciona

| Pieza | Estado |
| --- | --- |
| Motor de reglas declarativo (`transforms/rule_engine.py`) | Completo. 13 operadores, grupos con `stop_on_fail`, estados `OK`/`NO_EVALUADO`/`NO_APLICA`/`ALERTA_CAMPO_NO_DISPONIBLE_EN_ORIGEN`, escape hatch de plugins. Agnóstico de dominio. |
| Contrato de ejemplo (`contracts/business_partners.json`) | 15 campos, 4 grupos, 14 checks, `document_type_dispatch`. |
| Plugins bespoke (`transforms/domains/business_partners/plugins.py`) | Dispatch por tipo de documento + segmentación condicional de nombres. Leen el mapeo desde el contrato, sin duplicarlo en Python. |
| Runner (`run_pipeline.py`) | Genérico, resuelve builder por `source_type`, aplica contrato solo si el manifiesto lo declara ("solo bronze" es válido). |
| Builder SQL (`transforms/source_builders/sql.py`) | `sql_database()` de dlt, agnóstico de motor vía `drivername`. |
| Capa dbt | `staging/` + `marts/` para un dominio, con override de `generate_schema_name` y linaje `source() -> stg -> mart`. |
| DAG factory (`airflow/dags/medallion_dag_factory.py`) | Un DAG por manifiesto, fases derivadas de la existencia de carpetas dbt. No hay DAGs escritos a mano. |
| Stack Airflow (`docker-compose.yml` + `Dockerfile`) | LocalExecutor + Postgres + venv aislado para dbt + provider SSH. |
| Tests | **62 pruebas, todas pasan en ~0.35 s**, sin credenciales ni red (`python -m pytest`). |
| Documentación | ~1.600 líneas en 5 documentos (`ARCHITECTURE`, `COMMANDS-PIPELINE`, `CHEATSHEET`, `REGLAS-NEGOCIO`, `DEPLOYMENT`) + README con mapa de navegación. |

### 1.2 Higiene de des-corporatización: verificada limpia

Se barrió el repo buscando identificadores del entorno laboral de origen
(nombres de empresa/producto, dominios de negocio del ERP original, rutas de
servidores, IPs, project IDs, correos, nombres de usuario):

- **0 coincidencias en los 44 archivos versionados.**
- Los únicos matches aparecen en `__pycache__/*.pyc` y `.pytest_cache/`, que
  llevan embebida la ruta absoluta de compilación del equipo actual. Ambos
  están en `.gitignore` y **no están versionados**. Nada que hacer, salvo no
  versionarlos nunca.
- La abstracción es estructural, no un buscar/reemplazar: el submodelo
  `business_partners` + 15 catálogos es coherente de punta a punta (DBML →
  contrato → manifiesto → staging → mart), y los documentos declaran de forma
  explícita que el esquema y las reglas son ilustrativos.

### 1.3 Lo que falta o está flojo (resumen; el detalle es el backlog de §5)

1. **No se puede ejecutar.** Requiere MSSQL real + BigQuery + ADC.
   `run_pipeline.py` tiene `destination="bigquery"` fijo. Un revisor no puede
   clonar y correr nada más allá de los tests unitarios. *Este es el hueco más
   grande del proyecto como pieza de portafolio.*
2. **Una sola fuente.** El README y `ARCHITECTURE.md` prometen "runner
   multi-fuente", pero no hay ninguna estructura que lo demuestre: un solo
   manifiesto, un solo motor, una sola sección de credenciales.
3. **`write_disposition` global por dominio**, no por tabla. Hoy se pasa un
   único valor a `pipeline.run()`. Sin `merge` por clave primaria ni `append`.
4. **Sin control de frecuencia de sincronización.** Todo dominio se corre
   entero, siempre. No hay forma de correr solo las tablas calientes.
5. **Un gap de robustez documentado pero no resuelto**
   (`ARCHITECTURE.md`, "Gaps conocidos"): las tablas con muchas FKs
   auto-referenciales no se pueden reflejar con SQLAlchemy y hoy la decisión es
   *excluirlas del manifiesto*. Es la debilidad más visible del repo para un
   lector técnico. Hay solución conocida (§5, F5).
6. **Sin CI, sin lint configurado, sin licencia.** `ruff check --select E,F
   --line-length 110` reporta **11 hallazgos** (E501 y orden de imports),
   todos triviales. Un solo commit squash, sin remoto.
7. **Residuos menores de nomenclatura y consistencia** (F0.4, F0.5).

---

## 2. Objetivo del rediseño

Al terminar este roadmap, el repo debe cumplir estas cinco afirmaciones, todas
verificables por un tercero sin acceso a nada privado:

1. **Se clona y se corre en dos comandos**, sin cuenta de nube, sin base de
   datos externa, sin credenciales. Medallion completo (bronze → silver → gold)
   sobre DuckDB local, con datos sintéticos deterministas.
2. **Es multi-fuente de verdad**: dos motores de base de datos distintos
   (SQL Server y PostgreSQL), levantados en contenedores, con manifiestos
   agrupados por fuente y **una colisión de nombres deliberada** entre ambas
   para que la separación por fuente tenga una razón demostrable y no teórica.
3. **La estrategia de carga se decide por tabla, no por dominio**
   (`replace` / `merge` con PK / `append`), declarada en el manifiesto y
   validada antes de correr.
4. **La cadencia se decide por tabla** (`high` / `daily` / `weekly`), y Airflow
   genera un DAG por combinación fuente × dominio × frecuencia, con su cron,
   sin escribir DAGs a mano.
5. **Es robusto ante esquemas hostiles**: tablas irreflexionables por bugs de
   FK y columnas con valores outlier tienen mitigación declarativa, sin
   hardcodear nombres de tabla en el código del motor.

Y como consecuencia transversal: **CI en verde** que corre lint, tests,
validación de manifiestos y un end-to-end real contra las bases de prueba.

---

## 3. Arquitectura destino (árbol de carpetas)

```text
contracts/<fuente>/<dominio>.json          # contrato declarativo (opcional por dominio)
sources/<fuente>/<dominio>.yaml            # manifiestos, agrupados POR FUENTE
transforms/
  rule_engine.py                           # motor genérico (no se toca por reglas de negocio)
  contract_utils.py                        # resolución de alias / fail-fast de columnas
  bigquery_gold.py                         # helper de vistas gold (solo destino BigQuery)
  source_builders/
    sql.py                                 # MSSQL/PostgreSQL/MySQL vía SQLAlchemy
  domains/<fuente>/<dominio>/
    plugins.py                             # lógica bespoke por dominio
    views.py                               # SQL de vistas gold de ese dominio
run_pipeline.py                            # runner único: --manifest, --frequency
scripts/
  validar_manifiestos.py                   # validación estructural (corre en CI)
  diagnostico_reflexion.py                 # aísla qué tabla dispara el bug de reflexión de FKs
  smoke_test_connection.py                 # conectividad de una fuente
demo/
  docker-compose.demo.yml                  # SQL Server + PostgreSQL de prueba
  seed.py                                  # generador de datos sintéticos deterministas
  schemas/erp_mssql.sql                    # DDL fuente A
  schemas/crm_postgres.sql                 # DDL fuente B
  run_demo.py                              # orquestador del demo (cross-platform, sin make)
dbt/
  dbt_project.yml                          # perfiles: demo (duckdb) | dev (bigquery)
  macros/
    generate_schema_name.sql
    countif.sql                            # compatibilidad BigQuery <-> DuckDB
  models/staging/<fuente>/<dominio>/
  models/marts/<fuente>/<dominio>/
airflow/dags/medallion_dag_factory.py      # un DAG por fuente x dominio x frecuencia
tests/                                     # motor, plugins, contrato, manifiestos, selección por frecuencia
.github/workflows/ci.yml                   # lint + tests + validación + E2E demo
```

**Consecuencia importante de la colisión deliberada:** como las dos fuentes van
a tener un dominio con el mismo nombre, `contracts/`, `transforms/domains/` y
`dbt/models/**/` **tienen que llevar el nivel de fuente**. No es simetría
decorativa: sin ese nivel, los plugins y los modelos de un dominio pisarían a
los del otro.

---

## 4. Especificación del manifiesto destino

El manifiesto es el contrato entre todas las piezas (runner, validador, DAG
factory, dbt). Esta es la forma final a la que apuntan todas las fases; los
bloques nuevos se van agregando fase por fase, sin romper los manifiestos que
todavía no los declaren (**todo bloque nuevo es opcional y tiene default**).

```yaml
# sources/<fuente>/<dominio>.yaml
source: erp_mssql                  # DEBE coincidir con el nombre de la carpeta contenedora
domain: business_partners
source_type: sql                   # ver SOURCE_BUILDERS en run_pipeline.py
credentials_section: sources.erp_mssql.credentials

tables:
  - countries
  - business_partners

# --- Opcional: motor de reglas. Sin estas dos claves el dominio es "solo bronze". ---
contract: contracts/erp_mssql/business_partners.json
rule_target_table: business_partners

# --- Opcional (F4): cadencia por tabla. Lo no declarado cae a 'weekly'. ---
frequencies:
  high:  [business_partners]
  daily: []

# --- Opcional (F3): estrategia de carga por tabla. El resto usa destination.write_disposition. ---
merge_tables:
  business_partners: [partner_id]   # clave primaria real, verificada contra el esquema
append_tables: []                   # solo bitácoras genuinamente insert-only

# --- Opcional (F5): mitigaciones de esquemas hostiles, declarativas. ---
manual_reflection_tables: []        # tablas que revientan la reflexión de FKs de SQLAlchemy
column_truncation: {}               # {tabla: {columna: max_caracteres}}

# --- Opcional (F5): backend de extracción de dlt. ---
extraction:
  backend: pyarrow                  # default; se degrada a sqlalchemy si hay rule_target_table

destination:
  type: duckdb                      # duckdb | bigquery  (F1)
  dataset: src                      # capa, no dominio   (F2.4)
  table_prefix: src_erp_            # evita colisiones entre fuentes dentro del dataset
  write_disposition: replace        # default para tablas fuera de merge_tables/append_tables

# --- Opcional: vistas gold dinámicas (solo destino BigQuery). ---
gold_views: [resumen_ejecucion_business_partners]

# --- Opcional (F4): cron por frecuencia. Lo no declarado queda en disparo manual. ---
orchestration:
  schedules:
    high:   "0 * * * *"
    daily:  "0 3 * * *"
    weekly: "0 4 * * 1"
```

---

## 5. Backlog

Fases ordenadas por dependencia. Dentro de una fase, los ítems se pueden hacer
en cualquier orden salvo que se indique.

---

### F0 — Higiene de portafolio *(rápido, alto retorno visible)*

Nada acá cambia la arquitectura; todo se nota desde afuera del repo.

- [x] **F0.1 — Licencia y metadatos.** Agregar `LICENSE` (MIT), y al README un
      bloque de badges (CI, licencia, Python) y una línea de una frase que diga
      qué es el proyecto antes del primer párrafo.
      *Aceptación:* GitHub muestra la licencia detectada en la barra lateral.
      *Cerrado 2026-08-29:* `LICENSE` (MIT, Json Rivera) agregado. Badges de
      licencia y Python 3.12+ agregados; el badge de CI queda pendiente de
      F0.3 porque hoy no existe workflow de CI (el repo ya tiene remoto en
      `github.com/JasRockr/dlt-medallion-pipeline`).

- [x] **F0.2 — Configuración de lint.** Crear `pyproject.toml` con ruff:
      `line-length = 110` y `select = ["E", "F"]` — selección conservadora y
      explícita a propósito: errores reales (imports rotos, nombres no
      definidos, sintaxis), no preferencias de estilo. Sin fijarlo, ruff activa
      un set amplio por defecto que cambia entre versiones sin aviso.
      Corregir los **11 hallazgos actuales** (E501 en tests y en el runner,
      orden de imports por el `load_dotenv()` temprano — usar `# noqa: E402`
      con comentario explicando por qué el import va después de la carga del
      `.env`, en vez de reordenar y romper la carga).
      *Aceptación:* `ruff check .` sale limpio.
      *Cerrado 2026-08-29:* `pyproject.toml` con la config indicada. Import
      sin usar (`Optional`) eliminado en la DAG factory; los 8 E402 de
      `run_pipeline.py` y `smoke_test_connection.py` con `# noqa: E402` y
      comentario explicando el porqué; las 2 líneas largas de los tests
      partidas. `ruff check .` sale limpio y los 62 tests siguen en verde.

- [x] **F0.3 — CI mínimo** (`.github/workflows/ci.yml`), tres jobs:
      `lint` (ruff), `tests` (pytest), `validate-manifests` (F2.5, cuando
      exista; hasta entonces omitir el job).
      *Aceptación:* PR contra `main` dispara los jobs y quedan en verde.
      *Cerrado 2026-08-29:* jobs `lint` y `tests` agregados; `validate-manifests`
      omitido con comentario explícito, tal como pide el ítem. `ruff` agregado
      (pineado) a `requirements-dev.txt` — no estaba declarado en ningún
      requirements pese a que `CLAUDE.md` y este roadmap ya instruían correrlo.
      Los comandos exactos del workflow se corrieron en local con los mismos
      resultados (`ruff check .` limpio, 62 tests en verde), y la primera
      corrida real en GitHub Actions tras el push quedó en verde.

- [x] **F0.4 — Residuos de nomenclatura heredada.** En
      `airflow/dags/medallion_dag_factory.py`, los defaults de las Airflow
      Variables `vm01_project_root` / `vm01_python_bin` apuntan a una ruta con
      nombre heredado de un sandbox anterior (`/opt/test-dlt-py`). Cambiar a
      `/opt/dlt-medallion-pipeline` y su venv. Revisar de paso que
      `_build_extract_task()` no reciba parámetros que no usa.
      *Aceptación:* `grep -ri "test-dlt-py" .` no devuelve nada.
      *Cerrado 2026-08-29:* ambos defaults actualizados a
      `/opt/dlt-medallion-pipeline`. `_build_extract_task()` recibía `domain`
      sin usarlo en el cuerpo de la función; parámetro y argumento en el
      call site eliminados. `ruff check .` limpio, 62 tests en verde. El
      grep de aceptación ya no encuentra la cadena en código; las dos
      coincidencias que quedan son la descripción de este mismo ítem en el
      roadmap, no una referencia viva.

- [x] **F0.5 — Consistencia de la capa dbt.** El manifiesto extrae 16 tablas
      pero `dbt/models/staging/business_partners/_business_partners__sources.yml`
      declara 15: falta `accounts`. Decidir y dejar escrito **una** de las dos:
      declararla como source aunque no se use en ningún join, o dejar un
      comentario explícito de por qué se extrae a bronze y no se declara.
      *Aceptación:* el conteo de tablas del manifiesto y el de `sources.yml`
      coinciden, o hay un comentario que justifica la diferencia.
      *Cerrado 2026-08-30:* `accounts` **sí** se usaba ya en el staging
      (`bp.account_id`, sin enriquecer porque el catálogo no tiene columna
      descriptiva — eso ya estaba documentado en el `.sql`); lo que faltaba
      era declararla como `source()` en `sources.yml`, que es lo que
      determina el lineage bronze visible en la documentación de dbt.
      Se declaró con una descripción que remite al porqué no participa del
      join de enriquecimiento. Conteo 16/16 verificado; YAML válido; 62
      tests en verde.

- [ ] **F0.6 — Reencuadre narrativo.** Varios documentos hablan del proyecto
      como si fuera un encargo interno: "migrar a producción (Workspace
      corporativo)", "LAN corporativa", "el SQL Server real"
      (`docs/COMMANDS-PIPELINE.md` §421, `docs/DEPLOYMENT.md` líneas 85, 198,
      315). No es fuga de datos, pero cuenta la historia equivocada para un
      portafolio. Reescribir esos pasajes en clave de proyecto propio: "cómo se
      llevaría este diseño a un entorno productivo con red privada", en
      condicional y sin dueño implícito.
      *Aceptación:* `grep -rniE "corporativ|el SQL Server real" docs/` no
      devuelve nada que implique un empleador.

---

### F1 — Entorno demo ejecutable *(la fase de mayor retorno del roadmap)*

Objetivo: `git clone` → dos comandos → medallion completo corriendo local, con
resultados visibles. Sin nube, sin credenciales.

- [ ] **F1.1 — Destino configurable.** `run_pipeline.py` tiene
      `destination="bigquery"` fijo. Leerlo de `destination.type` del
      manifiesto (`duckdb` | `bigquery`), con default `bigquery` para no romper
      los manifiestos existentes. Para DuckDB, fijar la ruta del archivo
      (`demo/warehouse.duckdb`) desde el manifiesto o una variable de entorno.
      Agregar `dlt[duckdb]` a `requirements.txt`.
      *Trampa:* `gold_views` y `transforms/bigquery_gold.py` usan sintaxis y
      cliente de BigQuery. Con destino DuckDB, el runner debe **saltarse** el
      bloque `gold_views` con un warning explícito, no fallar. La cobertura
      gold en modo demo la da el modelo `marts/` de dbt, que es el reemplazo
      previsto de esas vistas de todos modos.
      *Aceptación:* `python run_pipeline.py --manifest <m>` con
      `type: duckdb` escribe tablas consultables en el archivo DuckDB.

- [ ] **F1.2 — Dos bases de datos de prueba en contenedores.**
      `demo/docker-compose.demo.yml` con:
      - **Fuente A — `erp_mssql`**: `mcr.microsoft.com/mssql/server:2022-latest`.
        Se elige SQL Server a propósito: mantiene vivo el camino `pyodbc` que el
        proyecto documenta, y **es el dialecto donde se reproduce el bug de
        reflexión de FKs** de F5 — sin esta fuente, ese trabajo no se puede
        demostrar. Requiere ~2 GB de RAM; documentarlo.
      - **Fuente B — `crm_postgres`**: `postgres:16-alpine`. Motor distinto,
        driver distinto (`psycopg2`), para probar que el builder SQL es
        realmente agnóstico. Agregar `psycopg2-binary` a `requirements.txt`.
      Healthchecks en ambos servicios, puertos no estándar en el host
      (ej. 14330 y 54320) para no chocar con instalaciones locales.
      *Aceptación:* `docker compose -f demo/docker-compose.demo.yml up -d` deja
      ambos servicios `healthy`.

- [ ] **F1.3 — Esquemas y datos sintéticos deterministas.**
      `demo/schemas/*.sql` con el DDL de cada fuente, y `demo/seed.py` que puebla
      ambas con **semilla fija** (mismos datos en cada corrida, en cualquier
      máquina). El generador debe emitir a propósito filas sucias que ejerciten
      cada estado del motor de reglas: documentos con formato inválido, nombres
      de prueba, correos con dominio mal escrito, celulares con caracteres,
      organizaciones sin segmentación de nombre (para que salga `NO_APLICA`), y
      al menos un campo declarado `available_in_source: false` para que aparezca
      `ALERTA`. Volumen sugerido: 5.000 filas en la tabla central, cientos en
      catálogos — suficiente para que el reporte gold tenga distribución
      interesante y rápido de sembrar.
      *Aceptación:* dos corridas de `seed.py` producen datos idénticos; el
      reporte gold muestra filas en `OK`, `ERROR` y `ALERTA`.

- [ ] **F1.4 — dbt sobre DuckDB.** Agregar `dbt-duckdb` a
      `requirements-dbt.txt` y un target `demo` en `profiles.yml.example`
      apuntando al mismo archivo `.duckdb` que escribe dlt.
      *Trampas concretas, ya identificadas:*
      - El modelo de staging usa `partition_by` / `cluster_by`, que son
        configuraciones exclusivas de BigQuery. Moverlas a un bloque
        condicional por `target.type`.
      - Los modelos usan `countif()`, que **no existe en DuckDB**. Crear
        `dbt/macros/countif.sql` que resuelva a `countif(...)` en BigQuery y a
        `sum(case when ... then 1 else 0 end)` en el resto, y reemplazar los
        usos en el modelo de staging y en el mart.
      - Con `table_prefix` (F2.4), las `sources.yml` de dbt necesitan
        `identifier:` explícito por tabla — el nombre lógico del source ya no
        coincide con el nombre físico en el warehouse.
      *Aceptación:* `dbt build --target demo` corre staging + marts sobre
      DuckDB sin tocar BigQuery.

- [ ] **F1.5 — Orquestador del demo, cross-platform.** `demo/run_demo.py`
      (Python, **no Makefile**: el entorno de desarrollo principal es Windows)
      con subcomandos `up`, `seed`, `ingest`, `transform`, `report`, `down`, y
      un `all` que los encadena. `report` debe imprimir en consola un resumen
      legible del mart (conteos por estado de validación) — el "resultado
      visible" que justifica todo el demo.
      *Aceptación:* `python demo/run_demo.py all` termina imprimiendo el
      reporte, partiendo de un repo recién clonado.

- [ ] **F1.6 — Documentar el demo primero.** Mover el Quickstart del README al
      camino DuckDB, y bajar el camino MSSQL/BigQuery a "modo producción". Lo
      primero que ve un visitante tiene que ser algo que puede correr.
      *Aceptación:* el README arranca con un quickstart que no menciona ninguna
      credencial de nube.

---

### F2 — Multi-fuente

Con las dos bases de F1 en pie, esto deja de ser una promesa del README.

- [ ] **F2.1 — Clave `source` y layout por fuente.** Mover los manifiestos a
      `sources/<fuente>/<dominio>.yaml` y agregar la clave `source:` a cada uno.
      Regla: **el valor de `source` debe coincidir con el nombre de la carpeta
      contenedora**, y el validador lo verifica (F2.5).
      Reubicar en paralelo `contracts/<fuente>/`, `transforms/domains/<fuente>/`
      y `dbt/models/{staging,marts}/<fuente>/`, actualizando las referencias
      `"plugin": "transforms.domains.<fuente>.<dominio>.plugins:<func>"` dentro
      del contrato y la ruta `_CONTRACT_PATH` de `plugins.py`.

- [ ] **F2.2 — `pipeline_name` con la fuente.** El nombre del pipeline de dlt
      debe incluir la fuente, no solo el dominio:
      `f"{source}_{domain}_pipeline_to_{dataset}"`. **Motivo concreto:** dlt
      guarda el estado de cada pipeline en un directorio derivado de ese nombre;
      dos fuentes con un dominio homónimo compartirían estado y se corromperían
      mutuamente. Este es exactamente el escenario que F2.3 construye a
      propósito.

- [ ] **F2.3 — La colisión deliberada.** Crear tres manifiestos:
      1. `sources/erp_mssql/business_partners.yaml` — el dominio insignia: con
         contrato, motor de reglas, staging y mart. Es el actual, migrado.
      2. `sources/crm_postgres/sales_orders.yaml` — dominio de escala, **solo
         bronze** (sin contrato): un fact (`orders`) con descendientes
         (`order_items`, `order_events`) más catálogos. Es el que justifica
         `merge_tables` / `append_tables` (F3) y `frequencies` (F4).
      3. `sources/crm_postgres/business_partners.yaml` — dominio mínimo (2–3
         tablas, solo bronze) que **existe únicamente para colisionar en nombre
         con el de la fuente A**. Documentarlo así en un comentario del propio
         manifiesto: es una prueba viva de por qué la carpeta por fuente, el
         `pipeline_name` con prefijo y el `table_prefix` existen. Sin él, la
         separación por fuente es una afirmación sin evidencia.
      *Aceptación:* los tres pipelines corren en la misma sesión de demo y
      aterrizan sin pisarse, con estado dlt separado.

- [ ] **F2.4 — Nomenclatura de datasets por capa, no por dominio.** Hoy cada
      dominio tiene su propio dataset (`business_partners_data`,
      `staging_business_partners`, `curated_business_partners`). Con dos fuentes
      y varios dominios eso explota en fuentes × dominios × capas datasets.
      Migrar a **un dataset por capa** — `src` / `stg` / `cur` — con las tablas
      diferenciadas por prefijo dentro: `{capa}_{fuente}_{objeto}`
      (`src_erp_business_partners`, `src_crm_orders`). El runner aplica el
      prefijo asignando `resource.table_name` antes de correr.
      *Alcance del cambio:* `run_pipeline.py`, los tres manifiestos, `+schema`
      en `dbt_project.yml`, las `sources.yml` (con `identifier:`, ver F1.4), el
      SQL de la vista gold dinámica, y las menciones de dataset en
      `docs/REGLAS-NEGOCIO.md` §"Cobertura Operativa Actual" y en
      `docs/ARCHITECTURE.md` §"Capa de transformación".

- [ ] **F2.5 — Validador de manifiestos** (`scripts/validar_manifiestos.py`).
      Recorre `sources/**/*.yaml` sin necesitar credenciales ni red, y verifica:
      YAML válido y mapeo en la raíz; claves requeridas (`source`, `domain`,
      `source_type`, `credentials_section`, `tables`, `destination`); `tables`
      lista no vacía; `destination.dataset` y `destination.write_disposition`
      presentes; `contract` y `rule_target_table` siempre juntos; `source` ==
      nombre de la carpeta; que el archivo de contrato referenciado exista y sea
      JSON válido; y las validaciones de F3.3 y F4.3. Sale con código 1 si algo
      falla, imprimiendo `OK`/`FALLA` por manifiesto.
      *Aceptación:* job `validate-manifests` en CI; un manifiesto roto a
      propósito tumba el job.

- [ ] **F2.6 — DAG factory multi-fuente.** Cambiar el `glob("*.yaml")` por
      `rglob`, y el `dag_id` a `<fuente>__<dominio>`. Las rutas de modelos dbt
      que la factory verifica pasan a `models/staging/<fuente>/<dominio>/`.
      *Aceptación:* la factory genera un DAG por manifiesto sin colisión de
      `dag_id`.

- [ ] **F2.7 — Credenciales por fuente.** `.dlt/secrets.toml.example` con una
      sección por fuente (`[sources.erp_mssql.credentials]`,
      `[sources.crm_postgres.credentials]`), cada una con su `drivername`. El
      demo debe poder inyectarlas por variables de entorno (dlt las resuelve
      desde el entorno) para que `run_demo.py` no obligue a editar archivos.

---

### F3 — Estrategia de carga por tabla

- [ ] **F3.1 — Hints por recurso.** Reemplazar el `write_disposition` global de
      `pipeline.run()` por hints aplicados recurso por recurso antes de correr:
      las tablas en `merge_tables` van a `merge` con su `primary_key`; las de
      `append_tables` a `append`; el resto al `destination.write_disposition`.
      *Marco de decisión, para dejarlo escrito en la documentación:*

      | Estrategia | Cuándo | Por qué |
      | --- | --- | --- |
      | `replace` | Catálogos y maestros de bajo volumen | Recarga completa barata a esa escala; sin lógica de deduplicación innecesaria. |
      | `merge` | Facts y descendientes transaccionales | Alto volumen y filas que se actualizan; `replace` sería caro y `append` duplicaría. Exige clave confiable. |
      | `append` | Bitácoras genuinamente insert-only | Solo si se confirma que las filas nunca se editan ni se borran; si no, deja duplicados silenciosos. Es candidato, nunca default. |

- [ ] **F3.2 — Documentar el comportamiento no obvio de `merge`.**
      `merge` inserta y actualiza por clave primaria, pero **nunca borra del
      destino una fila que desapareció de la fuente**. A diferencia de
      `replace`, una tabla en `merge` es la unión acumulada de todo lo que se
      extrajo alguna vez, no una foto del estado presente. Consecuencias que
      deben quedar escritas en `docs/ARCHITECTURE.md`:
      - Ningún modelo silver/gold puede tratar una tabla bronze en `merge` como
        "el estado vigente" sin un criterio explícito de vigencia.
      - Auditar una tabla en `merge` **no** se hace comparando conteos totales
        contra la fuente (un conteo mayor es esperado y correcto), sino
        agrupando por la clave primaria y buscando `HAVING COUNT(*) > 1`.
      El demo es el lugar ideal para demostrarlo: sembrar, correr, borrar filas
      en la fuente, correr de nuevo, y mostrar la diferencia entre una tabla en
      `merge` y una en `replace`.

- [ ] **F3.3 — Validaciones.** Tanto en el runner (falla temprano) como en el
      validador de F2.5: una tabla no puede estar en `merge_tables` y
      `append_tables` a la vez (son mutuamente excluyentes); toda tabla
      declarada en cualquiera de las dos listas debe existir en `tables` (si no,
      la entrada nunca se aplica y es un error silencioso); `merge_tables.<t>`
      debe ser una lista de columnas no vacía.

- [ ] **F3.4 — Tests.** Unitarios, sin base de datos: dado un manifiesto y una
      lista de recursos simulados, verificar que a cada recurso se le aplicó el
      hint correcto, y que las combinaciones inválidas levantan error.

---

### F4 — Frecuencia de sincronización

- [ ] **F4.1 — Bloque `frequencies` y flag `--frequency`.** Frecuencias
      soportadas: `high`, `daily`, `weekly`, declaradas en una constante única
      del runner que el validador reutiliza. `run_pipeline.py --frequency daily`
      corre solo esas tablas (`source.with_resources(...)`); sin el flag, corre
      todas. **Las tablas sin frecuencia explícita caen a `weekly`** — así un
      manifiesto sin el bloque sigue funcionando igual que hoy.

- [ ] **F4.2 — Mensaje de error útil.** Si se pide una frecuencia sin tablas en
      ese manifiesto, el error debe listar las frecuencias disponibles con su
      conteo de tablas y recordar la regla del default `weekly`. Un error de
      CLI que solo dice "no hay tablas" obliga a abrir el YAML.

- [ ] **F4.3 — Validaciones.** Frecuencia desconocida; una tabla en más de una
      frecuencia; una tabla declarada en `frequencies` que no está en `tables`.
      Las mismas reglas en el runner y en el validador.

- [ ] **F4.4 — DAG por frecuencia** *(esto no existe en ningún otro lado; es el
      diferenciador de este repo).* La DAG factory genera **un DAG por cada
      combinación fuente × dominio × frecuencia declarada**, con `dag_id`
      `<fuente>__<dominio>__<frecuencia>`, el cron de
      `orchestration.schedules.<frecuencia>` y la tarea de extracción llamando
      al runner con `--frequency <frecuencia>`. Un dominio sin bloque
      `frequencies` sigue produciendo un único DAG que corre todo.
      *Decisión de diseño a documentar:* las fases dbt (staging/marts) se
      enganchan solo al DAG de la frecuencia **más alta** declarada, para no
      recalcular la capa silver tres veces al día por tablas que no cambiaron.
      Si se prefiere lo contrario, dejar escrito por qué.

- [ ] **F4.5 — Tarea de extracción local para el demo.** Hoy la extracción se
      dispara siempre por `SSHOperator` contra una VM remota. En modo demo eso
      no aplica: elegir `BashOperator` local o `SSHOperator` según una Airflow
      Variable (`execution_mode = local | remote`), con default `local`.
      *Aceptación:* `docker compose up` + abrir Airflow muestra los DAGs
      generados y uno de ellos corre end-to-end contra las bases del demo.

- [ ] **F4.6 — Tests.** Selección de tablas por frecuencia, incluido el
      fallback a `weekly` y los tres casos de validación de F4.3.

---

### F5 — Robustez ante esquemas hostiles

Cierra el gap declarado hoy en `ARCHITECTURE.md` §"Gaps conocidos". Es la fase
que convierte un "no lo resolví" en un "lo resolví y sé por qué el mecanismo es
frágil" — narrativamente, la más valiosa del roadmap después de F1.

- [ ] **F5.1 — Reflexión manual de columnas.** Para las tablas listadas en
      `manual_reflection_tables` del manifiesto, no usar el camino normal de
      `sql_database()`. En su lugar: construir un `MetaData` propio y una
      `Table` **solo con columnas** obtenidas vía `Inspector.get_columns()`
      (que no toca constraints de FK, así que nunca dispara el bug), y pasar ese
      `MetaData` ya poblado a `sql_table()`.
      *Por qué funciona:* si el `MetaData` que recibe ya contiene una `Table`
      con ese nombre, dlt se salta el autoload que es justamente el que
      revienta. **Esto es un detalle interno no documentado de la librería, no
      un contrato público de su API.** Consecuencias obligatorias:
      - Pinear la versión exacta de `dlt` en `requirements.txt`, con un
        comentario que diga que el pineo existe por esto.
      - Envolver el llamado en `try/except ArgumentError` y relanzar un error
        que explique que el workaround dejó de funcionar y apunte al fallback.
      - Documentar el fallback ya conocido: un `@dlt.resource` propio que lea
        con SQL crudo (`exec_driver_sql`), convirtiendo cada fila a `dict`
        (el `RowMapping` de SQLAlchemy no es serializable por el JSON de dlt).
        Se pierde la inferencia de tipos y el soporte de incrementales.
      *Diferencia deliberada con el enfoque de referencia:* la lista de tablas
      afectadas **va en el manifiesto, no en un `set` del módulo**. Hardcodearla
      en `sql.py` viola el principio de que el motor no conoce dominios, y en
      este repo además sería un vector de fuga de nombres.

- [ ] **F5.2 — Reproducir el bug en el demo.** En el DDL de la fuente A
      (SQL Server), incluir a propósito una tabla con muchas FKs, varias
      auto-referenciales, que dispare
      `ArgumentError: ForeignKeyConstraint with duplicate source column
      references are not supported`. Declararla en `manual_reflection_tables` y
      dejar en la documentación el antes/después.
      *Sin esto, F5.1 es código sin evidencia.* Verificar primero que el patrón
      efectivamente reproduce el error en el contenedor; si no se logra,
      registrar el intento y dejar F5.1 documentado como mitigación defensiva.

- [ ] **F5.3 — Truncado de columnas outlier.** Bloque `column_truncation`
      (`{tabla: {columna: max_caracteres}}`): construye el recurso con SQL crudo
      y un `CASE WHEN LEN(col) > N THEN LEFT(col, N-3) + '...' ELSE col END`,
      de modo que **sea evidente que el valor fue cortado** y no que el dato
      terminaba ahí. Motivación real: columnas de texto libre con valores de
      megabytes (HTML, payloads) que hacen fallar la carga en el destino.
      Sembrar en el demo un par de filas con esa forma para demostrarlo.
      *Nota:* el SQL de truncado es dependiente del dialecto (`LEN`/`LEFT` en
      SQL Server, `LENGTH`/`LEFT` en PostgreSQL). Resolverlo por dialecto o
      documentar la limitación explícitamente.

- [ ] **F5.4 — Backend de extracción `pyarrow`, con cuidado.** El backend por
      defecto de dlt arma un `dict` de Python por fila, que es el camino más
      lento a volumen; `pyarrow` procesa por lotes en formato columnar y es
      sensiblemente más rápido en las fases de normalizado y carga.
      **⚠ Incompatibilidad crítica, no obvia:** con backend `pyarrow` el recurso
      emite tablas de Arrow por lote, **no filas `dict`**. El motor de reglas se
      engancha con `add_map()` esperando un `dict` por fila — activar `pyarrow`
      globalmente **rompe el motor de reglas en silencio o con un error críptico
      de tipos**. La implementación correcta es **por recurso**: `pyarrow` para
      las tablas sin reglas, backend por defecto para `rule_target_table`. El
      runner debe forzar esa degradación automáticamente cuando el manifiesto
      declara `rule_target_table`, y dejarlo dicho en un comentario.
      *Aceptación:* un dominio con contrato y `backend: pyarrow` declarado corre
      igual que antes, con las columnas de validación presentes, y loguea que
      degradó el backend para la tabla de reglas.
      *Advertencia honesta a documentar:* si el cuello de botella real está del
      lado del motor origen (bloqueos, falta de índices), este cambio no ayuda.
      Confirmar con el desglose por fase de una corrida real antes de afirmar
      que resolvió algo.

- [ ] **F5.5 — Script de diagnóstico** (`scripts/diagnostico_reflexion.py`).
      Cuando la reflexión masiva falla, el error no dice **cuál** tabla la
      disparó. Este script reflexiona tabla por tabla contra una fuente y
      reporta cuáles fallan y con qué error. Solo lectura, no extrae datos.
      Documentarlo en el CHEATSHEET como primer paso de diagnóstico ante un
      fallo de reflexión.

---

### F6 — Documentación y narrativa

- [ ] **F6.1 — Actualizar `docs/ARCHITECTURE.md`**: secciones nuevas de
      multi-fuente, estrategia de carga por tabla, frecuencias, y mitigaciones
      de esquemas hostiles. Retirar el gap de reflexión de "Gaps conocidos" y
      reemplazarlo por la sección de mitigación (con el fallback documentado).

- [ ] **F6.2 — `docs/DECISIONES.md` (ADR ligero).** Una entrada por decisión no
      obvia, con contexto / opciones / decisión / consecuencias / cuándo
      revisarla. Candidatas iniciales: dataset por capa vs. por dominio;
      `merge` no espeja borrados; backend `pyarrow` incompatible con el motor de
      reglas; mitigaciones declarativas en el manifiesto en vez de listas en
      código; DuckDB como destino de demostración; frecuencias en el manifiesto
      en vez de en el cron.
      *Es la pieza que más diferencia un portafolio de un tutorial:* muestra
      criterio, no solo ejecución.

- [ ] **F6.3 — Diagrama de arquitectura** en el README (Mermaid, que GitHub
      renderiza nativo): las dos fuentes → dlt → bronze → dbt → silver/gold, con
      Airflow orquestando y el motor de reglas actuando en el punto de carga.

- [ ] **F6.4 — Actualizar `CHEATSHEET.md` y `COMMANDS-PIPELINE.md`** con los
      comandos nuevos (`--frequency`, `run_demo.py`, validador, diagnóstico).

- [ ] **F6.5 — Sección "Qué demuestra este proyecto"** en el README: 6–8 puntos
      concretos, cada uno enlazando al archivo que lo evidencia. Es lo que
      alguien lee en 60 segundos antes de decidir si abre el código.

---

## 6. Trampas conocidas (catálogo de referencia rápida)

Ordenadas por probabilidad de costar una tarde:

1. **`pyarrow` + `add_map` no conviven** (F5.4). Es la más cara: falla lejos del
   cambio que la causó.
2. **`merge` no borra** (F3.2). Lleva a métricas silenciosamente infladas en
   silver/gold, sin ningún error visible.
3. **El workaround de reflexión depende de un detalle interno de dlt** (F5.1).
   Un `pip install --upgrade` puede romperlo sin aviso. De ahí el pineo.
4. **`countif` y `partition_by` son de BigQuery** (F1.4). Rompen dbt sobre
   DuckDB de formas poco descriptivas.
5. **`table_prefix` desacopla el nombre lógico del físico** (F1.4/F2.4). Las
   `sources.yml` de dbt necesitan `identifier:` explícito o no encuentran nada.
6. **Colisión de estado de dlt entre fuentes homónimas** (F2.2). No da error:
   da resultados incorrectos.
7. **`RowMapping` no es serializable** por el JSON de dlt. Al construir recursos
   con SQL crudo, convertir cada fila a `dict` explícitamente.
8. **La imagen de SQL Server pide ~2 GB de RAM.** En equipos ajustados o en CI
   puede ser el motivo real de un fallo intermitente.
9. **`load_dotenv()` antes de los imports de dlt** es intencional (dlt lee
   configuración en tiempo de import). Reordenar los imports para contentar al
   linter rompe la carga: usar `# noqa: E402` con comentario.

---

## 7. Fuera de alcance (decidido, no pendiente)

Escrito para que ninguna sesión futura lo reabra por inercia:

- **No** construir un motor de validación universal que infiera reglas solo. Si
  el catálogo de operadores declarativos se queda corto, la respuesta correcta
  es adoptar una herramienta madura (Great Expectations, Soda, los tests de
  dbt), no agrandar esta.
- **No** Celery/Redis en Airflow: LocalExecutor sobra para este volumen.
- **No** CDC ni replicación en tiempo real: el proyecto demuestra ELT por lotes.
- **No** multi-cloud: DuckDB para el demo, BigQuery como destino productivo de
  referencia. Agregar un tercer destino no demuestra nada nuevo.
- **No** portar herramientas de operación atadas a una VM concreta (chequeos de
  conectividad de un servidor específico, diagnósticos de un inventario de
  tablas particular). Lo que se porta es el patrón, nunca el inventario.

---

## 8. Checklist de arranque en una máquina nueva

```bash
git clone <repo> && cd dlt-medallion-pipeline
python -m venv dlt_env && source dlt_env/Scripts/activate   # Windows
pip install -r requirements-dev.txt
python -m pytest                       # debe dar 62 pruebas en verde (estado 2026-08-29)
python -m ruff check .                 # 11 hallazgos hasta que se cierre F0.2
```

Requisitos adicionales para trabajar en F1 en adelante: Docker Desktop con al
menos 4 GB asignados, y el driver ODBC de SQL Server si se va a correr la
fuente A desde el host en vez de desde un contenedor.

**Orden recomendado de ataque:** F0 completo (una sesión corta, y ya se nota
desde fuera) → F1 (la fase que cambia el proyecto de categoría) → F2 → F3 → F4
→ F5 → F6. F5 puede adelantarse si interesa más la profundidad técnica que la
ejecutabilidad, pero F5.2 depende de tener la fuente A del demo en pie.

---

## 9. Cómo quedó el estado al cerrar la sesión de análisis

- Repo verificado limpio de datos y nombres corporativos (§1.2).
- 62 pruebas en verde, 11 hallazgos de lint, 44 archivos versionados, 1 commit,
  sin remoto configurado.
- **F0.1 a F0.5 cerrados** (LICENSE + badges + one-liner; `pyproject.toml`
  con ruff limpio; CI en verde con jobs `lint`/`tests`; nomenclatura
  heredada corregida en la DAG factory; `accounts` declarada en
  `sources.yml`). **F0.6 es el siguiente paso.**
