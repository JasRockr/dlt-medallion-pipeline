# Flujo de Datos con Python + dlt (Data Load Tools)

Pipeline MSSQL → BigQuery, pensado para reproducirse paso a paso desde cero
(entorno free/personal de GCP) y migrar después a un entorno corporativo real
sin cambios de código.

Esta guía es para una **máquina de desarrollo** (correr/probar el pipeline
localmente). Para provisionar las VMs reales (VM-01/VM-02, laboratorio o
producción) ver `docs/DEPLOYMENT.md`.

---

## 1. Entorno virtual

````bash
# dlt_env basado en Python 3.12: Anaconda
# conda create --name dlt_env python=3.12 -y
# conda activate dlt_env

## venv
python -m venv dlt_env
# source dlt_env/bin/activate # Linux/Mac
source dlt_env\Scripts\activate # Win
````

## 2. Proyecto con CLI de dlt

````bash
## Instalación dlt
pip install dlt
dlt --version

## Iniciar nuevo proyecto dlt: pipeline mssql -> bigquery
dlt init mssql_test bigquery

# Scaffolding creado por dlt (el nombre de archivo inicial,
# mssql_test_pipeline.py, luego se reemplazó por scripts/smoke_test_connection.py
# + el runner genérico run_pipeline.py - ver sección 9 y docs/ARCHITECTURE.md)
# .
# ├── requirements.txt
# ├── mssql_test_pipeline.py
# ├── .gitignore
# ├── .dlt
# │   ├── config.toml
# │   ├── secrets.toml

## Origen genérico de bases de datos SQL (RDB), necesario para MSSQL
pip install "dlt[sql_database]"

## Driver Python para conectarse a SQL Server vía ODBC
pip install pyodbc

## Carga de variables de entorno desde .env (ver sección 6 - ADC)
pip install python-dotenv

## Manifiestos declarativos (sources/*.yaml) - ver docs/ARCHITECTURE.md
pip install pyyaml

## Instalación de todo junto (requirements.txt ya incluye lo anterior)
pip install -r requirements.txt

## Para desarrollo/pruebas (incluye pytest)
pip install -r requirements-dev.txt
pytest tests/ -v
````

A nivel de sistema (no Python) también se necesita el **ODBC Driver 17 (o 18)
for SQL Server** de Microsoft instalado en la máquina. Verificar con:

````powershell
Get-OdbcDriver | Where-Object { $_.Name -like "*SQL Server*" }
````

## 3. Configuración de orígenes (no sensible) — `.dlt/config.toml`

`table_names` (plural, lista) es el nombre real del parámetro de
`sql_database()`; usar `table` (singular) lo ignora silenciosamente y dlt
termina reflejando **toda** la base de datos en vez de la tabla deseada (una
base de datos de ERP típica puede tener varios cientos de tablas; reflejarla
completa puede chocar con una FK duplicada ajena al submodelo que nos
interesa — ver "Gaps conocidos" en `docs/ARCHITECTURE.md`).

`table_names` se pasa **explícito**, no en este archivo:
`scripts/smoke_test_connection.py` lo define en código, y `business_partners`
(y cualquier dominio nuevo) lo define en su manifiesto
(`sources/<dominio>.yaml`, clave `tables`) — para que ninguno afecte el
alcance de tablas de otro al compartir esta sección de configuración.

````toml
[runtime]
log_level = "WARNING"
dlthub_telemetry = true

[destination.bigquery]
location = "US"
````

## 4. Credenciales — `.dlt/secrets.toml`

Sólo van aquí los secretos que dlt resuelve de forma nativa. **No** se
incluyen `private_key`/`client_email` de BigQuery — ver sección 6. Copiar
desde `.dlt/secrets.toml.example`.

La sección de MSSQL se nombra por origen (`sources.mssql_business_partners`,
no el genérico `sources.sql_database`) para poder sumar más
motores/orígenes sin colisión — ver sección 10.

````toml
[destination.bigquery.credentials]
project_id = "TU_PROJECT_ID"

[sources.mssql_business_partners.credentials]
drivername = "mssql+pyodbc"
database = "TU_BASE_DE_DATOS"
password = "TU_PASSWORD"
username = "TU_USUARIO"
host = "TU_HOST_O_IP"
port = 1433
query = { driver = "ODBC Driver 17 for SQL Server" }
````

