import os
import sys
import time
import pathlib
import traceback
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from scripts.inventory_documents import inventory_directory
from scripts.ingest_directory import ingest_directory


def run_daemon(interval_seconds: int = 300):
    base_data_path = os.getenv("DATA_SOURCE_PATH", "data/source")
    print(f"\n==================================================")
    print(f"🚀 Iniciando Daemon de Ingesta Automática")
    print(f"📂 Observando directorio: {base_data_path}")
    print(f"⏱️  Frecuencia de escaneo: Cada {interval_seconds} segundos")
    print(f"==================================================\n")

    while True:
        try:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{current_time}] 🔄 Iniciando ciclo de escaneo...")
            
            # 1. Inventariar nuevos documentos (encuentra PDFs nuevos y detecta OCR)
            inventory_directory(base_data_path)
            
            # 2. Ingerir los documentos pendientes
            ingest_directory(base_data_path, limit=None, force=False, retry_failed=False)
            
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Ciclo completado. Esperando {interval_seconds}s para el próximo escaneo...\n")
            
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ Error crítico en el ciclo del daemon:")
            traceback.print_exc()
            print(f"⚠️ El daemon continuará en el próximo ciclo a pesar del error.\n")
        
        # Esperar hasta el próximo ciclo
        time.sleep(interval_seconds)


if __name__ == "__main__":
    # Puedes configurar el intervalo mediante variable de entorno o dejar el default de 300s (5 minutos)
    interval = int(os.getenv("DAEMON_INTERVAL_SECONDS", 300))
    run_daemon(interval)
