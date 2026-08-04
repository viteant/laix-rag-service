# API pública del RAG jurídico

Base URL de producción: `https://api.viant.online`.

La documentación interactiva generada por FastAPI está disponible en:

- `GET /docs`: Swagger UI.
- `GET /openapi.json`: contrato OpenAPI en JSON.
- `GET /health`: estado público del servicio y de PostgreSQL/pgvector.

## Alcance público

La API de consulta se publica bajo `/v1/jurisprudence`. Aunque el nombre del
recurso se mantiene por compatibilidad, la búsqueda cubre los documentos que
ya estén indexados en el RAG: jurisprudencia, documentos y Registro Oficial.

Los endpoints `/v1/admin` y `/v1/admin/pipeline` son operativos: registran
archivos ubicados dentro del servidor, administran lotes y pueden disparar
trabajo intensivo. No deben ser consumidos desde un navegador de terceros ni
usarse como interfaz pública del producto.

## Autenticación

Los endpoints protegidos aceptan `Authorization: Bearer <JWT>`. El JWT se
obtiene con un `client_id` y un `client_secret` previamente registrados en la
tabla `api_clients`.

```bash
export API_BASE='https://api.viant.online'
export CLIENT_ID='rag_frontend_prod'
export CLIENT_SECRET='guarda_este_valor_fuera_de_git'

TOKEN=$(curl --fail-with-body -sS "$API_BASE/v1/auth/token" \
  -H 'Content-Type: application/json' \
  -d "{\"client_id\":\"$CLIENT_ID\",\"client_secret\":\"$CLIENT_SECRET\"}" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

La respuesta incluye `access_token`, `token_type` (`bearer`) y `expires_in`.
Cuando expire, solicita otro token: no almacenes el JWT como secreto de largo
plazo.

### Crear el primer cliente (solo administrador del VPS)

Ejecuta esto una única vez desde `/opt/laix-rag`. Imprime el secreto solo en la
terminal; cópialo a un gestor de secretos y no lo subas a Git.

```bash
sudo docker compose -f docker-compose.prod.yml exec -T api python -c '
import secrets
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.database.models import ApiClient
db = SessionLocal()
client_id = "rag_frontend_prod"
try:
    if db.query(ApiClient).filter_by(client_id=client_id).first():
        raise SystemExit("El cliente ya existe; no se modificó nada.")
    client_secret = secrets.token_urlsafe(32)
    db.add(ApiClient(
        client_id=client_id,
        hashed_secret=get_password_hash(client_secret),
        name="Frontend producción",
        is_active=True,
    ))
    db.commit()
    print("CLIENT_ID=" + client_id)
    print("CLIENT_SECRET=" + client_secret)
finally:
    db.close()
'
```

## Consultas

### Salud

```bash
curl --fail-with-body -sS "$API_BASE/health"
```

Debe responder `status: "healthy"`, `database: "ok"` y
`pgvector_extension: true`.

### Búsqueda semántica

`POST /v1/jurisprudence/search`

```bash
curl --fail-with-body -sS "$API_BASE/v1/jurisprudence/search" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "¿Qué criterios existen sobre la motivación de sentencias?",
    "limit": 5
  }'
```

Campos opcionales de `filters`:

```json
{
  "legal_area": "Laboral y Social",
  "case_number": "319-2011",
  "source_type": "jurisprudence"
}
```

`limit` acepta valores entre 1 y 50. La respuesta devuelve la consulta,
`count` y la lista `results`. Conserva el identificador de caso o documento de
un resultado para solicitar su detalle.

### Respuesta generada con RAG

`POST /v1/jurisprudence/answer`

```bash
curl --fail-with-body -sS "$API_BASE/v1/jurisprudence/answer" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "¿Qué requisitos exige la motivación de una sentencia?",
    "top_k": 5
  }'
```

`top_k` acepta valores entre 1 y 20. La respuesta se fundamenta solo en los
fragmentos recuperados; el cliente debe mostrar las fuentes retornadas y no
presentarla como asesoría jurídica definitiva.

### Detalle y trazabilidad

```bash
# Sustituye con un ID recibido en búsqueda/respuesta.
export CASE_ID='uuid-del-caso'
curl --fail-with-body -sS \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/v1/jurisprudence/cases/$CASE_ID"

export DOCUMENT_ID='uuid-del-documento'
curl --fail-with-body -sS \
  -H "Authorization: Bearer $TOKEN" \
  "$API_BASE/v1/jurisprudence/documents/$DOCUMENT_ID"
```

El detalle de caso expone materia, órgano, fechas, páginas y metadatos. El
detalle de documento expone el SHA-256, estado de procesamiento, páginas y los
casos detectados. Ambos devuelven `404` si el UUID no existe.

## Prueba mínima de extremo a extremo

1. Abre `https://api.viant.online/docs` y verifica que cargue con HTTPS.
2. Ejecuta la comprobación de salud.
3. Crea el cliente administrativo solo si aún no existe; guarda el secreto.
4. Solicita un token y ejecuta `/search` con una consulta amplia.
5. Usa un ID retornado para consultar el detalle.
6. Ejecuta `/answer` solo cuando quieras probar la generación; consume más
   recursos que `/search`.

Errores esperados:

- `401`: falta el Bearer o el token/credenciales son inválidos.
- `404`: el caso o documento solicitado no existe.
- `422`: cuerpo JSON inválido o `limit`/`top_k` fuera de rango.
- `5xx`: conserva la hora, endpoint y cuerpo del error; no reintentes en un
  bucle, especialmente mientras el RAG está indexando.

## Recomendaciones para el frontend

- Guarda `CLIENT_SECRET` exclusivamente en el backend/BFF, nunca en el
  navegador, una app móvil distribuida ni un repositorio.
- El frontend llama a su BFF; el BFF obtiene y renueva el JWT ante esta API.
- Ante `401`, renueva el JWT una vez y repite la solicitud una sola vez.
- Configura Cloudflare en modo **Full (strict)** para conservar la validación
  TLS hasta el origen.
