import os
from typing import Any
import psycopg2


def get_env(name: str, default: Any = None) -> str:
    value = os.getenv(name, default=default)
    if value is None:
        raise ValueError(f"Missing environment variable: {name}")
    else:
        return value


if __name__ == "__main__":
    db_host = get_env("DATABASE_HOST")
    db_port = get_env("DATABASE_PORT")
    db_name = get_env("DATABASE_NAME")
    db_user = get_env("DATABASE_USER")
    db_pass = get_env("DATABASE_PASS")
    conn = None
    try:
        print(f"Waiting for database on - {db_user}:{db_pass}@{db_host}:{db_port}/{db_name}")
        conn = psycopg2.connect(host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass)
        cursor = conn.cursor()
        cursor.close()
    except Exception:
        exit(1)
    finally:
        if conn:
            conn.close()
