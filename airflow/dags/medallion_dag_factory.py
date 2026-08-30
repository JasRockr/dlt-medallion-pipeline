"""DAG factory genérica: lee cada manifiesto declarativo (`sources/<dominio>.yaml`)
y construye un DAG con el mismo esquema de 3 fases (extract_bronze ->
transform_staging -> transform_curated), sin un DAG escrito a mano por
dominio. Mismo principio que `run_pipeline.py` del lado de dlt: este
módulo no conoce ningún dominio de negocio en particular.

Para agregar un dominio nuevo a Airflow no se toca este archivo -- alcanza
con que exista `sources/<dominio>.yaml` (ver docs/ARCHITECTURE.md sección
"Orquestación (Airflow)"):

- `extract_bronze` se agrega siempre (todo dominio tiene extracción).
- `transform_staging` solo si existe `dbt/models/staging/<dominio>/`.
- `transform_curated` solo si existe `dbt/models/marts/<dominio>/`.
- El bloque opcional `orchestration.schedule` del manifiesto fija el cron;
  si se omite, el DAG queda con disparo manual (`schedule=None`) y pausado
  al crearse, para no disparar nada por accidente antes de revisarlo.

Variables de Airflow que este módulo lee (con default para que el parseo
del DAG no falle si todavía no se configuraron en la UI):

- `vm01_ssh_conn_id`: Connection SSH hacia la VM de extracción (VM-01).
- `vm01_project_root`: ruta del repo en VM-01.
- `vm01_python_bin`: python del venv de dlt en VM-01 (dlt_env).
- `dbt_project_dir` / `dbt_profiles_dir`: rutas del proyecto dbt en VM-02.
- `dbt_bin`: ejecutable de dbt en VM-02. Default: el venv aislado que
  instala el Dockerfile de la imagen de Airflow (ver docs/ARCHITECTURE.md
  sección "Orquestación (Airflow)" y `docker-compose.yml`).
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Dict

import pendulum
import yaml
from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator
from airflow.providers.ssh.operators.ssh import SSHOperator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS_DIR = PROJECT_ROOT / "sources"
DBT_MODELS_DIR = PROJECT_ROOT / "dbt" / "models"

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _var(key: str, default: str) -> str:
    return Variable.get(key, default_var=default)


def _cargar_manifest(manifest_path: Path) -> Dict[str, Any]:
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8"))


def _build_extract_task(dag: DAG, manifest_relpath: str) -> SSHOperator:
    project_root = _var("vm01_project_root", "/opt/dlt-medallion-pipeline")
    python_bin = _var("vm01_python_bin", "/opt/dlt-medallion-pipeline/dlt_env/bin/python")
    command = f"cd {project_root} && {python_bin} run_pipeline.py --manifest {manifest_relpath}"

    return SSHOperator(
        task_id="extract_bronze",
        ssh_conn_id=_var("vm01_ssh_conn_id", "vm01_extraccion"),
        command=command,
        cmd_timeout=3600,
        dag=dag,
    )


def _build_dbt_task(dag: DAG, task_id: str, dbt_select: str) -> BashOperator:
    project_dir = _var("dbt_project_dir", str(PROJECT_ROOT / "dbt"))
    profiles_dir = _var("dbt_profiles_dir", project_dir)
    dbt_bin = _var("dbt_bin", "/opt/airflow/dbt_venv/bin/dbt")
    command = (
        f"{dbt_bin} run --select {dbt_select} "
        f"--project-dir {project_dir} --profiles-dir {profiles_dir}"
    )

    return BashOperator(task_id=task_id, bash_command=command, dag=dag)


def _build_dag(manifest_path: Path) -> DAG:
    manifest = _cargar_manifest(manifest_path)
    domain = manifest["domain"]
    orchestration = manifest.get("orchestration") or {}
    manifest_relpath = f"sources/{manifest_path.name}"

    dag = DAG(
        dag_id=f"{domain}_pipeline",
        schedule=orchestration.get("schedule"),
        start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
        catchup=False,
        is_paused_upon_creation=True,
        default_args=DEFAULT_ARGS,
        tags=["medallion", domain],
    )

    with dag:
        extract = _build_extract_task(dag, manifest_relpath)
        upstream = extract

        if (DBT_MODELS_DIR / "staging" / domain).is_dir():
            staging = _build_dbt_task(
                dag, "transform_staging", f"path:models/staging/{domain}"
            )
            upstream >> staging
            upstream = staging

        if (DBT_MODELS_DIR / "marts" / domain).is_dir():
            curated = _build_dbt_task(
                dag, "transform_curated", f"path:models/marts/{domain}"
            )
            upstream >> curated

    return dag


for _manifest_path in sorted(MANIFESTS_DIR.glob("*.yaml")):
    _dag = _build_dag(_manifest_path)
    globals()[_dag.dag_id] = _dag
