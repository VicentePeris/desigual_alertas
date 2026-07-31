import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, jsonify
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


def get_env_int(name, default):
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
EMAIL_TO = os.environ.get("EMAIL_TO")

def enviar_alerta(anomalias, hora_analizada):
    """Configura y envía el correo electrónico usando SMTP seguro."""
    msg = MIMEMultipart()
    msg['From'] = EMAIL_FROM
    msg['To'] = EMAIL_TO
    msg['Subject'] = f"ALERTA GA4: Eventos a 0 - Hora: {hora_analizada}"

    # Construimos el cuerpo del mensaje en texto plano
    body = f"Se han detectado anomalías de tracking en la hora {hora_analizada} (Zona: {TIMEZONE}):\n\n"
    for store in anomalias:
        body += f" Mercado: {store['store']}\n"
        body += f"  - view_item: {store['view_item_count']}\n"
        body += f"  - add_to_cart: {store['add_to_cart_count']}\n"
        body += f"  - begin_checkout: {store['begin_checkout_count']}\n"
        body += f"  - purchase: {store['purchase_count']}\n"
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

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200


@app.route("/", methods=["GET", "POST"])
def ejecutar_control():
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
      COUNTIF(event_name = 'purchase') AS purchase_count
    FROM
      base_datos
    WHERE
      event_hour = (SELECT target_hour FROM calcular_hora_objetivo) AND store IN ('DE','ES','US','FR','PL','IT','NL','GB','MX','CA','AT','PT','JP','BE','CZ','CH','SE','HR')
    GROUP BY 1
    HAVING 
      page_view_count = 0
      OR (view_item_count > 30 AND add_to_cart_count = 0)
      OR (begin_checkout_count > 5 AND purchase_count = 0)
      OR (purchase_count > 0 AND (add_to_cart_count = 0 OR view_item_count = 0 OR begin_checkout_count = 0))
    """

    try:
        query_job = client.query(query)
        resultados = list(query_job.result())

        if len(resultados) > 0:
            # Si hay filas, significa que algún mercado tiene un evento a 0
            hora_analizada = str(resultados[0]['hora_analizada'])
            anomalias = [dict(row) for row in resultados]
            
            enviar_alerta(anomalias, hora_analizada)
            return jsonify({"status": "alerta_enviada", "Mercados_afectados": len(anomalias)}), 200
        
        return jsonify({"status": "ok", "message": "Métricas correctas en todos los mercados."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))