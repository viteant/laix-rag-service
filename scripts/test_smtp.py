import os
import sys
import pathlib

# Añadir el directorio raíz al path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from app.core.email import send_alert_email
from app.core.config import settings

def test_smtp():
    print("=========================================")
    print("🔍 INICIANDO PRUEBA DE CONEXIÓN SMTP")
    print("=========================================")
    
    if not all([settings.SMTP_HOST, settings.SMTP_PORT, settings.SMTP_USER, settings.SMTP_PASSWORD, settings.ALERT_EMAIL_TO]):
        print("❌ ERROR: Faltan variables de entorno SMTP.")
        print(f"Host: {settings.SMTP_HOST}")
        print(f"Port: {settings.SMTP_PORT}")
        print(f"User: {settings.SMTP_USER}")
        print(f"To:   {settings.ALERT_EMAIL_TO}")
        print("Asegúrate de haber configurado tu archivo .env (o los Secretos de GitHub)")
        sys.exit(1)
        
    print(f"Host: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
    print(f"Autenticando como: {settings.SMTP_USER}")
    print(f"Destinatario: {settings.ALERT_EMAIL_TO}")
    print("Enviando correo de prueba...")
    
    subject = "Prueba de Integración SMTP - LAIX RAG"
    body = (
        "<h2>✅ Conexión Exitosa</h2>"
        "<p>Si estás leyendo este correo, significa que la integración con <b>Brevo SMTP</b> "
        "funciona perfectamente en tu entorno de producción.</p>"
        "<p>El daemon de LAIX RAG ahora puede enviarte alertas críticas y resúmenes de ingesta "
        "de forma autónoma.</p>"
    )
    
    success = send_alert_email(subject, body, is_html=True)
    
    if success:
        print("\n✅ ¡PRUEBA SUPERADA! Revisa tu bandeja de entrada.")
    else:
        print("\n❌ FALLO EN LA PRUEBA. Revisa los logs de error arriba.")

if __name__ == "__main__":
    test_smtp()
