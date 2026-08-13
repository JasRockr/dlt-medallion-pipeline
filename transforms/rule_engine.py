"""Motor de reglas declarativo, agnóstico de dominio y de motor de origen.

No sabe nada de "business_partners" ni de ningún otro dominio de negocio: interpreta
contratos JSON con dos piezas (ver docs/ARCHITECTURE.md para el esquema
completo):

- `checks`: cada uno produce una columna de validación (`name`), lee uno o
  más campos de la fila (`inputs`) y se resuelve con una lista de `rules`
  declarativas (ver `OPERATORS` más abajo) o con un `plugin` (función Python
  importada dinámicamente, para la lógica que no se puede expresar de forma
  genérica).
- `groups`: orden de evaluación de los checks, con detención temprana
  opcional (`stop_on_fail`) si algún check del grupo falla.

La idea de "negocio específico" vive en los contratos (`contracts/*.json`)
y, cuando aplica, en plugins por dominio (`transforms/domains/<dominio>/`)
— no en este módulo.
"""

import importlib
import re
from typing import Any, Callable, Dict, List

OK = "OK"
NO_EVALUADO = "NO_EVALUADO"
FIELD_NOT_IN_SOURCE = "ALERTA_CAMPO_NO_DISPONIBLE_EN_ORIGEN"
NOT_APPLICABLE = "NO_APLICA"

# Estados que un check puede devolver sin que cuenten como fallo de grupo:
# OK (paso), alerta de campo ausente en origen, y "no aplica" (un plugin
# decide que esta fila no es candidata para esta regla, p. ej. una regla de
# persona natural sobre un business partner que es una organización).
_ESTADOS_NO_FALLO = (OK, FIELD_NOT_IN_SOURCE, NOT_APPLICABLE)


def _s(value: Any) -> str:
    """Normaliza a string recortado; None -> cadena vacía."""
    return (str(value) if value is not None else "").strip()


# ---------------------------------------------------------------------------
# Catálogo de operadores. Cada uno recibe el valor ya normalizado a string y
# los parámetros declarados en la regla, y devuelve True si PASA.
# ---------------------------------------------------------------------------

def _op_not_null(value: str, **_: Any) -> bool:
    return bool(value)


def _op_regex(value: str, pattern: str, **_: Any) -> bool:
    return bool(re.match(pattern, value))


def _op_length(value: str, eq: int = None, min: int = None, max: int = None, **_: Any) -> bool:
    n = len(value)
    if eq is not None:
        return n == eq
    if min is not None and n < min:
        return False
    if max is not None and n > max:
        return False
    return True


def _op_range(value: str, min: float = None, max: float = None, **_: Any) -> bool:
    try:
        n = float(value)
    except ValueError:
        return False
    if min is not None and n < min:
        return False
    if max is not None and n > max:
        return False
    return True


def _op_enum(value: str, values: List[str], case_insensitive: bool = False, **_: Any) -> bool:
    if case_insensitive:
        return value.lower() in {v.lower() for v in values}
    return value in values


def _op_not_in(value: str, values: List[str], case_insensitive: bool = True, **_: Any) -> bool:
    if case_insensitive:
        return value.lower() not in {v.lower() for v in values}
    return value not in values


def _op_starts_with(value: str, prefix: str, **_: Any) -> bool:
    return value.startswith(prefix)


def _op_not_ends_with(value: str, values: List[str], **_: Any) -> bool:
    return not value.lower().endswith(tuple(v.lower() for v in values))


def _op_not_contains(value: str, values: List[str], case_insensitive: bool = True, **_: Any) -> bool:
    haystack = value.lower() if case_insensitive else value
    needles = [v.lower() if case_insensitive else v for v in values]
    return not any(n in haystack for n in needles)


def _op_digits_only(value: str, **_: Any) -> bool:
    return value.isdigit()


def _op_alnum(value: str, extra_chars: str = "", **_: Any) -> bool:
    pattern = r"^[A-Za-z0-9" + re.escape(extra_chars) + r"]+$"
    return bool(re.match(pattern, value))


def _op_not_repeated_char(value: str, **_: Any) -> bool:
    return not bool(re.match(r"^(.)\1*$", value))


