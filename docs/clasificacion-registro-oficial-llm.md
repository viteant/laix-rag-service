# Clasificación jurídica de Registro Oficial mediante LLM

## Objetivo

Clasificar cada PDF descargado de Registro Oficial por su contenido jurídico y no por su contenedor editorial (`registro_oficial`, `suplementos`, etc.). El subtipo editorial se conserva como metadato técnico de origen; la clasificación jurídica se usa en el RAG y sus filtros.

Categorías permitidas:

```text
CONSTITUCION
LEY_ORGANICA
LEY_ORDINARIA
LEY_REFORMATORIA
CODIGO
DECRETO_EJECUTIVO
REGLAMENTO
ACUERDO_MINISTERIAL
ACUERDO
RESOLUCION
ORDENANZA
CIRCULAR
INSTRUCTIVO
NORMA_TECNICA
TRATADO_INTERNACIONAL
FE_DE_ERRATAS
AVISO
OTRO
```

Un ejemplar puede contener varias normas. Por ello se almacenará una categoría principal y una lista sin duplicados de categorías presentes. `OTRO` será la categoría exclusiva cuando no haya evidencia suficiente.

## Ubicación en el pipeline

Se añade una fase `classify_registro_oficial` con barrera de lote:

```text
download -> optimize -> extract_text -> classify_registro_oficial -> upload
-> verify_upload -> ingest_rag -> cleanup
```

La clasificación ocurre sobre el TXT ya extraído, nunca sobre el PDF original. No renombra ni altera PDFs, TXT ni el subtipo editorial. Al igual que las demás fases, procesa todos los activos elegibles antes de avanzar al siguiente paso.

Solo se ejecuta para `source_type=registro_oficial`. Jurisprudencia, documentos y leyes futuras no hacen llamadas al clasificador.

## Selección del texto a clasificar

1. Separar el TXT por marcadores `[[PAGE:n]]`.
2. Tomar como máximo `LLM_CLASSIFIER_MAX_INDEX_PAGES` páginas iniciales y limitar el contenido combinado a `LLM_CLASSIFIER_MAX_INPUT_CHARS`.
3. Aplicar una detección determinista de señales de índice: `ÍNDICE`, `INDICE`, `SUMARIO`, `CONTENIDO` y líneas que enumeren disposiciones con páginas.
4. En `source_subtype=indice_mensual`, no se invoca el LLM: se persiste `OTRO`, confianza `1.0` y método `rule_indice_mensual`.
5. Si no se detecta índice, se puede enviar el extracto inicial al LLM, indicando explícitamente que debe responder `OTRO` cuando no encuentre evidencia jurídica. Esto evita clasificaciones por suposiciones.

La extracción conserva los marcadores de página, para que el modelo pueda citar las páginas de evidencia. No se envían páginas posteriores ni el PDF a servicios externos.

## Contrato de salida del modelo

El adaptador exige JSON válido y valida su esquema antes de guardar datos:

```json
{
  "has_index": true,
  "primary_category": "LEY_ORGANICA",
  "categories": ["LEY_ORGANICA", "RESOLUCION"],
  "confidence": 0.91,
  "evidence": [
    {"category": "LEY_ORGANICA", "page": 1, "text": "LEY ORGÁNICA ..."}
  ]
}
```

Reglas de validación:

- Todas las categorías deben pertenecer al catálogo cerrado.
- `primary_category` debe estar en `categories`.
- `categories` no puede estar vacía ni repetida.
- `confidence` debe estar entre 0 y 1.
- La evidencia se limita a las páginas enviadas y a fragmentos cortos.
- Si `has_index=false`, el resultado válido por defecto es `OTRO`.

El prompt deberá prohibir inventar categorías, solicitar que clasifique solo lo visible y usar temperatura `0` por defecto. La versión del prompt se guarda con el resultado para poder auditar y reclasificar.

## Persistencia y metadatos RAG

Se añadirá un bloque `classification` a `pipeline_assets.metadata`, por ejemplo:

