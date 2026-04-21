"""
Database Module — PostgreSQL connection helper for the Streamlit app.

Provides cached connections and a query helper.
Falls back gracefully when PostgreSQL is unavailable (LOCAL_MODE).
"""

import os
import logging
import streamlit as st

logger = logging.getLogger(__name__)

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "f1chubby")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() in ("1", "true", "yes")


def _is_pg_configured():
    return bool(POSTGRES_HOST) and bool(POSTGRES_PASSWORD) and not LOCAL_MODE


@st.cache_resource(show_spinner=False)
def _get_pool():
    """Create a psycopg2 connection pool (cached for the Streamlit process lifetime)."""
    import psycopg2
    from psycopg2 import pool as pg_pool

    return pg_pool.SimpleConnectionPool(
        minconn=1,
        maxconn=3,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=5,
    )


def get_connection():
    """Get a connection from the pool. Caller must call put_connection() after use."""
    p = _get_pool()
    return p.getconn()


def put_connection(conn):
    p = _get_pool()
    p.putconn(conn)


def query(sql: str, params=None):
    """Execute a read query and return rows as a list of dicts. Returns None on failure."""
    if not _is_pg_configured():
        return None
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(cols, row)) for row in rows]
        finally:
            put_connection(conn)
    except Exception as e:
        logger.warning("PostgreSQL query failed: %s", e)
        return None
