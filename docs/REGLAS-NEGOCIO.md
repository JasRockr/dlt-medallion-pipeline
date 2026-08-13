# REGLAS DE NEGOCIO - Parametrización Datos (Detalle Completo)

A continuación, se presenta la propuesta formal de **Reglas de Negocio (RN)** estructurada por categorías lógicas y ordenadas de forma secuencial.

El objetivo de esta estructura es que los dueños de los procesos puedan evaluar, ajustar y aprobar cada regla, sirviendo como base directa para la parametrización final de los módulos en Python.

> Nota: Este archivo contiene la versión completa y detallada de las reglas de negocio del dominio de ejemplo `business_partners` (contraparte cliente/proveedor/empleado — un concepto ERP/CRM estándar). Los formatos de documento de identidad y de teléfono usados aquí son **ilustrativos**, no atados a la regulación de un país específico — en un caso real se ajustan el regex/longitud de cada regla al país/jurisdicción de la implementación concreta. El patrón (dispatch por tipo de documento, contrato declarativo, motor de reglas genérico) es lo que se mantiene fijo.
> Si prefieres la vista operativa y resumida (cómo se interpretan estas reglas
> como contrato JSON, checks y grupos), consulta `docs/ARCHITECTURE.md`
> sección "El contrato (`contracts/<dominio>.json`)".

---

## Índice de Reglas

- RN-01: Control de Valores Genéricos (Comodines)
- RN-02: Limpieza de Caracteres Especiales
- RN-03: Validación de Identificación Tributaria (Organizaciones)
- RN-04: Validación de Documento de Identidad Nacional
- RN-05: Validación de Pasaportes
- RN-06: Validación de Permisos de Residencia (Extranjeros)
- RN-07: Permisos Especiales Temporales
- RN-08: Suficiencia en la Dirección
- RN-09: Obligatoriedad del País
- RN-10: Segmento de Cliente (Requerimiento de Reporte)
- RN-11: Categoría Fiscal
- RN-12: Segmentación de Nombres (Personas Naturales)
- RN-13: Control de Nombres de Prueba o Vacíos
- RN-14: Formato de Celular
- RN-15: Estructura de Correo Electrónico

## Categoría 1: Reglas de Identidad y Documentación (Estructura Crítica)

Esta categoría mitiga el riesgo de rechazo en reportes regulatorios/fiscales y asegura que la clasificación de personas naturales y organizaciones sea consistente en toda la base de datos.

### RN-01: Control de Valores Genéricos (Comodines)

- **Definición:** Queda prohibido el uso de identificaciones ficticias, de prueba o por defecto en el campo de identificación, restringiendo el uso de símbolos ajenos a las estructuras documentales estándar.

- **Criterio de Aceptación:** El campo `partner_id` no puede contener únicamente ceros (ej. `0`, `00000`), ni consecutivos o letras individuales de relleno como `1`, `no`, `SI`, `v`, `x`.

- El campo debe estar compuesto **únicamente** por caracteres alfanuméricos del alfabeto inglés (letras `A-Z`, `a-z`, números `0-9`) y el carácter especial guion medio (`-`). No se permite ningún otro símbolo, espacio intermedio o puntuación.

### RN-02: Limpieza de Caracteres Especiales

- **Definición:** Para cualquier documento que no sea una identificación tributaria de organización, se restringe el registro si contiene puntuación o símbolos ajenos a una estructura alfanumérica limpia.

- **Criterio de Aceptación:** El campo no debe tener caracteres especiales o símbolos de error (ej. `*`, `#`, `?`, `!`, `@`).

### RN-03: Validación de Identificación Tributaria (Organizaciones)

- **Definición:** Todo business partner registrado bajo un tipo de documento de familia `ID_TRIBUTARIO_ORG` debe corresponder a una organización (persona jurídica), no a un individuo.

- **Criterio de Aceptación (ilustrativo):** Debe tener exactamente **9 dígitos** y comenzar exclusivamente con **8 o 9**. El dígito de verificación (si el esquema de la jurisdicción real lo requiere) no se incluye en este campo principal — es un ejemplo de formato, ajustar al algoritmo real del país de implementación.

- **Excepción (multi-establecimiento):** Se permite la estructura extendida `XXXX-XX` (donde las X representan los dígitos numéricos base) únicamente para identificar sucursales/establecimientos que comparten una misma identificación tributaria raíz — un patrón común en ERPs multi-sucursal, no específico de ninguna empresa.

### RN-04: Validación de Documento de Identidad Nacional

- **Definición:** Las identificaciones de familia `ID_NACIONAL` clasifican automáticamente al business partner como persona natural (individuo).

- **Criterio de Aceptación (ilustrativo):** La longitud permitida debe ser estrictamente de **6, 7, 8 o 10 dígitos**.

