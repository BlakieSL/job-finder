import os
import sys
from contextlib import contextmanager
from mysql.connector import pooling

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import DB_CONFIG

pool = pooling.MySQLConnectionPool(
    pool_name="dashboard",
    pool_size=5,
    host=DB_CONFIG['host'],
    port=DB_CONFIG['port'],
    user=DB_CONFIG['user'],
    password=DB_CONFIG['password'],
    database=DB_CONFIG['database'],
)

@contextmanager
def get_conn():
    conn = pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()
