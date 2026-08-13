"""Vistas 'gold' del dominio Business Partners. Ver transforms/bigquery_gold.py
para el helper genérico que las crea/actualiza."""

RESUMEN_EJECUCION_SQL = """
CREATE OR REPLACE VIEW `{project}.{dataset}.resumen_ejecucion_business_partners` AS
SELECT
  estado_validacion_global,
  detalle_validacion,
  COUNT(*) AS total_business_partners,
  COUNTIF(VALIDACION_CARACTERES_PARTNER_ID NOT IN ('OK', 'NO_EVALUADO')) AS errores_caracteres_partner_id,
  COUNTIF(VALIDACION_DOC_ESTRUCTURA NOT IN ('OK', 'NO_EVALUADO')) AS errores_doc_estructura,
  COUNTIF(VALIDACION_NOMBRE NOT IN ('OK', 'NO_EVALUADO')) AS errores_nombre,
  COUNTIF(VALIDACION_SEGMENTACION_NOMBRES = 'ERROR_NOMBRE_NO_SEGMENTADO') AS errores_segmentacion,
  COUNTIF(VALIDACION_DIRECCION NOT IN ('OK', 'NO_EVALUADO')) AS errores_direccion,
  COUNTIF(VALIDACION_PAIS NOT IN ('OK', 'NO_EVALUADO')) AS errores_pais,
  COUNTIF(VALIDACION_CELULAR NOT IN ('OK', 'NO_EVALUADO')) AS errores_celular,
  COUNTIF(VALIDACION_EMAIL NOT IN ('OK', 'NO_EVALUADO')) AS errores_email
FROM `{project}.{dataset}.business_partners`
GROUP BY estado_validacion_global, detalle_validacion
"""

GOLD_VIEWS = {
    "resumen_ejecucion_business_partners": RESUMEN_EJECUCION_SQL,
}
