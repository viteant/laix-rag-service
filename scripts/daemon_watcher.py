import os
import sys
import time
import pathlib
import traceback
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from scripts.inventory_documents import inventory_directory
from scripts.ingest_directory import ingest_directory
from app.core.email import send_alert_email


def run_daemon(interval_seconds: int = 300, idle_interval_seconds: int = 86400):
    base_data_path = os.getenv("DATA_SOURCE_PATH", "data/source")
    print(f"\n==================================================")
    print(f"🚀 Iniciando Daemon de Ingesta Automática")
    print(f"📂 Observando directorio: {base_data_path}")
    print(f"⏱️  Frecuencia activa: {interval_seconds}s | Reposo: {idle_interval_seconds}s")
    print(f"==================================================\n")

    while True:
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] 🔄 Iniciando ciclo de escaneo...")
            
            # 1. Inventariar nuevos documentos (encuentra PDFs nuevos y detecta OCR)
            inventory_res = inventory_directory(base_data_path)
            
            # 2. Ingerir los documentos pendientes si los hay
            ingest_res = {"success": 0, "skipped": 0, "failed": 0}
            if inventory_res and (inventory_res.get("new_count", 0) > 0 or inventory_res.get("total_pending", 0) > 0):
                ingest_res = ingest_directory(base_data_path, limit=None, force=False, retry_failed=False)
                
                # Si terminamos de procesar un lote (éxitos > 0) y ahora ya no queda nada, mandamos el correo.
                if ingest_res and ingest_res.get("success", 0) > 0:
                    failed_files = ingest_res.get("failed_files", [])
                    failed_list_html = ""
                    if failed_files:
                        failed_list_html = "<h3>Archivos Fallidos:</h3><ul>"
                        for f in failed_files:
                            failed_list_html += f"<li>{f}</li>"
                        failed_list_html += "</ul>"
                        
                    subject = "✅ Lote de Ingesta Completado"
                    body = (
                        f"<h2>Ingesta Completada Exitosamente</h2>"
                        f"<p>El daemon de inyección ha finalizado el procesamiento de un lote completo.</p>"
                        f"<ul>"
                        f"<li><b>Nuevos Exitosos:</b> {ingest_res.get('success', 0)}</li>"
                        f"<li><b>Omitidos/Ya procesados:</b> {ingest_res.get('skipped', 0)}</li>"
                        f"<li><b>Fallidos:</b> {ingest_res.get('failed', 0)}</li>"
                        f"</ul>"
                        f"{failed_list_html}"
                        f"<p>El sistema entrará en modo reposo hasta detectar nuevos archivos.</p>"
                    )
                    send_alert_email(subject, body)
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 📧 Correo de fin de lote enviado.")
            
            # Decidir tiempo de espera (Adaptive Sleep)
            if inventory_res and inventory_res.get("total_pending", 0) > 0:
                # Si todavía quedan cosas por procesar (por ejemplo si hubo límite o fallaron), usar active
                sleep_time = interval_seconds
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ⏳ Aún hay pendientes. Esperando {sleep_time}s (Activo)...")
            elif ingest_res and ingest_res.get("success", 0) > 0:
                # Acabamos de procesar un lote y ya no hay pendientes, ir a reposo largo pero revisando pronto por si acaso?
                # No, si terminamos, reposo.
                sleep_time = idle_interval_seconds
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💤 Lote terminado. Esperando {sleep_time}s (Reposo)...")
            else:
                # No hubo nada nuevo, seguimos en reposo
                sleep_time = idle_interval_seconds
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 💤 Sin cambios. Esperando {sleep_time}s (Reposo)...")
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Error crítico en el ciclo del daemon:")
            traceback.print_exc()
            
            error_details = traceback.format_exc()
            subject = f"Alerta Crítica: Fallo en Daemon ({type(e).__name__})"
            body = (
                f"<h2>Fallo en el Daemon</h2>"
                f"<p>Se ha producido un error inesperado que interrumpió el ciclo de escaneo.</p>"
                f"<h3>Detalles del Error:</h3>"
                f"<pre>{error_details}</pre>"
                f"<p>El daemon intentará recuperarse en el próximo ciclo.</p>"
            )
            send_alert_email(subject, body)
            
            sleep_time = interval_seconds
            print(f"⚠️ El daemon continuará en el próximo ciclo a pesar del error.\n")
        
        # Esperar hasta el próximo ciclo
        time.sleep(sleep_time)


if __name__ == "__main__":
    interval = int(os.getenv("DAEMON_INTERVAL_SECONDS", 300))
    idle_interval = int(os.getenv("IDLE_INTERVAL_SECONDS", 86400)) # Default 1 día
    run_daemon(interval, idle_interval)
