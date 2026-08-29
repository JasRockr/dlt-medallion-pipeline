"""Pruebas del motor de reglas genérico. No dependen de ningún dominio de
negocio real — usan contratos sintéticos pequeños construidos en el propio
test (ver tests/test_business_partners_contract.py para pruebas contra el
contrato del dominio de ejemplo Business Partners)."""

import pytest

from transforms.rule_engine import (
    FIELD_NOT_IN_SOURCE,
    NOT_APPLICABLE,
    OK,
    validar_row,
)


def _contrato(checks, groups=None):
    return {
        "fields": {},
        "groups": groups or [{"id": 1, "name": "G1", "stop_on_fail": True}],
        "checks": checks,
    }


@pytest.mark.parametrize(
    "op,params,valor,esperado",
    [
        ("not_null", {}, "x", True),
        ("not_null", {}, "", False),
        ("regex", {"pattern": "^[0-9]+$"}, "123", True),
        ("regex", {"pattern": "^[0-9]+$"}, "12a", False),
        ("length", {"eq": 3}, "abc", True),
        ("length", {"eq": 3}, "ab", False),
        ("length", {"min": 2, "max": 4}, "abc", True),
        ("length", {"min": 2, "max": 4}, "a", False),
        ("range", {"min": 0, "max": 10}, "5", True),
        ("range", {"min": 0, "max": 10}, "11", False),
        ("range", {"min": 0, "max": 10}, "abc", False),
        ("enum", {"values": ["A", "B"]}, "A", True),
        ("enum", {"values": ["A", "B"]}, "C", False),
        ("not_in", {"values": ["no", "si"]}, "no", False),
        ("not_in", {"values": ["no", "si"]}, "NO", False),
        ("starts_with", {"prefix": "3"}, "3001234567", True),
        ("starts_with", {"prefix": "3"}, "1001234567", False),
        ("not_ends_with", {"values": [".con"]}, "a@b.com", True),
        ("not_ends_with", {"values": [".con"]}, "a@b.con", False),
        ("not_contains", {"values": ["gamil"]}, "x@gmail.com", True),
        ("not_contains", {"values": ["gamil"]}, "x@gamil.com", False),
        ("digits_only", {}, "12345", True),
        ("digits_only", {}, "123a5", False),
        ("alnum", {"extra_chars": "-"}, "abc-123", True),
        ("alnum", {"extra_chars": "-"}, "abc_123", False),
        ("not_repeated_char", {}, "00000", False),
        ("not_repeated_char", {}, "01000", True),
        ("no_spaces", {}, "abc", True),
        ("no_spaces", {}, "a b", False),
    ],
)
def test_operador(op, params, valor, esperado):
    contrato = _contrato([{"name": "V", "group": 1, "inputs": ["f"], "rules": [{"op": op, **params}]}])
    resultado = validar_row({"f": valor}, contrato)
    assert (resultado["V"] == OK) is esperado


def test_grupo_detiene_evaluacion_de_siguientes_grupos():
    contrato = _contrato(
        [
            {"name": "V1", "group": 1, "inputs": ["a"], "rules": [{"op": "not_null"}]},
            {"name": "V2", "group": 2, "inputs": ["b"], "rules": [{"op": "not_null"}]},
        ],
        groups=[
            {"id": 1, "name": "G1", "stop_on_fail": True},
            {"id": 2, "name": "G2", "stop_on_fail": True},
        ],
    )
    resultado = validar_row({"a": "", "b": "x"}, contrato)
    assert resultado["V1"] != OK
    assert resultado["V2"] == "NO_EVALUADO"
    assert resultado["estado_validacion_global"] == "ERROR"
    assert resultado["detalle_validacion"] == "G1"


def test_grupo_sin_stop_on_fail_continua():
    contrato = _contrato(
        [
            {"name": "V1", "group": 1, "inputs": ["a"], "rules": [{"op": "not_null"}]},
            {"name": "V2", "group": 2, "inputs": ["b"], "rules": [{"op": "not_null"}]},
        ],
        groups=[
            {"id": 1, "name": "G1", "stop_on_fail": False},
            {"id": 2, "name": "G2", "stop_on_fail": True},
        ],
    )
    resultado = validar_row({"a": "", "b": "x"}, contrato)
    assert resultado["V1"] != OK
    assert resultado["V2"] == OK


def test_campo_no_disponible_en_origen_alerta_y_no_cuenta_como_fallo():
    contrato = _contrato(
        [{"name": "V1", "group": 1, "inputs": ["a"], "rules": []}],
    )
    contrato["fields"]["a"] = {"available_in_source": False}
    resultado = validar_row({}, contrato)
    assert resultado["V1"] == FIELD_NOT_IN_SOURCE
    assert resultado["estado_validacion_global"] == "ALERTA"


def test_not_applicable_no_cuenta_como_fallo():
    def _plugin_siempre_no_aplica(row):
        return NOT_APPLICABLE

    import sys
    import types

    modulo = types.ModuleType("_plugin_test_mod")
    modulo.fn = _plugin_siempre_no_aplica
    sys.modules["_plugin_test_mod"] = modulo

    contrato = _contrato(
        [{"name": "V1", "group": 1, "inputs": ["a"], "plugin": "_plugin_test_mod:fn"}],
    )
    resultado = validar_row({"a": "x"}, contrato)
    assert resultado["V1"] == NOT_APPLICABLE
    assert resultado["estado_validacion_global"] == OK


def test_valores_vacios_se_omiten_sin_not_null() -> None:
    contrato = _contrato(
        [{"name": "V1", "group": 1, "inputs": ["a"], "rules": [{"op": "digits_only"}]}],
    )
    resultado = validar_row({"a": ""}, contrato)
    assert resultado["V1"] == OK


def test_error_code_personalizado() -> None:
    contrato = _contrato(
        [{"name": "V1", "group": 1, "inputs": ["a"],
          "rules": [{"op": "not_null", "error_code": "MI_ERROR"}]}],
    )
    resultado = validar_row({"a": ""}, contrato)
    assert resultado["V1"] == "MI_ERROR"
