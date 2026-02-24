import os
import json
import logging
import boto3
import psycopg2
import psycopg2.pool

logger = logging.getLogger()

_db_config = None
_connection_pool = None


def get_db_config() -> dict:
    global _db_config
    if _db_config:
        return _db_config

    secret_arn = os.environ.get("SECRET_ARN")
    client     = boto3.client("secretsmanager")
    try:
        response = client.get_secret_value(SecretId=secret_arn)
        secret   = json.loads(response["SecretString"])
        _db_config = {
            "host":     secret["host"],
            "database": secret["db_name"],
            "user":     secret["username"],
            "password": secret["password"],
            "port":     secret.get("port", 5432),
        }
        return _db_config
    except Exception as e:
        logger.error(f"Failed to retrieve database secrets: {str(e)}")
        raise


def get_pool() -> psycopg2.pool.SimpleConnectionPool:
    global _connection_pool
    if _connection_pool is None:
        config = get_db_config()
        _connection_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            **config
        )
    return _connection_pool


def get_conn():
    pool = get_pool()
    conn = pool.getconn()
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        logger.warning("Zombie connection detected, reopening...")
        try:
            conn.close()
        except Exception:
            pass
        conn = psycopg2.connect(**get_db_config())
    return conn


def put_conn(conn):
    get_pool().putconn(conn)
