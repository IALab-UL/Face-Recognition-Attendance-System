import os
from dotenv import load_dotenv, find_dotenv

REQUIRED_ENV_VARS = [
    # Firebase
    "FIREBASE_SA_PATH",
    "FIREBASE_BUCKET",

    # PostgreSQL
    "PG_USER",
    "PG_PASSWORD",
    "PG_HOST",
    "PG_PORT",
    "PG_DBNAME",

    # SMTP
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",

    # Tuning
    "FR_TOLERANCE",
    "FR_DET_MODEL",
    "FR_SCALE",
    "FR_VOTE_FRAMES",
]

# Load and verify .env file
env_path = find_dotenv()
print("Usando .env en:", env_path)
load_dotenv(dotenv_path=env_path)

# Check for missing variables
missing_vars = [var for var in REQUIRED_ENV_VARS if os.getenv(var) is None]
if missing_vars:
    print("⚠️  Variables faltantes en el .env:", ", ".join(missing_vars))
    exit(1)

# Print loaded environment values (optional, sensitive values masked)
print("✔️  Todas las variables requeridas fueron cargadas correctamente:")
for var in REQUIRED_ENV_VARS:
    value = os.getenv(var)
    if "PASSWORD" in var or "KEY" in var:
        value = "********"
    print(f"  {var} = {value}")
