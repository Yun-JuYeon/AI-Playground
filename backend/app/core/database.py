import asyncpg
from openai import AsyncOpenAI
from .config import (
    OPENAI_API_KEY,
    POSTGRES_URL,
    POSTGRES_HOST,
    POSTGRES_PORT,
    POSTGRES_USER,
    POSTGRES_PASSWORD,
    POSTGRES_DB,
)


class PostgresClient:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    @staticmethod
    def _pool_kwargs() -> dict:
        # Supabase pooler(pgbouncer transaction mode)와의 prepared statement 충돌 방지
        return {"statement_cache_size": 0}

    async def connect(self):
        if self.pool is not None:
            return

        pool_kwargs = self._pool_kwargs()
        
        # 서버리스 환경(Vercel)을 위해 연결 개수 최소화 설정 추가
        # Supabase 무료 티어의 연결 제한을 넘지 않도록 합니다.
        pool_kwargs.update({
            "min_size": 1,
            "max_size": 1,
            "command_timeout": 60
        })

        if POSTGRES_URL:
            # 6543 포트를 사용하는 URL인지 확인하세요!
            self.pool = await asyncpg.create_pool(dsn=POSTGRES_URL, **pool_kwargs)
        else:
            self.pool = await asyncpg.create_pool(
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                database=POSTGRES_DB,
                **pool_kwargs,
            )

        await self._init_schema()

    async def _init_schema(self):
        if self.pool is None:
            return

        async with self.pool.acquire() as conn:
            # Session-based chat history table
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    session_id VARCHAR(8) NOT NULL,
                    conversation JSONB NOT NULL DEFAULT '[]'::jsonb,
                    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    is_current BOOLEAN NOT NULL DEFAULT FALSE,
                    CONSTRAINT uq_chat_history_user_session UNIQUE (username, session_id)
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_history_username_updated
                ON chat_history (username, updated_at DESC)
                """
            )

            await conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_history_current_per_user
                ON chat_history (username)
                WHERE is_current = TRUE
                """
            )

            # Wordchain current game state per user
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wordchain_state (
                    username TEXT PRIMARY KEY,
                    used_words JSONB NOT NULL DEFAULT '[]'::jsonb,
                    score INTEGER NOT NULL DEFAULT 0,
                    is_game_over BOOLEAN NOT NULL DEFAULT FALSE,
                    difficulty INTEGER NOT NULL DEFAULT 3,
                    current_idiom TEXT,
                    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            await conn.execute(
                """
                ALTER TABLE wordchain_state
                ADD COLUMN IF NOT EXISTS messages JSONB NOT NULL DEFAULT '[]'::jsonb
                """
            )

            # Wordchain history list per user
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wordchain_history (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    difficulty INTEGER NOT NULL DEFAULT 3,
                    words_count INTEGER NOT NULL DEFAULT 0,
                    words JSONB NOT NULL DEFAULT '[]'::jsonb,
                    result TEXT NOT NULL DEFAULT 'lose',
                    played_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_wordchain_history_username_played
                ON wordchain_history (username, played_at DESC, id DESC)
                """
            )

            # Idiom current game state per user
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idiom_state (
                    username TEXT PRIMARY KEY,
                    used_words JSONB NOT NULL DEFAULT '[]'::jsonb,
                    score INTEGER NOT NULL DEFAULT 0,
                    is_game_over BOOLEAN NOT NULL DEFAULT FALSE,
                    difficulty INTEGER NOT NULL DEFAULT 3,
                    current_idiom TEXT,
                    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            await conn.execute(
                """
                ALTER TABLE idiom_state
                ADD COLUMN IF NOT EXISTS messages JSONB NOT NULL DEFAULT '[]'::jsonb
                """
            )

            await conn.execute(
                """
                ALTER TABLE idiom_state
                ADD COLUMN IF NOT EXISTS current_idiom TEXT
                """
            )

            # Idiom history list per user
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idiom_history (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    difficulty INTEGER NOT NULL DEFAULT 3,
                    words_count INTEGER NOT NULL DEFAULT 0,
                    words JSONB NOT NULL DEFAULT '[]'::jsonb,
                    result TEXT NOT NULL DEFAULT 'lose',
                    played_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_idiom_history_username_played
                ON idiom_history (username, played_at DESC, id DESC)
                """
            )

    async def close(self):
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def get_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            await self.connect()
        return self.pool


storage_client = PostgresClient()
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
