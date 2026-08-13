{{ config(materialized='table') }}

-- Gold: equivalente a la vista dinámica resumen_ejecucion_business_partners
-- (transforms/domains/business_partners/views.py), pero leyendo de la capa
-- silver (stg_business_partners__business_partners) en vez de bronze
-- directamente -- completa el linaje bronze -> staging -> marts.
--
-- Criterio de paridad antes de retirar la vista dinámica (ver
-- docs/ARCHITECTURE.md): este modelo debe producir el mismo conteo y los
-- mismos valores agregados que la vista actual durante varias corridas
-- consecutivas.

select
    estado_validacion_global,
    detalle_validacion,
    count(*) as total_business_partners,
    countif(VALIDACION_CARACTERES_PARTNER_ID not in ('OK', 'NO_EVALUADO')) as errores_caracteres_partner_id,
    countif(VALIDACION_DOC_ESTRUCTURA not in ('OK', 'NO_EVALUADO')) as errores_doc_estructura,
    countif(VALIDACION_NOMBRE not in ('OK', 'NO_EVALUADO')) as errores_nombre,
    countif(VALIDACION_SEGMENTACION_NOMBRES = 'ERROR_NOMBRE_NO_SEGMENTADO') as errores_segmentacion,
    countif(VALIDACION_DIRECCION not in ('OK', 'NO_EVALUADO')) as errores_direccion,
    countif(VALIDACION_PAIS not in ('OK', 'NO_EVALUADO')) as errores_pais,
    countif(VALIDACION_CELULAR not in ('OK', 'NO_EVALUADO')) as errores_celular,
    countif(VALIDACION_EMAIL not in ('OK', 'NO_EVALUADO')) as errores_email
from {{ ref('stg_business_partners__business_partners') }}
group by estado_validacion_global, detalle_validacion
