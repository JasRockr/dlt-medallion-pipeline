"""Pruebas de los plugins bespoke del dominio Business Partners (la parte
que no es expresable con operadores genéricos: dispatch por tipo de
documento y segmentación de nombres condicional)."""

import pytest

from transforms.domains.business_partners.plugins import (
    validar_doc_estructura,
    validar_segmentacion_nombres,
)
from transforms.rule_engine import NOT_APPLICABLE


@pytest.mark.parametrize(
    "partner_id,document_type,esperado",
    [
        ("900123456", "31", "OK"),  # ID tributario de organización válido
        ("900123456-01", "31", "OK"),  # con sufijo de establecimiento
        ("12345678", "31", "ERROR_FORMATO_ID_TRIBUTARIO"),  # no empieza en 8/9
        ("12345678", "13", "OK"),  # ID nacional, 8 dígitos
        ("123456789", "13", "ERROR_LONGITUD_INEXISTENTE"),  # 9 dígitos: longitud fuera de rango
        ("1123456789", "13", "OK"),  # ID nacional 10 dígitos empezando en 1
        ("2123456789", "13", "ERROR_INICIO_ID_NACIONAL"),  # 10 dígitos sin empezar en 1
        ("12345", "13", "ERROR_LONGITUD_ID_NACIONAL"),  # longitud no permitida
        ("AB1234567", "41", "OK"),  # pasaporte alfanumérico
        ("AB", "41", "ERROR_FORMATO_PASAPORTE"),  # muy corto
        ("1234567", "22", "OK"),  # permiso de residencia extranjera
        ("8027483", "47", "OK"),  # permiso especial temporal
        ("11111111", "47", "ERROR_FORMATO_PERMISO_TEMPORAL"),  # repetido
        ("000111", "11", "OK"),  # registro civil: sin regla de longitud específica
        ("123", "99", "ERROR_TIPO_DOCUMENTO_DESCONOCIDO"),  # código no catalogado
        ("123", "", "ERROR_TIPO_DOCUMENTO_FALTANTE"),
    ],
)
def test_validar_doc_estructura(partner_id, document_type, esperado):
    row = {"partner_id": partner_id, "document_type": document_type}
    assert validar_doc_estructura(row) == esperado


def test_segmentacion_nombres_organizacion_no_aplica():
    row = {"is_individual": None, "first_name": None, "last_name": None}
    assert validar_segmentacion_nombres(row) == NOT_APPLICABLE


def test_segmentacion_nombres_persona_natural_ok():
    row = {"is_individual": "Y", "first_name": "JUAN", "last_name": "PEREZ"}
    assert validar_segmentacion_nombres(row) == "OK"


def test_segmentacion_nombres_persona_natural_sin_segmentar():
    row = {"is_individual": "Y", "first_name": None, "last_name": None}
    assert validar_segmentacion_nombres(row) == "ERROR_NOMBRE_NO_SEGMENTADO"
