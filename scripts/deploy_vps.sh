#!/usr/bin/env bash
set -e

REPO_NAME="$1"
ENV_CONTENT="$2"

echo "🚀 Iniciando Despliegue Automático en VPS..."

# 1. Crear directorio de producción
mkdir -p /opt/laix-rag
cd /opt/laix-rag

# 2. Clonar si no existe .git o hacer pull si existe
if [ ! -d ".git" ]; then
  echo "📥 Clonando repositorio $REPO_NAME por primera vez..."
  git clone "https://github.com/${REPO_NAME}.git" .
fi

git fetch --all
git reset --hard origin/main

# 3. Escribir archivo .env desde secret de GitHub
if [ -n "$ENV_CONTENT" ]; then
  echo "$ENV_CONTENT" > .env
  echo "⚙️ Archivo .env de producción actualizado."
fi

# 4. Compilar y levantar contenedores en producción
echo "🐳 Ejecutando Docker Compose..."
docker compose -f docker-compose.prod.yml up -d --build

# 5. Limpiar imágenes huérfanas
docker image prune -f

# 6. Comprobar salud del servicio
echo "⏳ Verificando salud del servicio..."
sleep 5
HEALTH_STATUS=$(curl -s http://localhost/health | grep -o '"status":"healthy"' || true)

if [ "$HEALTH_STATUS" = '"status":"healthy"' ]; then
  echo "✅ Despliegue exitoso. El servicio RAG responde 'healthy'."
else
  echo "❌ Advertencia: La verificación de salud devolvió un estado no esperado."
fi
