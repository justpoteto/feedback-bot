from os import getenv
from dotenv import load_dotenv
import asyncpg
from typing import Optional

load_dotenv()

_pool: Optional[asyncpg.Pool] = None

async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(getenv("DB_URL"))
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS forward_messages (
                id SERIAL PRIMARY KEY,
                msg_id BIGINT,
                user_id BIGINT,
                date TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS banned (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                date TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                date TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS forward_relations (
                button_msg_id BIGINT PRIMARY KEY,
                message_data TEXT,
                user_id BIGINT
            );
        """)

def get_pool() -> asyncpg.Pool:
    return _pool
