import json
import uuid
from datetime import datetime
from ..core.database import redis_client, openai_client
from ..core.config import SYSTEM_PROMPT


def get_session_key(username: str, session_id: str) -> str:
    """Get Redis key for a specific chat session"""
    return f"chat:session:{username}:{session_id}"


def get_session_list_key(username: str) -> str:
    """Get Redis key for user's session list"""
    return f"chat:sessions:{username}"


def get_current_session_key(username: str) -> str:
    """Get Redis key for user's current session ID"""
    return f"chat:current:{username}"


async def create_new_session(username: str) -> str:
    """Create a new chat session and return its ID"""
    session_id = str(uuid.uuid4())[:8]

    # Initialize session data
    session_data = {
        "id": session_id,
        "conversation": [{"role": "system", "content": SYSTEM_PROMPT}],
        "messages": [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

    # Save session
    await redis_client.set(
        get_session_key(username, session_id),
        json.dumps(session_data)
    )

    # Set as current session
    await redis_client.set(get_current_session_key(username), session_id)

    # Add to session list
    await add_session_to_list(username, session_id)

    return session_id


async def add_session_to_list(username: str, session_id: str):
    """Add session ID to user's session list"""
    key = get_session_list_key(username)
    data = await redis_client.get(key)
    sessions = json.loads(data) if data else []

    # Remove if already exists (to move to front)
    if session_id in sessions:
        sessions.remove(session_id)

    # Add to front
    sessions.insert(0, session_id)

    # Keep max 20 sessions
    if len(sessions) > 20:
        # Delete old session data
        old_id = sessions.pop()
        await redis_client.delete(get_session_key(username, old_id))

    await redis_client.set(key, json.dumps(sessions))


async def get_current_session_id(username: str) -> str:
    """Get current session ID, create new if none exists"""
    key = get_current_session_key(username)
    session_id = await redis_client.get(key)

    if session_id:
        return session_id

    # Create new session if none exists
    return await create_new_session(username)


async def get_session(username: str, session_id: str) -> dict:
    """Get session data by ID"""
    key = get_session_key(username, session_id)
    data = await redis_client.get(key)

    if data:
        return json.loads(data)

    return None


async def save_session(username: str, session_id: str, session_data: dict):
    """Save session data"""
    session_data["updated_at"] = datetime.now().isoformat()

    await redis_client.set(
        get_session_key(username, session_id),
        json.dumps(session_data)
    )

    # Move to front of list
    await add_session_to_list(username, session_id)


async def switch_session(username: str, session_id: str) -> dict:
    """Switch to a different session"""
    session = await get_session(username, session_id)

    if session:
        await redis_client.set(get_current_session_key(username), session_id)
        return session

    return None


async def get_all_sessions(username: str) -> list[dict]:
    """Get all sessions for sidebar display"""
    # 기존 데이터 마이그레이션 체크
    await migrate_old_data(username)

    list_key = get_session_list_key(username)
    data = await redis_client.get(list_key)
    session_ids = json.loads(data) if data else []

    sessions = []
    for sid in session_ids:
        session = await get_session(username, sid)
        if session:
            # Get preview from first user message
            user_messages = [m for m in session.get("messages", []) if m.get("type") == "message" and m.get("username") != "AI"]
            preview = ""
            if user_messages:
                preview = user_messages[0]["message"][:30]
                if len(user_messages[0]["message"]) > 30:
                    preview += "..."

            sessions.append({
                "id": session["id"],
                "preview": preview or "새 대화",
                "message_count": len([m for m in session.get("messages", []) if m.get("type") == "message"]),
                "updated_at": session.get("updated_at", session.get("created_at"))
            })

    return sessions


async def migrate_old_data(username: str):
    """Migrate old chat data to new session format"""
    old_conv_key = f"chat:conversation:{username}"
    old_msg_key = f"chat:messages:{username}"

    old_conv = await redis_client.get(old_conv_key)
    old_msg = await redis_client.get(old_msg_key)

    if old_msg:
        messages = json.loads(old_msg)
        if messages:
            # Create a session from old data
            session_id = str(uuid.uuid4())[:8]
            conversation = json.loads(old_conv) if old_conv else [{"role": "system", "content": SYSTEM_PROMPT}]

            session_data = {
                "id": session_id,
                "conversation": conversation,
                "messages": messages,
                "created_at": messages[0].get("timestamp", datetime.now().isoformat()) if messages else datetime.now().isoformat(),
                "updated_at": messages[-1].get("timestamp", datetime.now().isoformat()) if messages else datetime.now().isoformat()
            }

            await redis_client.set(
                get_session_key(username, session_id),
                json.dumps(session_data)
            )

            await add_session_to_list(username, session_id)
            await redis_client.set(get_current_session_key(username), session_id)

    # Delete old keys
    await redis_client.delete(old_conv_key, old_msg_key)


async def delete_session(username: str, session_id: str) -> bool:
    """Delete a specific chat session"""
    # Delete session data
    await redis_client.delete(get_session_key(username, session_id))

    # Remove from session list
    list_key = get_session_list_key(username)
    data = await redis_client.get(list_key)
    sessions = json.loads(data) if data else []

    if session_id in sessions:
        sessions.remove(session_id)
        await redis_client.set(list_key, json.dumps(sessions))

    # If deleted session was current, switch to another or create new
    current_id = await redis_client.get(get_current_session_key(username))
    if current_id == session_id:
        if sessions:
            await redis_client.set(get_current_session_key(username), sessions[0])
        else:
            await redis_client.delete(get_current_session_key(username))

    return True


async def get_ai_response(conversation: list[dict]) -> str:
    """Get AI response from OpenAI"""
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=conversation,
        max_tokens=1000,
    )
    return response.choices[0].message.content
