# PIPELINE DE DATOS: dlt + dbt + Airflow

[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](Dockerfile)

> Proyecto de portafolio: pipeline medallion (bronze/silver/gold) con
> ingesta vía dlt, transformación en dbt, orquestación en Airflow y un
> motor de reglas de negocio declarativo.

Pipeline de datos personal con arquitectura medallion completa: **dlt**
extrae de MSSQL a BigQuery (bronze), **dbt** transforma (silver/staging,
gold/marts), **Airflow** orquesta ambos, y un **motor de reglas de negocio
declarativo** (contratos JSON, no código Python por regla) valida cada fila
en tiempo de carga. Diseñado para escalar a cientos de tablas / múltiples
dominios de negocio sin reescribir el motor ni el runner — agregar un
dominio nuevo es manifiesto + contrato, no código nuevo.

El dominio de ejemplo incluido (`business_partners` — maestro de
contrapartes cliente/proveedor/empleado, un concepto ERP/CRM estándar) es
ilustrativo: los datos, reglas de validación y esquema son ficticios,
pensados para mostrar el patrón completo end-to-end de forma reproducible.

## Mapa de documentación

| Quiero... | Leer |
| --- | --- |
| Saber qué falta por construir y en qué orden (estado y plan del proyecto) | [docs/ROADMAP.md](docs/ROADMAP.md) |
| Entender el motor de reglas, la capa dbt y la DAG factory; agregar un dominio/regla/origen nuevo | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Configurar mi máquina y correr un pipeline de dlt localmente, paso a paso | [docs/COMMANDS-PIPELINE.md](docs/COMMANDS-PIPELINE.md) |
| Ver comandos rápidos del día a día (dlt, dbt, Airflow) sin explicación | [docs/CHEATSHEET.md](docs/CHEATSHEET.md) |
| Consultar las reglas de negocio del dominio de ejemplo Business Partners | [docs/REGLAS-NEGOCIO.md](docs/REGLAS-NEGOCIO.md) |
| Levantar VM-01 (extracción) / VM-02 (Airflow+dbt) en laboratorio o producción | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |

## Quickstart (desarrollo local)

```bash
python -m venv dlt_env && source dlt_env/Scripts/activate   # Windows; dlt_env/bin/activate en Linux/Mac
pip install -r requirements-dev.txt
cp .env.example .env                              # completar GOOGLE_APPLICATION_CREDENTIALS
cp .dlt/secrets.toml.example .dlt/secrets.toml     # completar credenciales reales
gcloud auth application-default login
python run_pipeline.py --manifest sources/business_partners.yaml
```

Detalle completo de cada paso: [docs/COMMANDS-PIPELINE.md](docs/COMMANDS-PIPELINE.md).

## Estructura del repo (alto nivel)

```text
sources/<dominio>.yaml      manifiesto: qué extraer, a dónde, con qué contrato
contracts/<dominio>.json    contrato declarativo: campos, checks, grupos
transforms/                 motor de reglas + builders de origen + código por dominio
run_pipeline.py             runner único: extracción dlt -> bronze
dbt/                        staging (silver) y marts (gold) sobre el bronze de dlt
airflow/dags/               DAG factory: un DAG por manifiesto, sin DAGs a mano
docker-compose.yml          Airflow (LocalExecutor) + dbt, para VM-02
```

Mapa completo de carpetas y por qué existe cada una:
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#mapa-de-carpetas).
