# Operación en VPS

## Requisitos de secretos de GitHub Actions

Configura `VPS_HOST`, `VPS_PORT`, `VPS_USERNAME`, `VPS_SSH_KEY` y `ENV_FILE_CONTENT`.
`ENV_FILE_CONTENT` debe incluir al menos `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`,
`R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, SMTP y
`EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2`.

El workflow ejecuta `pytest tests -q` antes del despliegue. Si falla, no sincroniza
ni reinicia el VPS.

## Primer arranque

1. Fusiona o envía a `main`; GitHub Actions construye las imágenes y despliega.
2. Comprueba `https://TU_DOMINIO/health` y los logs: `docker compose -f docker-compose.prod.yml logs -f api worker`.
3. Crea un lote manual en el panel y ejecuta solamente el descubrimiento.
4. Revisa el inventario y usa Pausar/Cancelar si es necesario.
5. Para una prueba de humo, selecciona un único activo y ejecuta las fases de forma controlada. No habilites descarga masiva hasta que R2, SMTP y embeddings estén verificados.

Para validar los PDFs locales de ejemplo sin descargar ni subir archivos, ejecuta:

```bash
docker compose -f docker-compose.prod.yml exec -T api python scripts/verify_source_samples.py
```

## Scheduler relativo

El servicio `laix-public-pipeline.service` consulta cada minuto. Solo crea y encola
un nuevo descubrimiento 24 horas después de que el lote anterior haya finalizado
correctamente. Actívalo con:

```bash
sudo systemctl enable --now laix-public-pipeline.service
sudo systemctl status laix-public-pipeline.service
```

Para desactivarlo durante pruebas:

```bash
sudo systemctl disable --now laix-public-pipeline.service
```

Además define `PUBLIC_PIPELINE_SCHEDULER_ENABLED=true` en `.env` de producción.
# Fuentes PDF persistentes

Los PDFs manuales no se guardan dentro de `/opt/laix-rag`. En producción se
suben a `/data/laix-rag/source/{jurisprudencia,documentos}`; Docker los monta
como `/app/data/source`. Esta ruta no forma parte del despliegue `rsync`.
