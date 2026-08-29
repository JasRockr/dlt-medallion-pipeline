"""Prueba de humo de conectividad MSSQL -> BigQuery.

No es un pipeline de negocio: extrae únicamente la tabla `countries` para
verificar que las credenciales, la autenticación ADC y la facturación de
BigQuery siguen funcionando (ver `docs/COMMANDS-PIPELINE.md`). El pipeline
real del dominio Business Partners se ejecuta con
`python run_pipeline.py --manifest sources/business_partners.yaml` (ver
`docs/ARCHITECTURE.md`).
"""

from dotenv import load_dotenv

load_dotenv()

# Los imports de abajo van después de load_dotenv() a propósito: dlt lee
# configuración (credenciales, destino) en tiempo de import, así que el
# .env tiene que estar cargado antes de importar dlt o los módulos que lo
# usan. Reordenar para contentar al linter rompe esa carga.
import dlt  # noqa: E402
from dlt.sources.credentials import ConnectionStringCredentials  # noqa: E402
from dlt.sources.sql_database import sql_database  # noqa: E402

# Misma sección de credenciales que sources/business_partners.yaml: esta
# prueba de humo valida conectividad contra el mismo origen MSSQL, no uno aparte.
CREDENTIALS_SECTION = "sources.mssql_business_partners.credentials"


def run_smoke_test() -> None:
    credentials = dlt.secrets.get(CREDENTIALS_SECTION, expected_type=ConnectionStringCredentials)
    source = sql_database(credentials=credentials, table_names=["countries"])
    pipeline = dlt.pipeline(
        pipeline_name="smoke_test_pipeline",
        destination="bigquery",
        dataset_name="smoke_test_data",
    )
    load_info = pipeline.run(source)
    print(load_info)


if __name__ == "__main__":
    run_smoke_test()
