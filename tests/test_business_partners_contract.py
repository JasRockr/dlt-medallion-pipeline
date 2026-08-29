"""Prueba de regresión: contracts/business_partners.json + el motor genérico
deben seguir produciendo los mismos resultados frente a un set de casos
sintéticos que cubren cada categoría de falla (identidad/documentación,
higiene de nombres, requerimientos de reporte, contactabilidad).

Todos los valores de este archivo son ficticios -- generados para ejercitar
cada regla, no datos de ninguna persona ni organización real."""

import json
from pathlib import Path

import pytest

from transforms.rule_engine import validar_row

CONTRACT_PATH = Path(__file__).parent.parent / "contracts" / "business_partners.json"


@pytest.fixture(scope="module")
def contrato():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


CASOS_SINTETICOS = [
    # (row, estado_esperado, detalle_esperado)
    (
        {"partner_id": "", "document_type": "13", "full_name": "", "address": "MAIN ST 12",
         "country": 1, "is_individual": "Y", "first_name": "", "last_name": "",
         "mobile_phone": None, "email": None, "created_by": "sa"},
        "ERROR", "IDENTIDAD_DOCUMENTACION",
    ),
    (
        {"partner_id": "00000", "document_type": "13", "full_name": "DOE JANE", "address": "Apartado ",
         "country": 1, "is_individual": None, "first_name": "JANE", "last_name": "DOE",
         "mobile_phone": "1234567890", "email": None, "created_by": "System Admin"},
        "ERROR", "IDENTIDAD_DOCUMENTACION",
    ),
    (
        {"partner_id": "0054321", "document_type": "13", "full_name": "PRUEBA PRUEBA",
         "address": "SPRINGFIELD", "country": 1, "is_individual": None, "first_name": "PRUEBA",
         "last_name": "PRUEBA", "mobile_phone": "3040000000",
         "email": "test.placeholder@example.com", "created_by": "Ops Admin"},
        "ERROR", "HIGIENE_NOMBRES",
    ),
    (
        {"partner_id": "019125665", "document_type": "13", "full_name": "SMITH JOHN ALEXANDER",
         "address": "123 MAIN STREET APT 4", "country": 1, "is_individual": None, "first_name": "JOHN",
         "last_name": "SMITH", "mobile_phone": "3154440094", "email": "test.partner4@example.com",
         "created_by": "QA Team"},
        "ERROR", "IDENTIDAD_DOCUMENTACION",
    ),
    (
        {"partner_id": "900123456", "document_type": "31", "full_name": "ACME TESTING CORP",
         "address": "456 INDUSTRIAL AVE", "country": 1, "is_individual": None, "first_name": None,
         "last_name": None, "mobile_phone": "3001234567", "email": "contact@example.com",
         "created_by": "admin"},
        "ALERTA", "",
    ),
    (
        {"partner_id": "049424096", "document_type": "41", "full_name": "GARC?A TESTING",
         "address": "789 SOUTH BLVD", "country": 1, "is_individual": None, "first_name": "TESTING",
         "last_name": "GARC?A", "mobile_phone": "3046337377", "email": "test.encoding@example.com",
         "created_by": "QA Team"},
        "ERROR", "HIGIENE_NOMBRES",
    ),
    (
        {"partner_id": "8027483", "document_type": "47", "full_name": "DOE JANE TEMP",
         "address": "10 NORTH STREET", "country": 1, "is_individual": "Y", "first_name": "JANE",
         "last_name": "DOE", "mobile_phone": "3043629634", "email": "test.partner7@gamil.com",
         "created_by": "QA Team"},
        "ERROR", "CONTACTABILIDAD",
    ),
]


@pytest.mark.parametrize("row,estado_esperado,detalle_esperado", CASOS_SINTETICOS)
def test_casos_sinteticos_regresion(contrato, row, estado_esperado, detalle_esperado):
    resultado = validar_row(row, contrato)
    assert resultado["estado_validacion_global"] == estado_esperado
    assert resultado["detalle_validacion"] == detalle_esperado


def test_ningun_business_partner_puede_quedar_ok_mientras_falten_segmento_y_categoria_fiscal(contrato):
    """RN-10/RN-11 alertan siempre (gap de esquema documentado); por diseño,
    el máximo estado alcanzable hoy es ALERTA, nunca OK puro."""
    fila_perfecta = {
        "partner_id": "900123456", "document_type": "31", "full_name": "ACME TESTING CORP",
        "address": "456 INDUSTRIAL AVE", "country": 1, "is_individual": None,
        "mobile_phone": "3001234567", "email": "contact@example.com", "created_by": "admin",
    }
    resultado = validar_row(fila_perfecta, contrato)
    assert resultado["estado_validacion_global"] == "ALERTA"
