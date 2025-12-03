import json
from ..core.database import redis_client, openai_client
from ..core.config import SYSTEM_PROMPT


def get_conversation_key(username: str) -> str:
    return f"chat:conversation:{username}"


def get_messages_key(username: str) -> str:
    return f"chat:messages:{username}"


def get_chat_history_key(username: str) -> str:
    return f"chat:history:{username}"


async def get_conversation(username: str) -> list[dict]:
    """Get conversation history from Redis"""
    key = get_conversation_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return [{"role": "system", "content": SYSTEM_PROMPT}]


async def save_conversation(username: str, messages: list[dict]):
    """Save conversation history to Redis"""
    key = get_conversation_key(username)
    await redis_client.set(key, json.dumps(messages))


async def get_chat_messages(username: str) -> list[dict]:
    """Get chat messages for UI display from Redis"""
    key = get_messages_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return []


async def save_chat_messages(username: str, messages: list[dict]):
    """Save chat messages for UI display to Redis"""
    key = get_messages_key(username)
    await redis_client.set(key, json.dumps(messages))


async def clear_conversation(username: str):
    """Clear conversation history for a user"""
    conv_key = get_conversation_key(username)
    msg_key = get_messages_key(username)
    await redis_client.delete(conv_key, msg_key)


async def get_ai_response(conversation: list[dict]) -> str:
    """Get AI response from OpenAI"""
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation,
        max_tokens=1000,
    )
    return response.choices[0].message.content


async def get_chat_history(username: str) -> list[dict]:
    """Get all past chat sessions for sidebar"""
    key = get_chat_history_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return []


async def save_chat_to_history(username: str, chat_session: dict):
    """Save completed chat session to history"""
    key = get_chat_history_key(username)
    history = await get_chat_history(username)
    history.insert(0, chat_session)
    # 최대 20개만 저장
    if len(history) > 20:
        history = history[:20]
    await redis_client.set(key, json.dumps(history))
