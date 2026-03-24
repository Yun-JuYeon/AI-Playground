import json
import uuid
from typing import AsyncGenerator
from datetime import datetime
from asyncpg import UniqueViolationError
from ..core.database import storage_client, openai_client
from ..core.config import SYSTEM_PROMPT


MAX_SESSIONS_PER_USER = 20


def _session_row_to_dict(row) -> dict:
    if not row:
        return None

    conversation = row["conversation"]
    messages = row["messages"]

    if isinstance(conversation, str):
        conversation = json.loads(conversation)
    if isinstance(messages, str):
        messages = json.loads(messages)

    created_at = row["created_at"]
    updated_at = row["updated_at"]

    return {
        "id": row["session_id"],
        "conversation": conversation or [],
        "messages": messages or [],
        "created_at": created_at.isoformat() if created_at else datetime.now().isoformat(),
        "updated_at": updated_at.isoformat() if updated_at else datetime.now().isoformat(),
    }


async def _enforce_session_limit(conn, username: str):
    await conn.execute(
        """
        DELETE FROM chat_history
        WHERE username = $1
          AND session_id IN (
            SELECT session_id
            FROM (
              SELECT session_id,
                     ROW_NUMBER() OVER (
                       PARTITION BY username
                       ORDER BY updated_at DESC
                     ) AS rn
              FROM chat_history
              WHERE username = $1
            ) ranked
            WHERE rn > $2
          )
        """,
        username,
        MAX_SESSIONS_PER_USER,
    )


async def create_new_session(username: str) -> str:
    """Create a new chat session and return its ID"""
    pool = await storage_client.get_pool()

    for _ in range(5):
        session_id = str(uuid.uuid4())[:8]
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages = []

        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE chat_history SET is_current = FALSE WHERE username = $1",
                    username,
                )

                try:
                    await conn.execute(
                        """
                        INSERT INTO chat_history (
                            username,
                            session_id,
                            conversation,
                            messages,
                            is_current
                        ) VALUES (
                            $1,
                            $2,
                            $3::jsonb,
                            $4::jsonb,
                            TRUE
                        )
                        """,
                        username,
                        session_id,
                        json.dumps(conversation),
                        json.dumps(messages),
                    )
                except UniqueViolationError:
                    continue

                await _enforce_session_limit(conn, username)
                return session_id

    raise RuntimeError("Failed to create unique session id")


async def get_current_session_id(username: str) -> str:
    """Get current session ID, create new if none exists"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT session_id
            FROM chat_history
            WHERE username = $1 AND is_current = TRUE
            LIMIT 1
            """,
            username,
        )

    if row:
        return row["session_id"]

    return await create_new_session(username)


async def get_session(username: str, session_id: str) -> dict:
    """Get session data by ID"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT session_id, conversation, messages, created_at, updated_at
            FROM chat_history
            WHERE username = $1 AND session_id = $2
            LIMIT 1
            """,
            username,
            session_id,
        )

    return _session_row_to_dict(row)


async def save_session(username: str, session_id: str, session_data: dict):
    """Save session data"""
    pool = await storage_client.get_pool()

    conversation = session_data.get("conversation", [])
    messages = session_data.get("messages", [])

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE chat_history SET is_current = FALSE WHERE username = $1",
                username,
            )

            await conn.execute(
                """
                UPDATE chat_history
                SET conversation = $3::jsonb,
                    messages = $4::jsonb,
                    updated_at = NOW(),
                    is_current = TRUE
                WHERE username = $1 AND session_id = $2
                """,
                username,
                session_id,
                json.dumps(conversation),
                json.dumps(messages),
            )

            await _enforce_session_limit(conn, username)


async def switch_session(username: str, session_id: str) -> dict:
    """Switch to a different session"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            exists = await conn.fetchval(
                """
                SELECT 1
                FROM chat_history
                WHERE username = $1 AND session_id = $2
                """,
                username,
                session_id,
            )

            if not exists:
                return None

            await conn.execute(
                "UPDATE chat_history SET is_current = FALSE WHERE username = $1",
                username,
            )
            await conn.execute(
                """
                UPDATE chat_history
                SET is_current = TRUE,
                    updated_at = NOW()
                WHERE username = $1 AND session_id = $2
                """,
                username,
                session_id,
            )

        row = await conn.fetchrow(
            """
            SELECT session_id, conversation, messages, created_at, updated_at
            FROM chat_history
            WHERE username = $1 AND session_id = $2
            LIMIT 1
            """,
            username,
            session_id,
        )

    return _session_row_to_dict(row)


async def get_all_sessions(username: str) -> list[dict]:
    """Get all sessions for sidebar display"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT session_id, messages, created_at, updated_at
            FROM chat_history
            WHERE username = $1
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            username,
            MAX_SESSIONS_PER_USER,
        )

    sessions = []
    for row in rows:
        messages = row["messages"]
        if isinstance(messages, str):
            messages = json.loads(messages)

        user_messages = [
            m for m in (messages or [])
            if m.get("type") == "message" and m.get("username") != "AI"
        ]

        preview = ""
        if user_messages:
            preview = user_messages[0]["message"][:30]
            if len(user_messages[0]["message"]) > 30:
                preview += "..."

        sessions.append({
            "id": row["session_id"],
            "preview": preview or "새 대화",
            "message_count": len([
                m for m in (messages or []) if m.get("type") == "message"
            ]),
            "updated_at": (row["updated_at"] or row["created_at"]).isoformat(),
        })

    return sessions


async def delete_session(username: str, session_id: str) -> bool:
    """Delete a specific chat session"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        async with conn.transaction():
            deleted_row = await conn.fetchrow(
                """
                DELETE FROM chat_history
                WHERE username = $1 AND session_id = $2
                RETURNING is_current
                """,
                username,
                session_id,
            )

            if not deleted_row:
                return False

            if deleted_row["is_current"]:
                next_row = await conn.fetchrow(
                    """
                    SELECT session_id
                    FROM chat_history
                    WHERE username = $1
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    username,
                )

                if next_row:
                    await conn.execute(
                        """
                        UPDATE chat_history
                        SET is_current = TRUE
                        WHERE username = $1 AND session_id = $2
                        """,
                        username,
                        next_row["session_id"],
                    )

    return True


async def get_ai_response(conversation: list[dict]) -> str:
    """Get AI response from OpenAI"""
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation,
        max_tokens=1000,
    )
    return response.choices[0].message.content


async def get_ai_response_stream(conversation: list[dict]) -> AsyncGenerator[str, None]:
    """Stream AI response chunks from OpenAI"""
    stream = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation,
        max_tokens=1000,
        stream=True,
    )

    async for chunk in stream:
        if not chunk.choices:
            continue

        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
