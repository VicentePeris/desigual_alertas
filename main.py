import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.cloud import bigquery
# from dotenv import load_dotenv

# load_dotenv()


def _make_json_response(status_code, data):
    """Helper para crear respuestas JSON compatibles con Cloud Functions."""
    return json.dumps(data), status_code, {"Content-Type": "application/json"}


def get_env_int(name, default):
    """Obtiene una variable de entorno como entero."""
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"La variable de entorno {name} no es un número válido: {value}") from exc


# Configuración mediante Variables de Entorno de Cloud Run
PROJECT_ID = os.environ.get("PROJECT_ID")
DATASET_ID = os.environ.get("DATASET_ID")
TIMEZONE = os.environ.get("TIMEZONE", "Europe/Madrid")

SMTP_SERVER = os.environ.get("SMTP_SERVER")
SMTP_PORT = get_env_int("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER") or os.environ.get("EMAIL_FROM")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD") or os.environ.get("SENDER_PASS")
EMAIL_FROM = os.environ.get("EMAIL_FROM")
EMAIL_TO = [email.strip() for email in (os.environ.get("EMAIL_TO") or "").split(",") if email.strip()]

def enviar_alerta(anomalias, hora_analizada):
    """Configura y envía el correo electrónico usando SMTP seguro."""
    if not EMAIL_TO:
        raise RuntimeError("La variable de entorno EMAIL_TO no contiene destinatarios válidos.")

    msg = MIMEMultipart()
    msg['From'] = EMAIL_FROM
    msg['To'] = ", ".join(EMAIL_TO)
    msg['Subject'] = f"ALERTA GA4: Eventos a 0 - Hora: {hora_analizada}"
    #print(EMAIL_FROM)
    #print(EMAIL_TO)
    # Construimos el cuerpo del mensaje en texto plano
    body = f"Se han detectado anomalías de tracking en la hora {hora_analizada} (Zona: {TIMEZONE}):\n\n"
    for store in anomalias:
        body += f" Mercado: {store['store']}\n"
         # Eventos a mostrar con detección de ceros
        eventos = [
            ('page_view', store['page_view_count']),
            ('view_item', store['view_item_count']),
            ('add_to_cart', store['add_to_cart_count']),
            ('begin_checkout', store['begin_checkout_count']),
            ('select_size', store['select_size_count']),
            ('new_register', store['new_register_count']),
            ('purchase', store['purchase_count']),
        ]
        
        for evento_name, evento_count in eventos:
            if evento_count == 0:
                body += f"  *** {evento_name}: {evento_count} <<< ¡ALERTA: SIN EVENTOS! ***\n"
            else:
                body += f"  - {evento_name}: {evento_count}\n"
        body += "-------------------------------------------\n"
    
    body += "\nPor favor, revisa si hay un fallo en el tagueo de la web."
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()  # Conexión segura
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        server.quit()
        print("Email enviado correctamente.")
    except Exception as e:
        print(f"Error crítico al enviar el email: {e}")


def main(request):
    """
    Función principal para Cloud Function (HTTP trigger).
    
    Args:
        request: Objeto de solicitud de Flask/Cloud Functions
        
    Returns:
        Tupla (response_body, status_code, headers)
    """
    print("start main")
    client = bigquery.Client()

    # Consulta con HAVING para filtrar anomalías directamente en BigQuery
    query = f"""
    WITH base_datos AS (
      SELECT
        event_name,
        (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'store') AS store,
        DATETIME_TRUNC(DATETIME(TIMESTAMP_MICROS(event_timestamp), '{TIMEZONE}'), HOUR) AS event_hour
      FROM
        `{PROJECT_ID}.{DATASET_ID}.events_intraday_*`
      WHERE
        _TABLE_SUFFIX = FORMAT_DATE('%Y%m%d', CURRENT_DATE('{TIMEZONE}'))
    ),
    calcular_hora_objetivo AS (
      SELECT
        DATETIME_SUB(MAX(event_hour), INTERVAL 2 HOUR) AS target_hour
      FROM
        base_datos
    )
    SELECT
      COALESCE(store, '(no_definido)') AS store,
      (SELECT target_hour FROM calcular_hora_objetivo) AS hora_analizada,
      COUNTIF(event_name = 'page_view') AS page_view_count,
      COUNTIF(event_name = 'view_item') AS view_item_count,
      COUNTIF(event_name = 'add_to_cart') AS add_to_cart_count,
      COUNTIF(event_name = 'begin_checkout') AS begin_checkout_count,
      COUNTIF(event_name = 'select_size') AS select_size_count,
      COUNTIF(event_name = 'new_register') AS new_register_count,
      COUNTIF(event_name = 'purchase') AS purchase_count
    FROM
      base_datos
    WHERE
      event_hour = (SELECT target_hour FROM calcular_hora_objetivo) AND store IN ('DE','ES','US','FR','PL','IT')
    GROUP BY 1
    HAVING 
      page_view_count = 0
      OR (view_item_count = 0)
      OR (add_to_cart_count = 0)
      OR (select_size_count = 0)
      OR (begin_checkout_count = 0)
      OR (new_register_count = 0)
      OR (view_item_count > 30 AND add_to_cart_count = 0)
      OR (begin_checkout_count > 5 AND purchase_count = 0)
      OR (purchase_count = 0 AND (add_to_cart_count > 15 OR view_item_count > 100 OR begin_checkout_count > 2))
      OR (purchase_count > 0 AND (add_to_cart_count < purchase_count OR view_item_count < purchase_count OR begin_checkout_count < purchase_count))
    """
    print(query)
    try:
        query_job = client.query(query)
        resultados = list(query_job.result())

        if len(resultados) > 0:
            # Si hay filas, significa que algún mercado tiene un evento a 0
            hora_analizada = str(resultados[0]['hora_analizada'])
            anomalias = [dict(row) for row in resultados]
            
            enviar_alerta(anomalias, hora_analizada)
            return _make_json_response(200, {
                "status": "alerta_enviada", 
                "Mercados_afectados": len(anomalias)
            })
        
        return _make_json_response(200, {
            "status": "ok", 
            "message": "Métricas correctas en todos los mercados."
        })

    except Exception as e:
        return _make_json_response(500, {
            "status": "error", 
            "message": str(e)
        })