`secrets.toml` y `.env` ya están en `.gitignore` — nunca deben subirse al
repo.

## 5. Función de conexión — `scripts/smoke_test_connection.py`

No es un pipeline de negocio: solo confirma que credenciales + ADC +
facturación funcionan, extrayendo únicamente `countries`. El pipeline real se
ejecuta con el runner genérico (sección 9, `docs/ARCHITECTURE.md`).

````python
from dotenv import load_dotenv

load_dotenv()  # carga GOOGLE_APPLICATION_CREDENTIALS desde .env (ver sección 6)

import dlt
from dlt.sources.credentials import ConnectionStringCredentials
from dlt.sources.sql_database import sql_database

CREDENTIALS_SECTION = "sources.mssql_business_partners.credentials"

def run_smoke_test() -> None:
    credentials = dlt.secrets.get(CREDENTIALS_SECTION, expected_type=ConnectionStringCredentials)
    source = sql_database(credentials=credentials, table_names=["countries"])
    pipeline = dlt.pipeline(
        pipeline_name="smoke_test_pipeline", destination='bigquery',
        dataset_name="smoke_test_data"
    )

    load_info = pipeline.run(source)
    print(load_info)

if __name__ == "__main__":
    run_smoke_test()
````

## 6. Autenticación a BigQuery sin clave JSON (Application Default Credentials)

Un error típico en proyectos de GCP con la política de organización
`iam.disableServiceAccountKeyCreation` activa: Google bloquea la descarga de
claves JSON de cuenta de servicio por seguridad. Esta política es además un
default de seguridad cada vez más común, así que el entorno corporativo real
probablemente la tendrá igual — conviene construir el pipeline sin depender
de claves desde el día uno.

`dlt`'s `GcpServiceAccountCredentials` cae automáticamente a
`google.auth.default()` (ADC) cuando `private_key`/`client_email` no están
en `secrets.toml`. Pasos para generar esas credenciales localmente:

````bash
# Instalar Google Cloud CLI (gcloud) si no está disponible:
# https://cloud.google.com/sdk/docs/install

gcloud auth login
gcloud config set project TU_PROJECT_ID
gcloud auth application-default login
````

El último comando abre el navegador, pide iniciar sesión y al finalizar
imprime una línea `Credentials saved to file: [...]`.

**Caveat de Windows:** si `gcloud` usa el Python de Microsoft Store (lo avisa
con un `WARNING` al correr `application-default login`), el archivo ADC
queda guardado en una ruta "sandboxed" tipo:

```text
C:\Users\<usuario>\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.1x_xxxxxxxxxxxxx\LocalCache\Roaming\gcloud\application_default_credentials.json
```

