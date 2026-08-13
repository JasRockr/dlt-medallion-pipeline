{{
  config(
    materialized='table',
    partition_by={'field': 'created_at', 'data_type': 'date', 'granularity': 'day'},
    cluster_by=['document_type']
  )
}}

-- Silver: tabla `business_partners` (bronze) enriquecida con las
-- descripciones de sus catálogos de referencia (docs/business-partners-schema.dbml).
-- Las columnas VALIDACION_*/estado_validacion_global/detalle_validacion ya
-- vienen calculadas desde bronze (transforms/rule_engine.py) -- aquí no se
-- reevalúa ninguna regla de negocio, solo se resuelven códigos a descripción.
-- `accounts` se deja fuera del join: no tiene columna descriptiva en el esquema.

with business_partners as (
    select * from {{ source('business_partners_bronze', 'business_partners') }}
)

select
    bp.partner_id,
    bp.full_name,
    bp.first_name,
    bp.middle_name,
    bp.last_name,
    bp.second_last_name,
    bp.is_individual,
    bp.address,
    bp.mobile_phone,
    bp.email,
    bp.status,

    bp.document_type,
    dt.description as document_type_description,

    bp.country_id,
    c.description as country_description,

    bp.city_id,
    ci.description as city_description,

    bp.organization_type,
    ot.description as organization_type_description,

    bp.tax_regime,
    tr.description as tax_regime_description,

    bp.marital_status,
    ms.description as marital_status_description,

    bp.partner_category,
    pc.description as partner_category_description,

    bp.list_id,
    rl.description as list_description,

    bp.economic_activity,
    ea.description as economic_activity_description,

    bp.zone_id,
    sz.description as zone_description,

    bp.sales_rep_id,
    sr.description as sales_rep_description,

    bp.service_agent_id,
    sa.description as service_agent_description,

    bp.bank_id,
    bk.description as bank_description,

    bp.chain_id,
    pch.description as chain_description,

    bp.account_id,
    bp.created_by,
    bp.created_at,

    -- columnas de validación inyectadas en bronze por el motor de reglas
    bp.VALIDACION_CARACTERES_PARTNER_ID,
    bp.VALIDACION_DOC_ESTRUCTURA,
    bp.VALIDACION_CARACTERES_NOMBRE,
    bp.VALIDACION_NOMBRE,
    bp.VALIDACION_SEGMENTACION_NOMBRES,
    bp.VALIDACION_DIRECCION,
    bp.VALIDACION_PAIS,
    bp.VALIDACION_SEGMENTO,
    bp.VALIDACION_CATEGORIA_FISCAL,
    bp.VALIDACION_CARACTERES_CELULAR,
    bp.VALIDACION_CELULAR,
    bp.VALIDACION_CARACTERES_EMAIL,
    bp.VALIDACION_EMAIL,
    bp.VALIDACION_CARACTERES_USUARIO,
    bp.estado_validacion_global,
    bp.detalle_validacion

from business_partners bp
left join {{ source('business_partners_bronze', 'document_types') }} dt on bp.document_type = dt.document_type
left join {{ source('business_partners_bronze', 'countries') }} c on bp.country_id = c.country_id
left join {{ source('business_partners_bronze', 'cities') }} ci on bp.city_id = ci.city_id
left join {{ source('business_partners_bronze', 'organization_types') }} ot on bp.organization_type = ot.organization_type
left join {{ source('business_partners_bronze', 'tax_regimes') }} tr on bp.tax_regime = tr.tax_regime
left join {{ source('business_partners_bronze', 'marital_statuses') }} ms on bp.marital_status = ms.marital_status
left join {{ source('business_partners_bronze', 'partner_categories') }} pc on bp.partner_category = pc.partner_category
left join {{ source('business_partners_bronze', 'reference_lists') }} rl on bp.list_id = rl.list_id
left join {{ source('business_partners_bronze', 'economic_activities') }} ea on bp.economic_activity = ea.economic_activity
left join {{ source('business_partners_bronze', 'sales_zones') }} sz on bp.zone_id = sz.zone_id
left join {{ source('business_partners_bronze', 'sales_reps') }} sr on bp.sales_rep_id = sr.sales_rep_id
left join {{ source('business_partners_bronze', 'service_agents') }} sa on bp.service_agent_id = sa.service_agent_id
left join {{ source('business_partners_bronze', 'banks') }} bk on bp.bank_id = bk.bank_id
left join {{ source('business_partners_bronze', 'partner_chains') }} pch on bp.chain_id = pch.chain_id