```json
{
  "classification": {
    "status": "classified",
    "method": "llm",
    "primary_category": "LEY_ORGANICA",
    "categories": ["LEY_ORGANICA", "RESOLUCION"],
    "confidence": 0.91,
    "model": "gpt-4.1-mini",
    "provider": "openai_compatible",
    "prompt_version": "registro-oficial-v1",
    "input_pages": [1, 2],
    "evidence": [{"category": "LEY_ORGANICA", "page": 1, "text": "LEY ORGÁNICA ..."}],
    "classified_at": "2026-07-27T00:00:00Z"
  }
}
```

No se requiere una columna nueva para la primera versión: `metadata` ya pertenece al activo, queda ligada a su identidad de descarga y permite la auditoría completa. Durante `ingest_rag`, este bloque se copia a `LegalCase.case_metadata` y a `LegalChunk.chunk_metadata`. La búsqueda vectorial añadirá el filtro opcional `registro_oficial_category`, que compara contra `chunk_metadata.categories`.

El diseño conserva `source_subtype` (suplemento, edición especial, etc.) separado de `categories`; ninguno reemplaza al otro en la base.

## Fallos y reintentos

- Un fallo de red, credenciales, timeout o JSON inválido no bloquea la carga del lote.
- Se guarda `status=fallback`, `method=fallback` y `categories=["OTRO"]`, junto al error técnico acotado.
- El panel podrá mostrar esos activos y ofrecer reclasificación. La reclasificación vuelve a ejecutar solo esta fase, sin redescargar ni renombrar archivos.
- Si `LLM_CLASSIFIER_ENABLED=false`, se omite el proveedor y se persiste `OTRO` con método `disabled`.

## Configuración por entorno

La implementación soportará adaptadores explícitos, configurables sin cambio de código:

```dotenv
# Clasificador jurídico de Registro Oficial
LLM_CLASSIFIER_ENABLED=false
LLM_CLASSIFIER_PROVIDER=openai_compatible
LLM_CLASSIFIER_MODEL=gpt-4.1-mini
LLM_CLASSIFIER_API_KEY=
LLM_CLASSIFIER_BASE_URL=https://api.openai.com/v1
LLM_CLASSIFIER_TIMEOUT_SECONDS=45
LLM_CLASSIFIER_TEMPERATURE=0
LLM_CLASSIFIER_MAX_INDEX_PAGES=3
LLM_CLASSIFIER_MAX_INPUT_CHARS=18000
LLM_CLASSIFIER_PROMPT_VERSION=registro-oficial-v1
```

Adaptadores previstos:

| `LLM_CLASSIFIER_PROVIDER` | Uso |
| --- | --- |
| `openai_compatible` | OpenAI y servicios compatibles con Chat Completions/JSON, cambiando `BASE_URL`, modelo y clave. |
| `openai` | Configuración abreviada de OpenAI; usa el mismo contrato estructurado. |
| `anthropic` | Adaptador Messages API con la misma salida JSON validada. |
| `ollama` | Modelo local mediante URL del servidor Ollama, sin enviar contenido a terceros. |

Las credenciales solo existirán en `.env`/GitHub Secrets; nunca en la base de datos, logs, correo ni respuestas de API.

## Plan de implementación

1. Añadir configuración y catálogo inmutable de categorías.
2. Implementar extracción de páginas iniciales, detector de índice y validador Pydantic del contrato JSON.
3. Implementar los adaptadores y un transporte inyectable para pruebas sin red.
4. Añadir la fase de clasificación y persistir el bloque de metadatos.
5. Propagar categorías al RAG y habilitar el filtro de búsqueda.
6. Mostrar estado, categoría, confianza y método en el frontend/panel.
7. Probar: índice simple, ejemplar mixto, `indice_mensual`, OCR, JSON inválido, timeout, proveedor deshabilitado y reintento.

## Criterios de aceptación

- Los documentos de Registro Oficial se clasifican solo con texto de páginas iniciales.
- `indice_mensual` siempre queda en `OTRO` sin consumo de LLM.
- Nunca se bloquea la carga/RAG por un fallo del clasificador.
- El resultado es trazable por modelo, prompt, evidencia y fecha.
- Las consultas RAG pueden filtrar por una o varias categorías sin perder el subtipo editorial.
- Los nombres de PDFs manuales y descargados no son alterados por esta funcionalidad.
