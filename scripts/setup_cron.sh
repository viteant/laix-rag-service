#!/usr/bin/env bash
set -e

echo "🛠️ Configurando Cronjob para el Scraper del Registro Oficial..."

# Obtener la ruta absoluta del directorio actual
PROJECT_DIR="$(pwd)"
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python"

# Validar que exista el entorno virtual
if [ ! -f "$VENV_PYTHON" ]; then
  echo "❌ Error: No se encontró el entorno virtual en $VENV_PYTHON"
  echo "Por favor, crea el entorno virtual (python -m venv .venv) e instala las dependencias (pip install .) antes de configurar el cron."
  exit 1
fi

# Validar que exista el script del scraper
SCRAPER_SCRIPT="${PROJECT_DIR}/scripts/scraper_registro_oficial.py"
if [ ! -f "$SCRAPER_SCRIPT" ]; then
  echo "❌ Error: No se encontró el script del scraper en $SCRAPER_SCRIPT"
  exit 1
fi

# Crear el comando cron (Día 1 de cada mes a las 00:00)
# Se usa 'cd' para asegurar que el script corre desde la raíz del proyecto
CRON_CMD="0 0 1 * * cd ${PROJECT_DIR} && ${VENV_PYTHON} ${SCRAPER_SCRIPT} >> ${PROJECT_DIR}/scraper_cron.log 2>&1"

# Verificar si el cronjob ya existe
if crontab -l 2>/dev/null | grep -q "$SCRAPER_SCRIPT"; then
  echo "✅ El cronjob ya está configurado:"
  crontab -l | grep "$SCRAPER_SCRIPT"
else
  # Añadir el cronjob preservando los existentes
  (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
  echo "✅ Cronjob configurado con éxito!"
  echo "El scraper se ejecutará el día 1 de cada mes a la medianoche."
  echo "Comando programado:"
  echo "$CRON_CMD"
fi
