import sys
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

# ────────────────────────────  CARGAR .env
load_dotenv()

# ────────────────────────────  VALIDACIÓN DE VARIABLES DE ENTORNO
required_vars = [
    "PG_HOST",
    "PG_PORT",
    "PG_USER",
    "PG_PASSWORD",
    "PG_DBNAME",
]
missing = [v for v in required_vars if not os.getenv(v)]
if missing:
    raise RuntimeError(f"Variables de entorno faltantes: {', '.join(missing)}")

# ────────────────────────────  ARGUMENTOS Y CONEXIÓN
if len(sys.argv) != 2:
    sys.exit("Uso: python export_single_video.py <video_id>")

video_id = int(sys.argv[1])

DB = {
    "host":     os.getenv("PG_HOST"),
    "port":     int(os.getenv("PG_PORT")),
    "user":     os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "dbname":   os.getenv("PG_DBNAME"),
}

conn = psycopg2.connect(**DB)
output_dir = Path("exported_unknown_videos")
output_dir.mkdir(exist_ok=True)

with conn.cursor() as cur:
    cur.execute(
        "SELECT id, ts, mp4 FROM unknown_videos WHERE id = %s LIMIT 1;",
        (video_id,),
    )
    row = cur.fetchone()
    if not row:
        sys.exit(f"Video ID {video_id} no encontrado")

    vid_id, ts, mp4 = row
    fname = output_dir / f"unknown_{vid_id}_{ts:%Y%m%d_%H%M%S}.mp4"
    with open(fname, "wb") as f:
        f.write(mp4)
    print(f"✔️  Video guardado en: {fname}")

conn.close()
