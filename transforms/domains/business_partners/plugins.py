"""Lógica de negocio de Business Partners que no se puede expresar con los
operadores genéricos de `transforms/rule_engine.py` (escape hatch de
plugins).

Cada función recibe la fila completa (`dict`) y devuelve un código de
estado de string (`"OK"` o `"ERROR_<algo>"`), igual que cualquier regla
declarativa. Referenciadas desde `contracts/business_partners.json` vía
`"plugin": "transforms.domains.business_partners.plugins:<nombre_funcion>"`.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict

from transforms.rule_engine import NOT_APPLICABLE

_CONTRACT_PATH = Path(__file__).parent.parent.parent.parent / "contracts" / "business_partners.json"

_ALNUM = re.compile(r"^[A-Za-z0-9]+$")
_ALL_SAME_CHAR = re.compile(r"^(.)\1*$")


def _s(value: Any) -> str:
    return (str(value) if value is not None else "").strip()


def _cargar_tipo_doc_rn_family() -> Dict[str, str]:
    """Fuente única de verdad: contracts/business_partners.json ->
    document_type_dispatch. No duplicar este mapeo a mano en Python: si el
    contrato cambia, debe reflejarse aquí automáticamente.
    """
    contrato = json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))
    return {
        codigo: definicion["familia"]
        for codigo, definicion in contrato["document_type_dispatch"].items()
    }


TIPO_DOC_RN_FAMILY = _cargar_tipo_doc_rn_family()


def validar_doc_estructura(row: Dict[str, Any]) -> str:
    """RN-03 a RN-07: longitud/formato del documento según su tipo
    (`document_type`). La familia de regla depende del tipo de documento,
    por eso no es expresable como una sola lista de operadores genéricos
    sobre un único campo.
    """
    t = _s(row.get("partner_id"))
    tipo = _s(row.get("document_type"))

    if not tipo:
        return "ERROR_TIPO_DOCUMENTO_FALTANTE"

    familia = TIPO_DOC_RN_FAMILY.get(tipo)
    if familia is None:
        return "ERROR_TIPO_DOCUMENTO_DESCONOCIDO"

    if familia == "GENERICO":
        return "OK"

    if familia == "ID_TRIBUTARIO_ORG":
        return "OK" if re.match(r"^[89]\d{8}(-\d{2})?$", t) else "ERROR_FORMATO_ID_TRIBUTARIO"

    if familia == "ID_NACIONAL":
        if not t.isdigit():
            return "ERROR_FORMATO_ID_NACIONAL"
        if len(t) == 9:
            return "ERROR_LONGITUD_INEXISTENTE"
        if len(t) not in (6, 7, 8, 10):
            return "ERROR_LONGITUD_ID_NACIONAL"
        if len(t) == 10 and not t.startswith("1"):
            return "ERROR_INICIO_ID_NACIONAL"
        return "OK"

    if familia == "PASAPORTE":
        return "OK" if (6 <= len(t) <= 15 and _ALNUM.match(t)) else "ERROR_FORMATO_PASAPORTE"

    if familia == "RESIDENCIA_EXTRANJERA":
        return "OK" if (4 <= len(t) <= 12 and _ALNUM.match(t)) else "ERROR_FORMATO_RESIDENCIA"

    if familia == "PERMISO_TEMPORAL":
        if 7 <= len(t) <= 15 and _ALNUM.match(t) and not _ALL_SAME_CHAR.match(t):
            return "OK"
        return "ERROR_FORMATO_PERMISO_TEMPORAL"

    return "ERROR_NO_EVALUADO"


def validar_segmentacion_nombres(row: Dict[str, Any]) -> str:
    """RN-12: personas naturales deben tener nombre/apellido segmentados en
    columnas propias. Depende de `is_individual` (clasifica el tipo de
    business partner), no de un único campo, por eso es plugin y no una
    regla declarativa.
    """
    if _s(row.get("is_individual")).upper() != "Y":
        return NOT_APPLICABLE  # organización: la segmentación de nombre natural no aplica
    if _s(row.get("first_name")) and _s(row.get("last_name")):
        return "OK"
    return "ERROR_NOMBRE_NO_SEGMENTADO"
