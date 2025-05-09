import os
import sys
import time
import pickle
import tempfile
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread
from collections import deque
from dotenv import load_dotenv

import cv2
import numpy as np
import face_recognition
import psycopg2
import psycopg2.extras
import pyttsx3
import platform
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

# ────────────────────────────  CARGAR .env
load_dotenv()

# ────────────────────────────  VALIDACIÓN DE CREDENCIALES BD
required_db = ["PG_HOST", "PG_PORT", "PG_USER", "PG_PASSWORD", "PG_DBNAME"]
missing_db = [v for v in required_db if not os.getenv(v)]
if missing_db:
    raise RuntimeError(f"Entorno incompleto, faltan: {', '.join(missing_db)}")

# ────────────────────────────  PARÁMETROS DE CONFIGURACIÓN
ATTENDANCE_COOLDOWN = timedelta(minutes=3)
UNKNOWN_COOLDOWN    = timedelta(seconds=7)

TMP_DIR = Path(tempfile.gettempdir())
BASE_DIR = Path(__file__).resolve().parent
PERU_TZ  = ZoneInfo("America/Lima")

# Tuning parameters (no defaults here if you prefer full env control)
TOLERANCE   = float(os.getenv("FR_TOLERANCE"))
DETECTOR    = os.getenv("FR_DET_MODEL")
FRAME_SCALE = int(os.getenv("FR_SCALE"))
VOTE_LEN    = int(os.getenv("FR_VOTE_FRAMES"))
recent_names: deque[str] = deque(maxlen=VOTE_LEN)

# ────────────────────────────  PARÁMETROS DE BASE DE DATOS
DB_PARAMS = {
    "host":     os.getenv("PG_HOST"),
    "port":     int(os.getenv("PG_PORT")),
    "user":     os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "dbname":   os.getenv("PG_DBNAME"),
}

# ────────────────────────────  CREAR TABLAS SI NO EXISTEN
SQL_ATTENDANCE = """
CREATE TABLE IF NOT EXISTS attendance(
    id SERIAL PRIMARY KEY,
    person TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    record_type CHAR(3) NOT NULL
);
"""
SQL_UNKNOWN = """
CREATE TABLE IF NOT EXISTS unknown_videos(
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL,
    mp4 BYTEA NOT NULL
);
"""

conn = psycopg2.connect(**DB_PARAMS)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute(SQL_ATTENDANCE)
    cur.execute(SQL_UNKNOWN)

# ────────────────────────────  FUNCIONES AUXILIARES
def last_record(name: str):
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(
            "SELECT record_type, ts FROM attendance WHERE person=%s "
            "ORDER BY ts DESC LIMIT 1;",
            (name,),
        )
        row = cur.fetchone()
        return (row["record_type"], row["ts"]) if row else (None, None)

def add_record(name: str, rec_type: str, ts: datetime):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO attendance(person, ts, record_type) VALUES(%s, %s, %s);",
            (name, ts, rec_type),
        )
    status = "entrada" if rec_type == "IN" else "salida"
    speak(f"{ts:%Y-%m-%d %H:%M:%S}  {name}  {status} registrada.")

