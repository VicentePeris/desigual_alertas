# Desigual Alertas

Servicio para detectar anomalías en eventos de GA4 almacenados en BigQuery y enviar alertas por correo electrónico cuando se detectan patrones sospechosos.

## Descripción

Este proyecto consulta los eventos intradía de Google Analytics 4 desde BigQuery, analiza si alguno de los mercados configurados presenta valores anormales en una hora concreta y envía un correo SMTP con el resumen de la incidencia.

La aplicación expone un endpoint HTTP en la ruta `/` que ejecuta la comprobación y, si encuentra anomalías, envía el aviso.

## Funcionalidades

- Consulta eventos de BigQuery para la fecha actual.
- Detecta posibles anomalías por mercado y hora.
- Envía alertas por correo usando SMTP.
- Puede ejecutarse localmente, en Docker o desplegarse en Cloud Run.

## Requisitos

- Python 3.11+
- Acceso a BigQuery con credenciales válidas de Google Cloud.
- Un servidor SMTP configurado para enviar correos.
- Variables de entorno definidas correctamente.

## Variables de entorno

Configura las siguientes variables antes de ejecutar la aplicación:

- `PROJECT_ID`: ID del proyecto de Google Cloud.
- `DATASET_ID`: Dataset donde se almacenan los eventos de GA4.
- `TIMEZONE`: Zona horaria utilizada en las consultas. Por defecto: `Europe/Madrid`.
- `SMTP_SERVER`: Servidor SMTP.
- `SMTP_PORT`: Puerto SMTP. Por defecto: `587`.
- `SMTP_USER`: Usuario SMTP.
- `SMTP_PASSWORD` o `SENDER_PASS`: Contraseña SMTP.
- `EMAIL_FROM`: Remitente del correo.
- `EMAIL_TO`: Destinatario o destinatarios del correo.
- `PORT`: Puerto HTTP para ejecución local o Cloud Run. Por defecto: `8080`.

## Instalación local

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

Crea un archivo `.env` con tus variables de entorno si vas a ejecutar la app localmente.

## Ejecución local

```bash
python main.py
```

La app quedará disponible en:

```text
http://localhost:8080/
```

## Ejecución con Docker

```bash
docker build -t desigual-alertas .
docker run -p 8080:8080 --env-file .env desigual-alertas
```

## Despliegue en Google Cloud Run

Un ejemplo de despliegue sería:

```bash
gcloud run deploy desigual-alertas \
  --source . \
  --platform managed \
  --region europe-west1 \
  --allow-unauthenticated
```

Asegúrate de configurar las variables de entorno en Cloud Run o mediante Secret Manager.

## Programación con Cloud Scheduler

Este servicio está pensado para ejecutarse mediante una petición HTTP periódica desde Cloud Scheduler.

- Cloud Scheduler llama a la URL del endpoint `/`.
- El endpoint ejecuta la lógica de comprobación y envío de alerta.
- Puedes programarlo con una frecuencia como cada 15 o 60 minutos según tus necesidades.

## Estructura del proyecto

- `main.py`: lógica principal de la aplicación y endpoint HTTP.
- `requirements.txt`: dependencias de Python.
- `Dockerfile`: configuración para desplegar con Docker/Cloud Run.

## Notas

- Para producción, es recomendable almacenar secretos como SMTP y credenciales de Google Cloud en Secret Manager.
- Verifica que la cuenta de servicio usada por la ejecución tenga permisos para consultar BigQuery.