def _op_no_spaces(value: str, **_: Any) -> bool:
    return " " not in value


OPERATORS: Dict[str, Callable[..., bool]] = {
    "not_null": _op_not_null,
    "regex": _op_regex,
    "length": _op_length,
    "range": _op_range,
    "enum": _op_enum,
    "not_in": _op_not_in,
    "starts_with": _op_starts_with,
    "not_ends_with": _op_not_ends_with,
    "not_contains": _op_not_contains,
    "digits_only": _op_digits_only,
    "alnum": _op_alnum,
    "not_repeated_char": _op_not_repeated_char,
    "no_spaces": _op_no_spaces,
}


def _resolve_plugin(ref: str) -> Callable[[Dict[str, Any]], str]:
    module_name, func_name = ref.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)


def _evaluar_regla_en_valor(value: str, regla: Dict[str, Any]) -> bool:
    op = OPERATORS.get(regla["op"])
    if op is None:
        raise ValueError(f"Operador de regla desconocido: '{regla['op']}'")
    return op(value, **{k: v for k, v in regla.items() if k != "op"})


def _evaluar_check_declarativo(check: Dict[str, Any], row: Dict[str, Any]) -> str:
    for nombre_campo in check["inputs"]:
        valor = _s(row.get(nombre_campo))
        if not valor and check.get("allow_empty", True) and not any(
            r["op"] == "not_null" for r in check.get("rules", [])
        ):
            continue  # campo vacío y ninguna regla exige not_null: se omite, no es error
        for regla in check.get("rules", []):
            if not _evaluar_regla_en_valor(valor, regla):
                return regla.get("error_code", f"ERROR_{regla['op'].upper()}")
    return OK


def _evaluar_check(check: Dict[str, Any], row: Dict[str, Any], fields: Dict[str, Any]) -> str:
    # Campo documentado como no disponible en el origen (gap de esquema
    # aceptado por negocio): el check siempre alerta, sin importar sus reglas.
    for nombre_campo in check["inputs"]:
        if fields.get(nombre_campo, {}).get("available_in_source") is False:
            return FIELD_NOT_IN_SOURCE

    if "plugin" in check:
        plugin_fn = _resolve_plugin(check["plugin"])
        return plugin_fn(row)

    return _evaluar_check_declarativo(check, row)


def validar_row(row: Dict[str, Any], contrato: Dict[str, Any]) -> Dict[str, Any]:
    """Aplica los `groups`/`checks` del contrato, en orden, con detención
    temprana por grupo. Devuelve las columnas de validación más
    `estado_validacion_global` y `detalle_validacion`.
    """
    checks_por_grupo: Dict[int, List[Dict[str, Any]]] = {}
    for check in contrato["checks"]:
        checks_por_grupo.setdefault(check["group"], []).append(check)

    resultado: Dict[str, Any] = {check["name"]: NO_EVALUADO for check in contrato["checks"]}
    grupos_fallidos: List[str] = []
    fields = contrato.get("fields", {})

    for grupo in sorted(contrato["groups"], key=lambda g: g["id"]):
        checks = checks_por_grupo.get(grupo["id"], [])
        grupo_ok = True
        for check in checks:
            estado = _evaluar_check(check, row, fields)
            resultado[check["name"]] = estado
            if estado not in _ESTADOS_NO_FALLO:
                grupo_ok = False

        if not grupo_ok:
            grupos_fallidos.append(grupo["name"])
            if grupo.get("stop_on_fail", True):
                break

    tiene_alerta = any(v == FIELD_NOT_IN_SOURCE for v in resultado.values())
    if grupos_fallidos:
        estado_global = "ERROR"
    elif tiene_alerta:
        estado_global = "ALERTA"
    else:
        estado_global = OK

    resultado["estado_validacion_global"] = estado_global
    resultado["detalle_validacion"] = ",".join(grupos_fallidos)
    return resultado


def apply_business_rules(contrato: Dict[str, Any]) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Construye la función para `dlt.resource.add_map()` ya cerrada sobre un
    contrato concreto."""

    def _map(row: Dict[str, Any]) -> Dict[str, Any]:
        row.update(validar_row(row, contrato))
        return row

    return _map
