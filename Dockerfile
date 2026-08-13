# Imagen de Airflow extendida con el provider de SSH (para el SSHOperator
# que dispara la extracción en VM-01) y un venv aislado para dbt.
#
# dbt no se instala en el mismo entorno de Airflow a propósito: evita
# conflictos entre el constraints file de Airflow y las dependencias de
# dbt-bigquery (ver docs/ARCHITECTURE.md sección "Orquestación (Airflow)").
# /opt/airflow ya es propiedad del usuario `airflow` en la imagen base, por
# eso el venv vive ahí en vez de en /opt directamente.
FROM apache/airflow:2.10.5-python3.12

COPY requirements-dbt.txt /tmp/requirements-dbt.txt

RUN python -m venv /opt/airflow/dbt_venv && \
    /opt/airflow/dbt_venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/airflow/dbt_venv/bin/pip install --no-cache-dir -r /tmp/requirements-dbt.txt

RUN pip install --no-cache-dir apache-airflow-providers-ssh==4.0.0
