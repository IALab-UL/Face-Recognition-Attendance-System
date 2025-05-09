import os
import sys
import time
import pickle
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread
from collections import deque
from dotenv import load_dotenv

import cv2
import numpy as np
import face_recognition
import pyttsx3
import firebase_admin
from firebase_admin import credentials, firestore, storage
from google.cloud.firestore_v1 import FieldFilter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

# ────────────────────────────  ENV & CONSTANTES
load_dotenv()

ATTENDANCE_COOLDOWN = timedelta(minutes=3)
UNKNOWN_COOLDOWN    = timedelta(seconds=7)
TMP_DIR             = Path(tempfile.gettempdir())
BASE_DIR            = Path(__file__).resolve().parent
PERU_TZ             = ZoneInfo("America/Lima")

TOLERANCE   = float(os.getenv("FR_TOLERANCE", 0.55))
DETECTOR    = os.getenv("FR_DET_MODEL",  "hog")
FRAME_SCALE = int  (os.getenv("FR_SCALE",       4))
VOTE_LEN    = int  (os.getenv("FR_VOTE_FRAMES", 3))
recent_names: deque[str] = deque(maxlen=VOTE_LEN)

# ────────────────────────────  FIREBASE INIT
cred = credentials.Certificate(os.getenv("FIREBASE_SA_PATH"))
firebase_admin.initialize_app(
    cred,
    {"storageBucket": os.getenv("FIREBASE_BUCKET")}
)

db     = firestore.client()
bucket = storage.bucket()

# ────────────────────────────  DB HELPERS
def last_record(name: str):
    docs = (
        db.collection("attendance")
          .where(filter=FieldFilter("person", "==", name))
          .order_by("ts", direction=firestore.Query.DESCENDING)
          .limit(1)
          .stream()
    )
    docs = list(docs)
    if not docs:
        return None, None
    d = docs[0].to_dict()
    return d["record_type"], d["ts"]

def add_record(name: str, rec_type: str, ts: datetime):
    db.collection("attendance").add(
        {"person": name, "record_type": rec_type, "ts": ts}
    )
    status = "entrada" if rec_type == "IN" else "salida"
    speak(f"{ts:%Y-%m-%d %H:%M:%S}  {name}  {status} registrada.")

def save_unknown_video(mp4_path: Path) -> None:
    blob_name = f"unknown_videos/{mp4_path.name}"
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(mp4_path)

    db.collection("unknown_videos").add(
        {
            "ts": datetime.now(timezone.utc),
            "gcs_uri": f"gs://{bucket.name}/{blob_name}"
        }
    )

# ────────────────────────────  VIDEO THREAD
def record_unknown(cam, seconds: int = 3):
    tmp = TMP_DIR / f"unknown_{datetime.now():%Y%m%d_%H%M%S}.mp4"
    fps = cam.get(cv2.CAP_PROP_FPS) or 20
    w   = int(cam.get(cv2.CAP_PROP_FRAME_WIDTH))
    h   = int(cam.get(cv2.CAP_PROP_FRAME_HEIGHT))
    vw  = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    end = time.time() + seconds
    while time.time() < end:
        ok, fr = cam.read()
        if ok:
            vw.write(fr)
    vw.release()

    save_unknown_video(tmp)
    tmp.unlink(missing_ok=True)  # elimina el archivo temporal

# ────────────────────────────  UTILIDADES
engine = pyttsx3.init()
engine.setProperty("rate", 250)
engine.setProperty("volume", 1.0)
engine.setProperty('voice', engine.getProperty('voices')[0].id)

def speak(msg: str):
    print(msg)
    engine.say(msg)
    engine.runAndWait()

with open("encodings.pickle", "rb") as f:
    enc_data = pickle.load(f)
known_encs   = enc_data["encodings"]
known_names  = enc_data["names"]

def schedule_weekly_reports():
    sched = BackgroundScheduler()
    trigger = CronTrigger(
        day_of_week="sun",
        hour=11,
        minute=0,
        timezone=PERU_TZ,
    )
    # placeholder; add job function if needed
    sched.start()
    return sched

# ────────────────────────────  LOOP PRINCIPAL
cam = cv2.VideoCapture(0)
face_locs = face_names = []
fps = cnt = 0
t0 = time.time()
last_unknown_ts = datetime.min.replace(tzinfo=timezone.utc)
scheduler = schedule_weekly_reports()

try:
    while True:
        ok, frame = cam.read()
        if not ok:
            speak("Error de cámara."); break

        small = cv2.resize(frame, (0, 0), fx=1/FRAME_SCALE, fy=1/FRAME_SCALE)
        rgb   = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        face_locs = face_recognition.face_locations(rgb, model=DETECTOR)
        face_encs = face_recognition.face_encodings(rgb, face_locs, model="large")
        face_names = []

        now = datetime.now(timezone.utc)
        for enc in face_encs:
            dists = face_recognition.face_distance(known_encs, enc)
            idx = int(np.argmin(dists))
            match = dists[idx] <= TOLERANCE
            name = known_names[idx] if match else "Desconocido"
            face_names.append(name)

            recent_names.append(name)
            voted_name = recent_names[0] if len(recent_names) == VOTE_LEN and len(set(recent_names)) == 1 else None

            if voted_name == "Desconocido":
                if now - last_unknown_ts >= UNKNOWN_COOLDOWN:
                    last_unknown_ts = now
                    speak("Usuario desconocido, por favor intente nuevamente.")
                    Thread(target=record_unknown, args=(cam,), daemon=True).start()
                continue

            if voted_name:
                last_type, last_ts = last_record(voted_name)
                if last_ts is None or now - last_ts >= ATTENDANCE_COOLDOWN:
                    next_type = "IN" if last_type in (None, "OUT") else "OUT"
                    add_record(voted_name, next_type, now)

        for (t, r, b, l), nm in zip(face_locs, face_names):
            t*=FRAME_SCALE; r*=FRAME_SCALE; b*=FRAME_SCALE; l*=FRAME_SCALE
            cv2.rectangle(frame, (l, t), (r, b), (0, 140, 255), 2)
            cv2.rectangle(frame, (l, b-25), (r, b), (0, 140, 255), cv2.FILLED)
            cv2.putText(frame, nm, (l+6, b-6), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 1)

        cnt += 1
        if time.time() - t0 >= 1:
            fps = cnt / (time.time() - t0)
            cnt = 0
            t0  = time.time()
        cv2.putText(frame, f"FPS:{fps:.1f}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        cv2.imshow("Attendance", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    cam.release()
    cv2.destroyAllWindows()
    scheduler.shutdown()