- **Restricción de Inicio:** Si el documento tiene 10 dígitos, debe iniciar obligatoriamente con el número **1** (ejemplo de restricción de formato de un esquema nacional concreto).

- **Alerta de Inconsistencia:** Cualquier documento de este tipo con **9 dígitos** debe marcarse como "Error" (longitud fuera del rango válido del esquema de referencia).

### RN-05: Validación de Pasaportes

- **Definición:** El pasaporte identifica a un individuo fuera de su país de origen, o a un extranjero dentro del territorio local.
- **Criterio de Aceptación:** Debe ser un campo **alfanumérico** (puede contener letras y números).
- **Restricción de Longitud:** Debe tener una longitud entre **6 y 15 caracteres** (los formatos de pasaporte varían ampliamente entre países; este rango es deliberadamente amplio como ejemplo).
- **Limpieza:** No debe contener espacios intermedios, guiones, ni caracteres especiales (ej. `*`, `#`, `?`).

### RN-06: Validación de Permisos de Residencia (Extranjeros)

- **Definición:** Identificaciones otorgadas a extranjeros residentes por la autoridad migratoria local.

- **Criterio de Aceptación:** Históricamente constan de números de hasta 6 o 7 dígitos, pero pueden expandirse a estructuras alfanuméricas según el volumen migratorio.
- **Restricción de Longitud:** Debe tener una longitud mínima de **4 caracteres** y máxima de **12 caracteres**.

### RN-07: Permisos Especiales Temporales

- **Definición:** Permisos de permanencia/protección temporal otorgados por razones humanitarias, laborales o migratorias específicas.
- **Criterio de Aceptación:** Suelen tener estructuras numéricas o alfanuméricas largas y seriadas.
- **Restricción de Longitud:** Rango estricto entre **7 y 15 caracteres**. No pueden ser valores repetitivos (ej. `11111111`).

---

## Categoría 2: Reglas de Localización y Requerimientos de Reporte

Estas reglas aseguran que los reportes regulatorios/fiscales y de clasificación comercial no presenten estructuras vacías, y que la información de ubicación esté presente para la gestión comercial y de riesgo.

### RN-08: Suficiencia en la Dirección

- **Definición:** La dirección física es un campo obligatorio para reportes y correspondencia.

- **Criterio de Aceptación:** El texto ingresado debe tener una longitud **igual o superior a 8 caracteres**. Valores demasiado cortos para ser una dirección real deben rechazarse por insuficiencia.

### RN-09: Obligatoriedad del País

- **Definición:** Todo business partner en la base de datos debe contar con la información geográfica básica del país de residencia o constitución.

- **Criterio de Aceptación:** El campo `country` bajo ninguna circunstancia puede estar vacío o nulo.

### RN-10: Segmento de Cliente (Requerimiento de Reporte)

- **Definición:** Información indispensable para dar cumplimiento a reportes de clasificación/segmentación exigidos por un ente de control o por política interna de negocio.

- **Criterio de Aceptación:** El campo `customer_segment` debe estar completamente diligenciado y parametrizado con valores válidos.

- **Nota de arquitectura:** este campo es intencionalmente `available_in_source: false` en el contrato — ilustra el patrón de declarar un requisito de negocio en el contrato *antes* de que exista una columna real que lo alimente (ver `contracts/business_partners.json`).

### RN-11: Categoría Fiscal

- **Definición:** Atributo requerido para habilitar facturación y flujos fiscales/administrativos.

- **Criterio de Aceptación:** No se permiten business partners activos sin una categoría fiscal explícita y homologada ante la autoridad correspondiente.

---

## Categoría 3: Reglas de Higiene de Nombres y Clasificación

Orientada a eliminar los re-procesos manuales del equipo administrativo mediante la estandarización en la captura de datos, y a evitar que errores de digitación generen fricciones en la comunicación con el cliente.

### RN-12: Segmentación de Nombres (Personas Naturales)

- **Definición:** El nombre completo de las personas naturales debe estructurarse de forma dividida en la base de datos.

- **Criterio de Aceptación:** La información debe capturarse y separarse estrictamente de forma independiente en los campos: `last_name`, `second_last_name` (u otros apellidos), `first_name` y `middle_name` (u otros nombres).

### RN-13: Control de Nombres de Prueba o Vacíos

- **Definición:** Restricción de cadenas de texto que indican falta de gestión en el cargue masivo o manual.
- **Criterio de Aceptación:** Los campos de nombre no pueden contener términos como `"NO REGISTRA"`, `"PRUEBA"`, `"ABC PRUEBA"`, `"TEST AA"` o caracteres de error de encoding (ej. `?` en lugar de una tilde/ñ).

