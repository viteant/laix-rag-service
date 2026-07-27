import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import settings

def send_alert_email(subject: str, message: str, is_html: bool = True) -> bool:
    """
    Envía un correo electrónico usando la configuración SMTP.
    Si no hay configuración SMTP, imprime el mensaje en consola.
    """
    if not all([settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.ALERT_EMAIL_TO]):
        print(f"⚠️ Alerta simulada (Falta config SMTP en .env) | {subject}:\n{message}")
        return False

    import os
    import hashlib
    from datetime import datetime
    
    # ------------------ DEBOUNCE LOGIC ------------------
    # Evitar spam: Enviar el correo solo 1 vez al día por cada Asunto único.
    locks_dir = os.path.join(os.getenv("DATA_SOURCE_PATH", "data"), "locks")
    os.makedirs(locks_dir, exist_ok=True)
    
    subject_hash = hashlib.md5(subject.encode('utf-8')).hexdigest()
    lock_file = os.path.join(locks_dir, f"email_{subject_hash}.lock")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    if os.path.exists(lock_file):
        with open(lock_file, "r") as f:
            last_sent = f.read().strip()
        if last_sent == today_str:
            print(f"🤫 [Debounce] Correo silenciado para hoy (ya se envió): {subject}")
            return True # Retorna True para no romper el flujo
            
    with open(lock_file, "w") as f:
        f.write(today_str)
    # ----------------------------------------------------

    msg = MIMEMultipart()
    msg['From'] = settings.SMTP_FROM_EMAIL if settings.SMTP_FROM_EMAIL else settings.SMTP_USER
    msg['To'] = settings.ALERT_EMAIL_TO
    msg['Subject'] = f"[LAIX RAG] {subject}"

    mime_type = "html" if is_html else "plain"
    msg.attach(MIMEText(message, mime_type, "utf-8"))

    try:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"📧 Correo enviado a {settings.ALERT_EMAIL_TO}: {subject}")
        return True
    except Exception as e:
        print(f"❌ Error enviando correo: {e}")
        return False
