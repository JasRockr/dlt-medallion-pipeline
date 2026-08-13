"""Helper genérico para crear vistas 'gold' en BigQuery.

No sabe nada del contenido SQL de ningún dominio — eso vive en
`transforms/domains/<dominio>/views.py`. Son vistas (no tablas
materializadas): no duplican almacenamiento ni generan costo de carga, y
solo consumen cuota de consulta cuando alguien las lee.
"""

from google.cloud import bigquery


def crear_vista(project: str, dataset: str, sql_template: str) -> None:
    client = bigquery.Client(project=project)
    client.query(sql_template.format(project=project, dataset=dataset)).result()
