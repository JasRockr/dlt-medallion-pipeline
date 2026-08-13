"""Builder de origen para bases de datos relacionales vía SQLAlchemy.

Agnóstico de motor: MSSQL, PostgreSQL o MySQL son la misma función — solo
cambia `drivername`/`query.driver` en la sección de credenciales del
manifiesto (ver `sources/business_partners.yaml` y docs/ARCHITECTURE.md). dlt
resuelve el dialecto correcto a partir del `drivername` de las credenciales.
"""

from typing import Any, Dict, Optional, Set, Tuple

import dlt
from dlt.sources.credentials import ConnectionStringCredentials
from dlt.sources.sql_database import sql_database
from sqlalchemy import create_engine, inspect


def build_source(manifest: Dict[str, Any]) -> Tuple[Any, Optional[Set[str]]]:
    """Devuelve (source de dlt, columnas reales de `rule_target_table`).

    Las columnas reales se usan en el runner para el pre-flight check de
    `transforms/contract_utils.py` (resolución de alias / fail-fast). Si el
    manifiesto no define `rule_target_table` (dominio "solo bronze", sin
    contrato de reglas), se omite la inspección y se devuelve `None`.
    """
    credentials = dlt.secrets.get(
        manifest["credentials_section"], expected_type=ConnectionStringCredentials
    )
    source = sql_database(credentials=credentials, table_names=manifest["tables"])

    if "rule_target_table" not in manifest:
        return source, None

    engine = create_engine(credentials.to_url())
    columnas_reales = {
        col["name"] for col in inspect(engine).get_columns(manifest["rule_target_table"])
    }
    engine.dispose()

    return source, columnas_reales