en vez de la ubicación estándar `%APPDATA%\gcloud\`. La librería
`google-auth` de Python (la que usa dlt) **no** la encuentra ahí por
defecto. La propia salida de `gcloud` indica la solución: apuntar
`GOOGLE_APPLICATION_CREDENTIALS` a esa ruta exacta.

Como esa variable la lee `google-auth` directamente del sistema operativo
(nunca pasa por el sistema de configuración de dlt, así que no puede vivir
en `secrets.toml`), se centraliza en un archivo `.env` en la raíz del
proyecto, cargado por `python-dotenv` al inicio del script:

````dotenv
# .env
GOOGLE_APPLICATION_CREDENTIALS=C:\Users\<usuario>\AppData\Local\Packages\...\application_default_credentials.json
````

Verificación rápida de que ADC funciona:

````bash
python -c "import google.auth; print(google.auth.default())"
````

## 7. Habilitar facturación en el proyecto GCP

BigQuery permite `SELECT` sin facturación habilitada (modo sandbox), pero
**cargar datos** (lo que hace dlt al escribir filas) requiere una cuenta de
facturación vinculada y activa, aunque sea consumiendo el crédito gratuito
de $300/90 días.

````bash
gcloud billing accounts list
gcloud billing projects describe TU_PROJECT_ID
````

Si `billingEnabled: false` u `OPEN: False`, completar/activar la cuenta de
facturación desde la consola:
[console.cloud.google.com/billing/linkedaccount](https://console.cloud.google.com/billing/linkedaccount)

## 8. Ejecutar la prueba de humo

````bash
python scripts/smoke_test_connection.py
````

Salida esperada:

```text
Pipeline smoke_test_pipeline load step completed in N seconds
1 load package(s) were loaded to destination bigquery and into dataset smoke_test_data
Load package <id> is LOADED and contains no failed jobs
```

## 9. Dominio Business Partners: runner genérico + motor de reglas declarativo

El dominio Business Partners (16 tablas de
`docs/business-partners-schema.dbml`, 15 catálogos + `business_partners`) ya
no tiene un script propio. Se ejecuta con el runner genérico y un
manifiesto:

````bash
python run_pipeline.py --manifest sources/business_partners.yaml
````

**Por qué un runner genérico y no un script por dominio:** con cientos de
tablas y varios motores de origen en el radar (ver más abajo), escribir un
script Python nuevo por cada dominio no escala. `run_pipeline.py` y
`transforms/rule_engine.py` no saben nada de "business_partners" — leen el
manifiesto (`sources/business_partners.yaml`) y el contrato
(`contracts/business_partners.json`) y hacen lo mismo que harían para
cualquier otro dominio. El diseño completo (catálogo de operadores, esquema
del contrato, cómo agregar un dominio o un tipo de origen nuevo) está en
**`docs/ARCHITECTURE.md`** — léelo antes de tocar `rule_engine.py` o de
copiar el patrón de Business Partners para un dominio nuevo.

**Dónde se transforma (y por qué):** las reglas se aplican en Python durante
la extracción de dlt (`resource.add_map()`), **antes** de cargar a BigQuery.
Esto mantiene el costo en cero mientras este es un laboratorio de capa
gratuita: son funciones puras de Python (sin red, sin SQL) y la carga a
BigQuery vía load job tampoco tiene costo de consulta (solo almacenamiento,
insignificante para este volumen). La alternativa —reglas como
vistas/modelos SQL en BigQuery después de cargar crudo (patrón ELT con
dbt)— consume cuota de consultas (cubierta por el 1 TiB/mes gratuito a este
volumen, pero añade una pieza más al stack). Queda documentado como punto de
reevaluación si el volumen crece lo suficiente para que el rendimiento en
Python deje de ser trivial, o si el catálogo de operadores declarativos se
vuelve insuficiente (en ese caso, evaluar adoptar Great Expectations/Soda/
dbt tests en vez de seguir ampliando `rule_engine.py` a mano).

**Arquitectura de capas (medallion ligero, sin dbt todavía):**

- **Bronze:** los 15 catálogos se cargan 1:1 sin transformar.
- **Silver:** `business_partners` se carga con sus columnas originales
  **más** las columnas `VALIDACION_*` y
  `estado_validacion_global`/`detalle_validacion` generadas por el motor de
  reglas — bronze y silver quedan combinados en una sola tabla por
  simplicidad de laboratorio (no hay copia cruda separada de
  `business_partners`; si se necesita reprocesar desde cero, dlt vuelve a
  extraer de MSSQL).
- **Gold:** la vista `business_partners_data.resumen_ejecucion_business_partners`
  (`transforms/domains/business_partners/views.py` +
  `transforms/bigquery_gold.py`), que agrega conteos de error por
  categoría — gratis de crear y mantener porque es una vista, no una tabla.

**Actualización:** la capa dbt (staging/marts con datasets propios, ver
sección 11 y `docs/ARCHITECTURE.md` sección "Capa de transformación (dbt)")
ya existe para Business Partners. No reemplaza nada de lo descrito arriba:
dlt sigue escribiendo bronze+validación en una sola tabla igual que hoy; dbt
construye silver/gold a partir de ahí, en datasets separados
(`staging_business_partners`, `curated_business_partners`).

**Contrato de columnas — `contracts/business_partners.json`:** define los
nombres canónicos esperados, sus alias permitidos, y los `checks`/`groups`
declarativos que produce el motor (ver `docs/ARCHITECTURE.md` para el
esquema completo). `transforms/contract_utils.py` compara las columnas
reales de `business_partners` contra el contrato antes de correr el
pipeline: si un campo requerido no existe ni por su nombre canónico ni por
alias, **falla temprano** (ver "Convención de Normalización de Columnas" en
`docs/REGLAS-NEGOCIO.md`).

**Gap de esquema conocido (RN-10, RN-11):** el esquema de
`business_partners` no tiene columnas `customer_segment` ni `tax_category`.
Por decisión de negocio, esas reglas se mantienen activas: el contrato las
marca `"available_in_source": false` y el motor emite automáticamente
`ALERTA_CAMPO_NO_DISPONIBLE_EN_ORIGEN` en `VALIDACION_SEGMENTO` /
`VALIDACION_CATEGORIA_FISCAL` hasta que se defina el campo de origen real.
Esto hace que ninguna fila pueda llegar a `estado_validacion_global = "OK"`
hoy — el máximo alcanzable es `"ALERTA"` — lo cual es el comportamiento
esperado, no un error del pipeline.

**Dispatch de reglas por tipo de documento (RN-03 a RN-07):** ver
`document_type_dispatch` en `contracts/business_partners.json` y
`transforms/domains/business_partners/plugins.py` (la única parte de
Business Partners que sigue siendo código Python, porque depende de dos
campos a la vez de forma no expresable como reglas declarativas — ver
`docs/ARCHITECTURE.md`).

**Pruebas:** `pytest` corre el motor genérico + los plugins de Business
Partners + un set de casos sintéticos de regresión contra el contrato
(`tests/test_business_partners_contract.py`).

**Verificar resultados:**

````sql
SELECT estado_validacion_global, COUNT(*) FROM business_partners_data.business_partners
GROUP BY estado_validacion_global;

SELECT * FROM business_partners_data.resumen_ejecucion_business_partners
ORDER BY total_business_partners DESC;
````

## 10. Credenciales nombradas por origen (preparación multi-fuente)

`sql_database()` resuelve credenciales por defecto desde la sección
`sources.sql_database` (el nombre de la función dlt), que es compartida por
**cualquier** llamada a `sql_database()` en el repo. Eso funciona mientras
solo exista un origen, pero colisiona en cuanto se agregue un segundo motor
(MySQL, PostgreSQL, otro MSSQL).

Por eso las credenciales viven en una sección nombrada por origen
(`sources.mssql_business_partners.credentials`, no
`sources.sql_database.credentials`) y se resuelven explícitamente en
código:

````python
import dlt
from dlt.sources.credentials import ConnectionStringCredentials
from dlt.sources.sql_database import sql_database

credentials = dlt.secrets.get(
    "sources.mssql_business_partners.credentials", expected_type=ConnectionStringCredentials
)
source = sql_database(credentials=credentials, table_names=[...])
````

Al sumar un segundo origen, se agrega su propia sección
(`sources.mysql_ventas.credentials`, `sources.pgsql_inventario.credentials`,
etc.) sin tocar las existentes. `sql_database()` es agnóstico al motor vía
SQLAlchemy: sumar MySQL/PostgreSQL es básicamente nueva cadena de conexión +
driver (`pymysql`, `psycopg2`), no un rediseño. CSV/XLSX no tienen un origen
dlt nativo equivalente a `sql_database()` y requieren un recurso propio
(`dlt.sources.filesystem` para CSV, o un `@dlt.resource` envolviendo
`pandas`/`openpyxl` para XLSX) — pendiente de implementar cuando se necesite.

## 11. Airflow + dbt: puesta en marcha del stack (VM-02)

`docker-compose.yml` levanta Airflow con `LocalExecutor` (sin Redis/Celery
— stack más simple para un laboratorio de un solo nodo) + dbt en un venv
aislado dentro de la misma imagen (`Dockerfile`). Pensado para correr en
VM-02; en el lab puede probarse igual en cualquier máquina con Docker.

````bash
# 1. Variables de entorno (mismo .env que ya usa dlt, ver sección 6).
# GOOGLE_APPLICATION_CREDENTIALS debe apuntar a la ruta generada por
# `gcloud auth application-default login` corrido EN VM-02 (no la de
# VM-01) -- docker-compose.yml monta ese archivo dentro de los contenedores
# en la misma ruta, así que sin este paso `dbt run` no encuentra ADC.
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# pegar el resultado en AIRFLOW_FERNET_KEY del .env, y completar
# AIRFLOW_WEBSERVER_SECRET_KEY / AIRFLOW_ADMIN_PASSWORD / POSTGRES_PASSWORD

# 2. Build + arranque
docker compose up airflow-init   # corre una vez: migra la DB y crea el usuario admin
docker compose up -d             # webserver (http://localhost:8080) + scheduler
````

`airflow dags list` debería mostrar `business_partners_pipeline` (3 tareas,
extracción + staging + marts) — la DAG factory genera un DAG por cada
manifiesto en `sources/`, ver `docs/ARCHITECTURE.md` sección "Orquestación
(Airflow)".

**Conexión SSH hacia VM-01 (no se crea sola, requiere VM-01 real):**

````bash
# Copiar la llave privada a airflow/keys/ (gitignored, ver .gitignore) antes de este paso
docker compose exec airflow-webserver airflow connections add vm01_extraccion \
  --conn-type ssh \
  --conn-host <ip-vm01> \
  --conn-login <usuario-vm01> \
  --conn-extra '{"key_file": "/opt/airflow/keys/vm01_id_rsa"}'
````

**Variables de Airflow** (solo si las rutas reales en VM-01/VM-02 difieren
de los defaults documentados en `airflow/dags/medallion_dag_factory.py` y
`docs/ARCHITECTURE.md` sección "Orquestación (Airflow)"):

````bash
docker compose exec airflow-webserver airflow variables set vm01_project_root /ruta/real/en/vm01
````

---

## Checklist para migrar a producción (Workspace corporativo)

Este checklist es sobre la **capa de datos** (dlt/contratos/credenciales).
Para las diferencias de **infraestructura** entre el laboratorio en
VirtualBox y producción en GCP (red, ADC, service accounts), ver la tabla
en `docs/DEPLOYMENT.md` sección "Diferencias laboratorio vs producción".

- [ ] No usar credenciales de usuario (ADC personal): adjuntar una cuenta de
      servicio directamente al recurso de cómputo (Cloud Run, GCE, GKE,
      Composer) o usar Workload Identity Federation si el workload corre
      fuera de GCP. Sigue sin requerir claves JSON.
- [ ] Roles mínimos en la cuenta de servicio: `roles/bigquery.dataEditor` +
      `roles/bigquery.jobUser` (evitar `roles/bigquery.admin`).
- [ ] Mover `host`/`username`/`password` de MSSQL (y cualquier otro secreto)
      a un gestor de secretos (Secret Manager) en vez de `secrets.toml`/`.env`.
- [ ] Confirmar que la política `iam.disableServiceAccountKeyCreation` (u
      otra equivalente) siga sin necesitar excepciones — el diseño actual ya
      no depende de claves JSON.
- [ ] `business_partners`: pasar de `write_disposition="replace"` a `merge`
      con `primary_key="partner_id"` + cursor incremental
      (`created_at`/timestamp de vigencia) una vez el volumen real lo
      justifique.
- [ ] Evaluar mover el contenido de `contracts/*.json` a modelos dbt
      (staging/marts) si el número de consumidores de
      `resumen_ejecucion_business_partners` crece, si el procesamiento en
      Python se vuelve el cuello de botella, o si el catálogo de operadores
      de `transforms/rule_engine.py` se vuelve insuficiente (en ese caso,
      considerar Great Expectations/Soda en vez de seguir ampliándolo a
      mano — ver `docs/ARCHITECTURE.md`).
- [ ] Definir el origen real de `customer_segment` y `tax_category`
      (RN-10/RN-11) y actualizar `contracts/business_partners.json`
      (`available_in_source: true` + sus reglas) para dejar de alertar por defecto.
- [ ] Implementar los builders de origen pendientes
      (`transforms/source_builders/`) a medida que cada fuente concreta
      (CSV, XLSX, XML, JSON, REST API, PostgreSQL, MySQL) tenga un caso
      real — ver "Cómo agregar un tipo de origen nuevo" en `docs/ARCHITECTURE.md`.