def save_unknown_video(mp4_path: Path) -> int:
    with open(mp4_path, "rb") as f, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO unknown_videos (ts, mp4)
            VALUES (%s, %s)
            RETURNING id;
            """,
            (datetime.now(timezone.utc), psycopg2.Binary(f.read())),
        )
        return cur.fetchone()[0]

def record_unknown(cam, seconds: int = 5):
    tmp = TMP_DIR / f"unknown_{datetime.now():%Y%m%d_%H%M%S}.mp4"
    fps = cam.get(cv2.CAP_PROP_FPS) or 20
    w = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    end = time.time() + seconds
    while time.time() < end:
        ok, fr = cam.read()
        if ok:
            vw.write(fr)
    vw.release()

    video_id = save_unknown_video(tmp)
    tmp.unlink(missing_ok=True)
    subprocess.Popen(
        [sys.executable, str(BASE_DIR / "export_single_video.py"), str(video_id)]
    )

engine = pyttsx3.init()
engine.setProperty("rate", 250)
engine.setProperty("volume", 1.0)
if platform.system().lower() == "darwin":
    desired_voice_id = "com.apple.voice.compact.es-MX.Paulina"
    for voice in engine.getProperty("voices"):
        if voice.id == desired_voice_id:
            engine.setProperty("voice", voice.id)
            break
    else:
        print("⚠️ Voz Paulina no encontrada. Usando la voz por defecto.")
else:
    engine.setProperty('voice', engine.getProperty('voices')[0].id)

def speak(msg: str):
    print(msg)
    engine.say(msg)
    engine.runAndWait()

with open("encodings.pickle", "rb") as f:
    enc_data = pickle.load(f)
known_encs  = enc_data["encodings"]
known_names = enc_data["names"]

def run_script(script_name: str):
    subprocess.Popen([sys.executable, str(BASE_DIR / script_name)])

def schedule_weekly_reports():
    sched = BackgroundScheduler()
    trigger = CronTrigger(
        day_of_week="sun", hour=11, minute=0, timezone=PERU_TZ
    )
    sched.add_job(run_script, trigger, args=("automatically_send_weekly_reports.py",))
    sched.start()
    return sched

# ────────────────────────────  BUCLE PRINCIPAL
cam = cv2.VideoCapture(0)
fps = cnt = 0
t0 = time.time()
last_unknown_ts = datetime.min.replace(tzinfo=timezone.utc)
scheduler = schedule_weekly_reports()

try:
    while True:
        ok, frame = cam.read()
        if not ok:
            speak("Error de cámara.")
            break

        small = cv2.resize(frame, (0,0), fx=1/FRAME_SCALE, fy=1/FRAME_SCALE)
        rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        locs  = face_recognition.face_locations(rgb, model=DETECTOR)
        encs  = face_recognition.face_encodings(rgb, locs, model="large")
        names = []

        now = datetime.now(timezone.utc)
        for enc in encs:
            dists = face_recognition.face_distance(known_encs, enc)
            idx   = int(np.argmin(dists))
            match = dists[idx] <= TOLERANCE
            name  = known_names[idx] if match else "Desconocido"
            names.append(name)

            recent_names.append(name)
            voted = (recent_names[0]
                    if len(recent_names)==VOTE_LEN and len(set(recent_names))==1
                    else None)

            if voted == "Desconocido":
                if now - last_unknown_ts >= UNKNOWN_COOLDOWN:
                    last_unknown_ts = now
                    speak("Usuario desconocido, intente nuevamente.")
                    Thread(target=record_unknown, args=(cam,)).start()
                continue

            if voted:
                last_type, last_ts = last_record(voted)
                if last_ts is None or now - last_ts >= ATTENDANCE_COOLDOWN:
                    next_type = "IN" if last_type in (None, "OUT") else "OUT"
                    add_record(voted, next_type, now)

        # dibujar recuadros y nombres
        for (t,r,b,l), nm in zip(locs, names):
            t*=FRAME_SCALE; r*=FRAME_SCALE; b*=FRAME_SCALE; l*=FRAME_SCALE
            cv2.rectangle(frame, (l,t), (r,b), (0,140,255), 2)
            cv2.rectangle(frame, (l,b-25), (r,b), (0,140,255), cv2.FILLED)
            cv2.putText(frame, nm, (l+6,b-6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1)

        cnt += 1
        if time.time() - t0 >= 1:
            fps = cnt / (time.time() - t0)
            cnt = 0
            t0  = time.time()
        cv2.putText(frame, f"FPS:{fps:.1f}", (10,30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)

        cv2.imshow("Attendance", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

finally:
    cam.release()
    cv2.destroyAllWindows()
    conn.close()
    scheduler.shutdown()
