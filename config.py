import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

DB_CONFIG = {
    'host':     os.environ.get("DB_HOST", "127.0.0.1"),
    'port':     int(os.environ.get("DB_PORT", "3306")),
    'user':     os.environ.get("DB_USER", "root"),
    'password': os.environ.get("DB_PASSWORD", ""),
    'database': os.environ.get("DB_NAME", "job_tracker"),
    'charset':  'utf8mb4',
}
