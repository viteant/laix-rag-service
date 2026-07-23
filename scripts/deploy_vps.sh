#!/usr/bin/env bash
set -e

REPO_NAME="${1:-viteant/laix-rag-service}"
GH_TOKEN="$2"

echo "🚀 Iniciando Despliegue Automático en VPS (Usuario: $USER)..."

# Determinar prefijo sudo si no somos root
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
else
  SUDO=""
fi

# 1. Crear directorio de producción
$SUDO mkdir -p /opt/laix-rag
$SUDO chown -R "$USER:$USER" /opt/laix-rag
cd /opt/laix-rag

# 2. Configurar autenticación para repositorios privados con GITHUB_TOKEN
if [ -n "$GH_TOKEN" ]; then
  AUTH_URL="https://x-access-token:${GH_TOKEN}@github.com/${REPO_NAME}.git"
else
  AUTH_URL="https://github.com/${REPO_NAME}.git"
fi

# Clonar si no existe .git o hacer pull si existe
if [ ! -d ".git" ]; then
  echo "📥 Clonando repositorio privado $REPO_NAME por primera vez..."
  git clone "$AUTH_URL" .
else
  git remote set-url origin "$AUTH_URL"
fi

git fetch --all
git reset --hard origin/main

# Omitir el token de las URLs remotas en disco por seguridad
git remote set-url origin "https://github.com/${REPO_NAME}.git"

# 3. Escribir archivo .env desde secret de GitHub
if [ -n "$ENV_CONTENT" ]; then
  echo "$ENV_CONTENT" > .env
  echo "⚙️ Archivo .env de producción actualizado."
else
  echo "⚠️ Advertencia: ENV_CONTENT no fue provisto. Manteniendo .env existente."
fi

# 4. Compilar y levantar contenedores en producción
echo "🐳 Ejecutando Docker Compose..."
if command -v docker-compose &> /dev/null; then
  DOCKER_COMPOSE_CMD="docker-compose"
else
  DOCKER_COMPOSE_CMD="docker compose"
fi

$SUDO $DOCKER_COMPOSE_CMD -f docker-compose.prod.yml up -d --build

# 5. Limpiar imágenes huérfanas
$SUDO docker image prune -f || true

# 6. Comprobar salud del servicio
echo "⏳ Verificando salud del servicio..."
sleep 5
HEALTH_STATUS=$(curl -s http://localhost/health | grep -o '"status":"healthy"' || true)

if [ "$HEALTH_STATUS" = '"status":"healthy"' ]; then
  echo "✅ Despliegue exitoso. El servicio RAG responde 'healthy'."
else
  echo "❌ Advertencia: La verificación de salud devolvió un estado no esperado."
fi