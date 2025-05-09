import os
from dotenv import load_dotenv
import smtplib
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.message import EmailMessage
from sqlalchemy import create_engine

# ────────────────────────────  CARGAR .env
load_dotenv()

# ────────────────────────────  VALIDACIÓN DE VARIABLES DE ENTORNO
required_vars = [
    "PG_USER",
    "PG_PASSWORD",
    "PG_HOST",
    "PG_PORT",
    "PG_DBNAME",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
]
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    raise RuntimeError(f"Variables de entorno faltantes: {', '.join(missing)}")

# ────────────────────────────  VARIABLES DE ENTORNO
DB_USER    = os.getenv("PG_USER")
DB_PASS    = os.getenv("PG_PASSWORD")
DB_HOST    = os.getenv("PG_HOST")
DB_PORT    = os.getenv("PG_PORT")
DB_NAME    = os.getenv("PG_DBNAME")

SMTP_HOST  = os.getenv("SMTP_HOST")
SMTP_PORT  = int(os.getenv("SMTP_PORT"))
SMTP_USER  = os.getenv("SMTP_USER")
SMTP_PASS  = os.getenv("SMTP_PASSWORD")

RECIPIENTS = [
    "ignaciodejesus.m.u@gmail.com",
    "20191240@aloe.ulima.edu.pe",
    "ialab@ulima.edu.pe"
]

# ────────────────────────────  SQLALCHEMY ENGINE
engine_url = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)
engine = create_engine(engine_url)

# ────────────────────────────  GENERAR CSVs
tz = timezone.utc
now = datetime.now(tz)
week_start = (now - timedelta(days=now.weekday())).replace(
    hour=0, minute=0, second=0, microsecond=0
)

week_df = pd.read_sql(
    "SELECT * FROM attendance WHERE ts >= %(ws)s",
    engine,
    params={"ws": week_start},
)
all_df = pd.read_sql("SELECT * FROM attendance", engine)

stamp = now.strftime("%Y%m%d")
week_csv = Path(f"attendance_semana_{stamp}.csv")
all_csv = Path(f"attendance_completo_{stamp}.csv")
week_df.to_csv(week_csv, index=False)
all_df.to_csv(all_csv, index=False)

# ────────────────────────────  ENVIAR E-MAIL
msg = EmailMessage()
msg["Subject"] = "Reportes de asistencia"
msg["From"] = SMTP_USER
msg["To"] = ", ".join(RECIPIENTS)
msg.set_content(
    "Adjunto encontrarás:\n"
    "1. Reporte de la semana actual\n"
    "2. Reporte completo de asistencia\n"
)

for p in (week_csv, all_csv):
    msg.add_attachment(
        p.read_bytes(),
        maintype="text",
        subtype="csv",
        filename=p.name,
    )

try:
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    print("✔️  Correos enviados correctamente.")
except smtplib.SMTPException as e:
    code = getattr(e, "smtp_code", "N/A")
    error = getattr(e, "smtp_error", b"").decode(errors="ignore")
    print(f"❌ Error al enviar el correo ({code}): {error}")
finally:
    week_csv.unlink(missing_ok=True)
    all_csv.unlink(missing_ok=True)
