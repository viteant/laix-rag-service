import os
import sys
import pathlib
import re
import argparse
import time
import random
import fcntl
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Añadir el directorio raíz al path para poder importar módulos de la app
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.email import send_alert_email

SECTIONS = {
    "registro_oficial": "https://www.registroficial.gob.ec/245427-2/",
    "suplementos": "https://www.registroficial.gob.ec/255776-2/",
    "edicion_especial": "https://www.registroficial.gob.ec/261974-2/",
    "edicion_constitucional": "https://www.registroficial.gob.ec/267099-2/",
    "edicion_juridica": "https://www.registroficial.gob.ec/266381-2/",
    "indice_mensual": "https://www.registroficial.gob.ec/265554-2/"
}

BASE_DOWNLOAD_DIR = Path("data/source")

def clean_filename(text):
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = text.replace(" ", "_")
    return text

def download_pdf(url, dest_path):
    if dest_path.exists():
        print(f"    ⏭️ Archivo ya existe: {dest_path.name}")
        return False
    
    print(f"    ⬇️ Descargando: {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"    ✅ Guardado como {dest_path.name}")
        
        # Espera natural entre descargas para no saturar al servidor
        sleep_time = random.uniform(1.5, 3.5)
        print(f"    ⏳ Esperando {sleep_time:.2f}s...")
        time.sleep(sleep_time)
        
        return True
    except Exception as e:
        print(f"    ❌ Error al descargar {url}: {e}")
        return False

def scrape_section(p, context, section_name, base_url, test_mode):
    download_dir = BASE_DOWNLOAD_DIR / section_name
    download_dir.mkdir(parents=True, exist_ok=True)
    
    page = context.new_page()
    print(f"\n=============================================")
    print(f"🌍 Sección: {section_name}")
    print(f"🌍 Navegando a {base_url} ...")
    print(f"=============================================")
    
    page.goto(base_url, wait_until="networkidle", timeout=60000)
    
    try:
        page.wait_for_selector("ul#tree2", timeout=30000, state="attached")
    except PlaywrightTimeoutError:
        print(f"❌ No se encontró 'ul#tree2' en {section_name}. Posible cambio en la web o bloqueo.")
        page.close()
        return

    item_links = page.locator("ul#tree2 a.post-imagen-link")
    count_items = item_links.count()
    print(f"🔍 Encontrados {count_items} meses/carpetas en {section_name}.")
    
    processed_page_2 = False
    docs_downloaded = 0
    
    for i in range(count_items):
        item_locator = item_links.nth(i)
        item_text = item_locator.inner_text().strip()
        
        print(f"\n📁 Procesando carpeta [{i+1}/{count_items}]: {item_text}")
        item_locator.evaluate("el => el.click()")
        time.sleep(2)
        
        current_page_idx = 1
        
        while True:
            print(f"  📄 --- Página {current_page_idx} de {item_text} ({section_name}) ---")
            
            try:
                page.wait_for_selector("#child-post-imagen", state="attached", timeout=10000)
            except PlaywrightTimeoutError:
                print("    ⚠️ Panel derecho no cargó a tiempo.")
                break
                
            time.sleep(1)
            
            child_panel = page.locator("#child-post-imagen")
            if "Sin Archivos post" in child_panel.inner_text():
                print("    ℹ️ Sin archivos (carpeta vacía).")
                break
            
            cards = page.locator(".card__item_post_imagen")
            count_cards = cards.count()
            
            if count_cards == 0:
                print("    ⚠️ No se encontraron tarjetas.")
                break
                
            for j in range(count_cards):
                card = cards.nth(j)
                titulo = card.locator("h4.card__title_numero_imagen").inner_text().strip()
                fechas_paginas = card.locator("p.txt_fecha_post_imagen").all_inner_texts()
                
                fecha = fechas_paginas[0].strip() if len(fechas_paginas) > 0 else "Sin_Fecha"
                paginas = fechas_paginas[1].strip() if len(fechas_paginas) > 1 else ""
                
                link_locator = card.locator("a.cta_post_imagen")
                if link_locator.count() == 0:
                    continue
                    
                download_url = link_locator.get_attribute("href")
                if not download_url:
                    continue
                if not download_url.startswith("http"):
                    download_url = urljoin(base_url, download_url)
                    
                clean_titulo = clean_filename(titulo)
                clean_fecha = clean_filename(fecha)
                filename = f"RO_{clean_titulo}_{clean_fecha}.pdf"
                dest_path = download_dir / filename
                
                print(f"    📑 Documento: {titulo} | {fecha} | {paginas}")
                if download_pdf(download_url, dest_path):
                    docs_downloaded += 1
                
                if test_mode:
                    break # Solo 1 documento por página en modo prueba
            
            if test_mode and current_page_idx >= 2:
                print(f"  ✅ Test mode: Se han procesado 2 páginas de {item_text} en {section_name}. Terminando carpeta.")
                processed_page_2 = True
                break
                
            # Paginación
            pagination = page.locator("ul.k-pagination__pages")
            if pagination.count() == 0:
                print("  🔚 No hay paginación en esta carpeta.")
                break
                
            next_page_num = current_page_idx + 1
            next_page_link = pagination.locator(f"a.button-post-imagen-link", has_text=re.compile(f"^\\s*{next_page_num}\\s*$"))
            
            if next_page_link.count() == 0:
                print("  🔚 No hay más páginas en esta carpeta.")
                break
            
            print(f"  ➡️ Navegando a la página {next_page_num} de {item_text}...")
            next_page_link.first.evaluate("el => el.click()")
            time.sleep(3)
            current_page_idx = next_page_num
            
        if test_mode and processed_page_2:
            print(f"\n✅ Test mode: finalizando {section_name} tras procesar exitosamente una carpeta con paginación.")
            break
            
    print(f"\n🎉 Extracción finalizada para: {section_name}. Descargados: {docs_downloaded}")
    
    # Enviar correo de notificación
    subject = f"✅ Descarga Finalizada: {section_name.replace('_', ' ').title()}"
    body = (
        f"<h2>Extracción Finalizada</h2>"
        f"<p>El scraper ha terminado de descargar los documentos para la sección: <b>{section_name}</b>.</p>"
        f"<p>Modo de prueba: {'Activado' if test_mode else 'Desactivado'}</p>"
        f"<p>Documentos nuevos descargados: <b>{docs_downloaded}</b></p>"
    )
    send_alert_email(subject, body, is_html=True)
    page.close()

def run_scraper(test_mode=False):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            accept_downloads=True
        )
        
        for section_name, base_url in SECTIONS.items():
            scrape_section(p, context, section_name, base_url, test_mode)
            
        browser.close()
    
    print("\n🚀 Todo el proceso de scraping ha terminado.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper Registro Oficial del Ecuador (Multisección)")
    parser.add_argument("--test-mode", action="store_true", help="Prueba 1 doc de pág 1 y pág 2 por sección")
    parser.add_argument("--force", action="store_true", help="Forzar la ejecución ignorando si ya corrió hoy")
    args = parser.parse_args()
    
    # 1. Asegurar que solo corra una instancia a la vez
    lock_path = BASE_DOWNLOAD_DIR / ".scraper.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock_file = open(lock_path, "w")
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("❌ El scraper ya se encuentra en ejecución (lockfile detectado). Saliendo.")
        sys.exit(0)
        
    # 2. Verificar si ya se ejecutó el día de hoy (salvo que sea test o forzado)
    today = datetime.now().strftime("%Y-%m-%d")
    run_file = BASE_DOWNLOAD_DIR / ".scraper_last_run"
    
    if not args.test_mode and not args.force and run_file.exists():
        if run_file.read_text().strip() == today:
            print(f"✅ El scraper ya se ejecutó con éxito el día de hoy ({today}). Saliendo.")
            sys.exit(0)
            
    run_scraper(test_mode=args.test_mode)
    
    # 3. Marcar como ejecutado si fue exitoso
    if not args.test_mode:
        run_file.write_text(today)
