"""Resolución de contrato de columnas (ver 'Convención de Normalización de
Columnas' en docs/REGLAS-NEGOCIO.md): si una columna real no coincide con el
nombre canónico del contrato, se busca un alias permitido; si no existe
ninguno de los dos, se falla temprano antes de correr el pipeline.
"""

import logging
from typing import Any, Dict, Set

logger = logging.getLogger("contract_utils")


class ContractoIncompletoError(Exception):
    pass


def construir_mapa_renombrado(columnas_reales: Set[str], contrato: Dict[str, Any]) -> Dict[str, str]:
    """Compara las columnas reales de la tabla fuente contra `contrato["fields"]`.

    Devuelve un mapa {columna_real: nombre_canonico} solo para los campos que
    llegaron por alias (no por su nombre canónico). Lanza
    `ContractoIncompletoError` si un campo `required: true` y
    `available_in_source` distinto de `False` no aparece ni por su nombre
    canónico ni por ninguno de sus alias.
    """
    renombrado: Dict[str, str] = {}

    for nombre_canonico, definicion in contrato.get("fields", {}).items():
        if definicion.get("available_in_source") is False:
            # Gap de esquema ya documentado y aceptado (ver RN-10/RN-11) - no es
            # un error de contrato, el motor de reglas emite su propia alerta.
            continue

        if nombre_canonico in columnas_reales:
            continue

        alias_encontrado = next(
            (alias for alias in definicion.get("aliases", []) if alias in columnas_reales),
            None,
        )
        if alias_encontrado:
            renombrado[alias_encontrado] = nombre_canonico
            logger.warning(
                "Columna '%s' no encontrada; usando alias '%s' -> renombrando a '%s'.",
                nombre_canonico, alias_encontrado, nombre_canonico,
            )
            continue

        if definicion.get("required"):
            raise ContractoIncompletoError(
                f"Campo requerido '{nombre_canonico}' no existe en la fuente ni por "
                f"nombre canónico ni por alias permitido. Actualiza el contrato "
                f"(contracts/<dominio>.json) o la consulta de origen."
            )

    return renombrado
