{#
    Override estándar de dbt: usa el `+schema` del modelo tal cual (sin
    concatenarlo con el dataset del target, que es el comportamiento por
    defecto). Así `+schema: staging_business_partners` en dbt_project.yml
    produce exactamente el dataset `staging_business_partners` en BigQuery,
    no `<target_dataset>_staging_business_partners`.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set default_schema = target.schema -%}
    {%- if custom_schema_name is none -%}
        {{ default_schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