---

## Categoría 4: Reglas de Contactabilidad (Campos de Comunicación)

Estas reglas garantizan que las comunicaciones comerciales o de servicio lleguen efectivamente a su destino, evitando re-procesos manuales y quejas por falta de contacto.

### RN-14: Formato de Celular

- **Criterio de Aceptación (ilustrativo):** Debe tener una longitud exacta de 10 caracteres numéricos y comenzar estrictamente con un dígito de prefijo específico (`3` en este ejemplo — el formato real de número móvil varía por país, ajustar longitud/prefijo según el mercado de la implementación).
- **Exclusión:** Si contiene letras, espacios o símbolos, se descarta inmediatamente como "Inválido" por prioridad de evaluación.

### RN-15: Estructura de Correo Electrónico

- **Criterio de Aceptación:** Debe cumplir el formato estándar `nombre_usuario@dominio.extension`.

- **Filtro de Errores de Digitación:** Se rechazarán de manera automática correos con dominios mal escritos detectados en el análisis (ej. dominios terminados en `.como`, `.con`, o proveedores mutados como `gamil`, `0utlook`).

---

## Orden Secuencial de Evaluación Propuesto (Pipeline de Ejecución)

Para optimizar el rendimiento del script en Python, cada registro de business partner pasará por las categorías en el siguiente orden estricto de arriba hacia abajo, aplicando la detención temprana si falla una categoría crítica:

```txt
[Inicio de Evaluación]
       │
       ▼
1. Identidad y Documentación ──────► Si falla (RN-01 al RN-07) ──► Detiene fila y reporta error
       │
       ▼
2. Higiene de Nombres y Campos ────► Si falla (RN-12 o RN-13) ───► Detiene fila y reporta error
       │
       ▼
3. Requerimientos de Reporte ──────► Si falla (RN-08 al RN-11) ───► Detiene fila y reporta error
       │
       ▼
4. Contactabilidad ────────────────► Si falla (RN-14 o RN-15) ───► Detiene fila y reporta error
       │
       ▼
[Registro Validado - Estado: OK]

```

---

## Convención de Normalización de Columnas

Cuando una consulta no entregue exactamente el nombre canónico esperado por el contrato JSON, el pipeline puede aceptar un alias explícito definido en `contracts/<dataset>.json`.

**Regla operativa:**

- Si existe un alias permitido, el pipeline renombra la columna al nombre canónico y emite una alerta visible en consola y logs.
- Si no existe ni el nombre canónico ni un alias permitido, el pipeline falla temprano para evitar validaciones inconsistentes.
- El objetivo es que la consulta, el contrato y la validación converjan en un mismo vocabulario de negocio.

**Ejemplo aplicado:**

- Nombre canónico esperado: `created_by`
- Alias aceptado: `responsible_user`

**Acción recomendada si aparece la alerta:**

- Si el cambio es permanente, actualizar la consulta o el contrato JSON para reflejar el nombre definitivo.
- Si el alias es temporal, mantenerlo documentado en el contrato para que la operación sea trazable y no silenciosa.

---

## Cobertura Operativa Actual

El pipeline actual (`transforms/rule_engine.py`, interpretando
`contracts/business_partners.json`) genera estas columnas de validación directamente
sobre la tabla `business_partners` en BigQuery (dataset `business_partners_data`), inyectadas
por dlt en tiempo de carga — no hay salidas intermedias en archivos:

- `VALIDACION_DOC_ESTRUCTURA`
- `VALIDACION_CELULAR`
- `VALIDACION_EMAIL`
- `VALIDACION_NOMBRE`
- `VALIDACION_SEGMENTACION_NOMBRES`
- `VALIDACION_CARACTERES_PARTNER_ID`
- `VALIDACION_CARACTERES_NOMBRE`
- `VALIDACION_CARACTERES_CELULAR`
- `VALIDACION_CARACTERES_EMAIL`
- `VALIDACION_CARACTERES_USUARIO`
- `VALIDACION_DIRECCION`
- `VALIDACION_PAIS`
- `VALIDACION_SEGMENTO`
- `VALIDACION_CATEGORIA_FISCAL`

Más `estado_validacion_global` y `detalle_validacion` (resumen por fila) y
la vista agregada `business_partners_data.resumen_ejecucion_business_partners`. Esquema
completo de cómo se generan estas columnas: `docs/ARCHITECTURE.md`
secciones "El contrato" y "Estados posibles de un check".

En términos prácticos, esto cubre las RN de identidad, nombres, contactabilidad, localización, categoría fiscal y control de caracteres que están definidas en este documento, con excepción de reglas puramente descriptivas o dependientes de criterios manuales del negocio que puedan requerir ajuste fino de parametrización en el contrato JSON.
