"""PostgreSQL connection utility with Cloud SQL support."""
import os
import time

import psycopg2

from src.config import app_config
from src.shared.db.exceptions import map_psycopg2_exception


class DatabaseUtils:
    @staticmethod
    def db_connect(max_retries: int = 3, retry_delay: float = 1.0):
        if os.path.exists("/cloudsql"):
            cloud_sql_connection_name = app_config.CLOUD_SQL_CONNECTION_NAME
            if not cloud_sql_connection_name:
                raise ValueError("CLOUD_SQL_CONNECTION_NAME is required for Cloud SQL connection")
            unix_socket = f"/cloudsql/{cloud_sql_connection_name}"
            return psycopg2.connect(
                host=unix_socket,
                database=app_config.DB_NAME,
                user=app_config.DB_USER,
                password=app_config.DB_PASSWORD,
            )

        host = app_config.DB_HOST
        port = app_config.DB_PORT
        name = app_config.DB_NAME
        user = app_config.DB_USER
        password = app_config.DB_PASSWORD
        sslmode = app_config.DB_SSLMODE

        missing = [env for env, value in {
            "DB_HOST": host, "DB_NAME": name, "DB_USER": user,
        }.items() if not value]
        if missing:
            raise ValueError(f"Missing required database settings: {', '.join(missing)}")

        conn_args = {"host": host, "port": port, "dbname": name, "user": user}
        if password:
            conn_args["password"] = password
        if sslmode:
            conn_args["sslmode"] = sslmode

        last_exception = None
        for attempt in range(max_retries):
            try:
                return psycopg2.connect(**conn_args)
            except psycopg2.OperationalError as e:
                last_exception = e
                error_msg = str(e).lower()
                if any(kw in error_msg for kw in ["password", "authentication", "permission"]):
                    raise map_psycopg2_exception(e, "connecting to database")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (2 ** attempt))
            except Exception as e:
                raise map_psycopg2_exception(e, "connecting to database")

        if last_exception:
            raise map_psycopg2_exception(last_exception, f"connecting to database after {max_retries} attempts")
