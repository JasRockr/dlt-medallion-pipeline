# Cheatsheet: comandos para correr y probar el pipeline

Referencia rápida de comandos. Para entender *por qué* algo funciona así,
ver `docs/COMMANDS-PIPELINE.md` (setup completo), `docs/ARCHITECTURE.md`
(diseño del motor de reglas, la capa dbt y la DAG factory) y
`docs/DEPLOYMENT.md` (puesta en marcha de VM-01/VM-02).

## Setup inicial (una sola vez por máquina)

```bash
python -m venv dlt_env
source dlt_env\Scripts\activate          # Windows
# source dlt_env/bin/activate            # Linux/Mac

pip install -r requirements-dev.txt      # runtime + pytest

cp .env.example .env                              # completar GOOGLE_APPLICATION_CREDENTIALS
cp .dlt/secrets.toml.example .dlt/secrets.toml     # completar credenciales reales

gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud auth application-default login
```

**Venv separado para dbt** (dbt no comparte dependencias con dlt ni con
Airflow -- evita conflictos de versión entre sus respectivos requirements):

```bash
python -m venv dbt_env
source dbt_env\Scripts\activate          # Windows
pip install -r requirements-dbt.txt
cp dbt/profiles.yml.example dbt/profiles.yml     # completar project_id real
```

## Día a día: correr pipelines

```bash
# Prueba de humo (conectividad + ADC + facturación, solo tabla `countries`)
python scripts/smoke_test_connection.py

# Pipeline de un dominio (runner genérico + manifiesto)
python run_pipeline.py --manifest sources/business_partners.yaml
```

## dbt: staging (silver) y marts (gold)

```bash
cd dbt
../dbt_env/Scripts/dbt run --select path:models/staging/business_partners --profiles-dir .
../dbt_env/Scripts/dbt run --select path:models/marts/business_partners --profiles-dir .
../dbt_env/Scripts/dbt test --profiles-dir .         # tests de schema.yml
../dbt_env/Scripts/dbt parse --profiles-dir .         # solo valida sintaxis/refs, sin conexión real
```

## Airflow + docker-compose (VM-02)

```bash
docker compose up airflow-init     # una sola vez: migra la DB y crea el usuario admin
docker compose up -d               # webserver (http://localhost:8080) + scheduler

docker compose exec airflow-webserver airflow dags list
docker compose exec airflow-webserver airflow dags trigger business_partners_pipeline
docker compose exec airflow-webserver airflow tasks list business_partners_pipeline

docker compose logs -f airflow-scheduler
docker compose down                # detener (los datos de Postgres persisten en el volumen)
```

Puesta en marcha completa (variables de `.env`, llave SSH hacia VM-01,
creación de la `Connection` en Airflow): `docs/COMMANDS-PIPELINE.md`
sección 11 y `docs/DEPLOYMENT.md`.

## Pruebas

```bash
pytest tests/ -v                                    # todo
pytest tests/test_rule_engine.py -v                 # solo el motor genérico
pytest tests/test_business_partners_contract.py -v  # solo regresión de Business Partners
```

## Diagnóstico / troubleshooting

```bash
# ¿ADC funciona?
python -c "import google.auth; print(google.auth.default())"

# ¿Facturación habilitada en el proyecto?
gcloud billing accounts list
gcloud billing projects describe <PROJECT_ID>

# ¿gcloud no se reconoce en esta terminal?
# (la sesión no recargó el PATH tras instalar el SDK; abrir una terminal nueva
# o, en PowerShell: $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User"))

# ¿Qué tablas/columnas tiene realmente el origen? (antes de escribir un contrato)
python -c "
from dotenv import load_dotenv; load_dotenv()
import dlt
from sqlalchemy import create_engine, inspect
from dlt.sources.credentials import ConnectionStringCredentials
creds = dlt.secrets.get('sources.mssql_business_partners.credentials', expected_type=ConnectionStringCredentials)
insp = inspect(create_engine(creds.to_url()))
print(insp.get_table_names())                  # todas las tablas
print(insp.get_columns('business_partners'))   # columnas de una tabla puntual
"
```

## Verificar resultados en BigQuery

```sql
-- Distribución de estados de validación
SELECT estado_validacion_global, COUNT(*) AS n
FROM business_partners_data.business_partners
GROUP BY estado_validacion_global
ORDER BY n DESC;

-- Resumen ejecutivo (vista gold)
SELECT * FROM business_partners_data.resumen_ejecucion_business_partners
ORDER BY total_business_partners DESC;

-- Conteo de filas por tabla cargada (cualquier dominio)
SELECT table_id, row_count FROM business_partners_data.__TABLES__ ORDER BY table_id;
```

## Agregar un dominio nuevo

```bash
# 1. contracts/<dominio>.json    (fields/groups/checks - ver ARCHITECTURE.md)
# 2. transforms/domains/<dominio>/plugins.py   (solo si hace falta lógica bespoke)
# 3. transforms/domains/<dominio>/views.py     (solo si hace falta vista gold, mientras no haya dbt)
# 4. sources/<dominio>.yaml      (manifiesto)
python run_pipeline.py --manifest sources/<dominio>.yaml
```

Para que ese dominio también tenga capa dbt y DAG de Airflow (opcional, no
bloquea lo de arriba): `docs/ARCHITECTURE.md` secciones "Cómo agregar la
capa dbt de un dominio nuevo" y "Orquestación (Airflow)" — un dominio sin
`dbt/models/staging/<dominio>/` simplemente obtiene un DAG de solo
extracción, sin configuración adicional.

## Git

```bash
git status
git add <archivos especificos>     # nunca -A a ciegas: revisar antes
git commit -m "tipo: descripción en español, conventional commits"
```
