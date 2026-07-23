#!/usr/bin/env bash

set -euo pipefail

REPOSITORY="${1:?Repository argument is required}"
ENV_FILE_BASE64="${2:?Environment content argument is required}"

ENV_FILE_CONTENT="$(
  printf '%s' "$ENV_FILE_BASE64" |
  base64 --decode
)"

echo "Deploying repository: $REPOSITORY"

# Ejemplo:
# printf '%s\n' "$ENV_FILE_CONTENT" > /ruta/del/proyecto/.env