"""Runner genérico: lee un manifiesto declarativo y ejecuta el pipeline dlt
correspondiente, aplicando el motor de reglas (`transforms/rule_engine.py`)
sobre la tabla de negocio indicada.

No conoce ningún dominio de negocio en particular — toda la semántica de
"business_partners" (o el dominio que sea) vive en el manifiesto YAML
(`sources/<dominio>.yaml`), el contrato (`contracts/<dominio>.json`) y, si
aplica, los plugins (`transforms/domains/<dominio>/`). Ver
docs/ARCHITECTURE.md para el diseño completo y cómo agregar un dominio o
un tipo de origen nuevo.

Uso:
    python run_pipeline.py --manifest sources/business_partners.yaml
"""

import argparse
import importlib
import json
import logging
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

load_dotenv()

import dlt
import yaml

from transforms.bigquery_gold import crear_vista
from transforms.contract_utils import construir_mapa_renombrado
from transforms.rule_engine import apply_business_rules

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("run_pipeline")

# Registro de builders de origen disponibles. Para agregar un tipo nuevo
# (filesystem_csv, rest_api, etc.) ver docs/ARCHITECTURE.md sección
# "Cómo agregar un tipo de origen nuevo" — no se listan builders sin
# implementación real para evitar código muerto.
SOURCE_BUILDERS = {
    "sql": "transforms.source_builders.sql:build_source",
}


def _resolver(ref: str):
    module_name, func_name = ref.split(":")
    return getattr(importlib.import_module(module_name), func_name)


def _advertir_campos_no_disponibles(contrato: Dict[str, Any]) -> None:
    for nombre_campo, definicion in contrato.get("fields", {}).items():
        if definicion.get("available_in_source") is False:
            checks_del_campo = [
                c["name"] for c in contrato["checks"] if nombre_campo in c["inputs"]
            ]
            logger.warning(
                "Campo '%s' no disponible en el origen: %s emitirá ALERTA en cada fila. %s",
                nombre_campo, ", ".join(checks_del_campo), definicion.get("note", ""),
            )


def run(manifest_path: str) -> None:
    manifest = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8"))

    build_source = _resolver(SOURCE_BUILDERS[manifest["source_type"]])
    source, columnas_reales = build_source(manifest)

    # Dominio "solo bronze" (sin contrato de reglas, ver docs/ARCHITECTURE.md):
    # se cargan las tablas tal cual, sin pre-flight de columnas ni motor de reglas.
    if "contract" in manifest:
        contrato = json.loads(Path(manifest["contract"]).read_text(encoding="utf-8"))
        _advertir_campos_no_disponibles(contrato)

        renombrado = construir_mapa_renombrado(columnas_reales, contrato)

        target = source.resources[manifest["rule_target_table"]]
        if renombrado:
            logger.warning("Resolviendo columnas por alias: %s", renombrado)
            target.add_map(lambda row: {renombrado.get(k, k): v for k, v in row.items()})
        target.add_map(apply_business_rules(contrato))
    else:
        logger.info("Dominio '%s' sin contrato: carga bronze sin reglas de negocio.", manifest["domain"])

    pipeline = dlt.pipeline(
        pipeline_name=f"{manifest['domain']}_pipeline",
        destination="bigquery",
        dataset_name=manifest["destination"]["dataset"],
    )
    load_info = pipeline.run(
        source, write_disposition=manifest["destination"].get("write_disposition", "append")
    )
    print(load_info)

    if manifest.get("gold_views"):
        project_id = dlt.secrets["destination.bigquery.credentials.project_id"]
        views_module = importlib.import_module(f"transforms.domains.{manifest['domain']}.views")
        for view_name in manifest["gold_views"]:
            crear_vista(
                project=project_id,
                dataset=manifest["destination"]["dataset"],
                sql_template=views_module.GOLD_VIEWS[view_name],
            )
            print(f"Vista {manifest['destination']['dataset']}.{view_name} creada/actualizada.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, help="Ruta al manifiesto YAML (ver sources/)")
    args = parser.parse_args()
    run(args.manifest)
