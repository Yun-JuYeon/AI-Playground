import asyncio
import json
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services.chat_service import (
    create_new_session,
    get_current_session_id,
    get_session,
    save_session,
    switch_session,
    get_all_sessions,
    get_ai_response_stream,
    delete_session
)

router = APIRouter()
chat_event_listeners: dict[str, list[asyncio.Queue]] = defaultdict(list)


class ChatRequest(BaseModel):
    message: str


def _current_messages(session: dict) -> list[dict]:
    return session.get("messages") or []


async def broadcast_chat_event(username: str, payload: dict):
    listeners = list(chat_event_listeners.get(username, []))
    for queue in listeners:
        try:
            await queue.put(payload)
        except asyncio.CancelledError:
            continue


@router.post("/api/chat/new/{username}")
async def new_chat(username: str):
    """Create a new chat session"""
    session_id = await create_new_session(username)
    return {"success": True, "session_id": session_id}


@router.get("/api/chat/sessions/{username}")
async def get_chat_sessions(username: str):
    """Get all chat sessions for sidebar"""
    sessions = await get_all_sessions(username)
    current_id = await get_current_session_id(username)
    return {"sessions": sessions, "current_id": current_id}


@router.post("/api/chat/switch/{username}/{session_id}")
async def switch_chat_session(username: str, session_id: str):
    """Switch to a different chat session"""
    session = await switch_session(username, session_id)
    if session:
        return {"success": True, "messages": session.get("messages", [])}
    return {"success": False, "message": "Session not found"}


@router.delete("/api/chat/session/{username}/{session_id}")
async def delete_chat_session(username: str, session_id: str):
    """Delete a specific chat session"""
    await delete_session(username, session_id)
    return {"success": True}


@router.post("/api/chat/send/{username}")
async def send_message(username: str, request: ChatRequest):
    """Send a message and get AI response"""
    message = request.message
    session_id = await get_current_session_id(username)
    if not session_id:
        return {"error": "No active session"}

    session = await get_session(username, session_id)
    if not session:
        return {"error": "Session not found"}

    user_msg = {
        "type": "message",
        "username": username,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    session_messages = _current_messages(session)
    session_messages.append(user_msg)
    session["messages"] = session_messages
    await save_session(username, session_id, session)
    await broadcast_chat_event(username, user_msg)
    await broadcast_chat_event(username, {"type": "session_updated"})

    conversation = session.get("conversation", [])
    conversation.append({"role": "user", "content": message})

    await broadcast_chat_event(username, {"type": "ai_stream_start", "timestamp": datetime.now().isoformat()})

    ai_parts = []
    try:
        async for chunk in get_ai_response_stream(conversation):
            if not chunk:
                continue
            ai_parts.append(chunk)
            await broadcast_chat_event(username, {"type": "ai_stream_chunk", "delta": chunk})
    except Exception as exc:
        error_msg = {
            "type": "system",
            "message": f"AI 응답 오류: {str(exc)}",
            "timestamp": datetime.now().isoformat()
        }
        session_messages.append(error_msg)
        session["conversation"] = conversation
        await save_session(username, session_id, session)
        await broadcast_chat_event(username, error_msg)
        await broadcast_chat_event(username, {"type": "session_updated"})
        return {"success": False, "error": str(exc)}

    ai_response = "".join(ai_parts).strip()
    conversation.append({"role": "assistant", "content": ai_response})
    session["conversation"] = conversation

    ai_msg = {
        "type": "message",
        "username": "AI",
        "message": ai_response,
        "timestamp": datetime.now().isoformat()
    }
    session_messages.append(ai_msg)
    session["messages"] = session_messages
    await save_session(username, session_id, session)
    await broadcast_chat_event(username, {"type": "ai_stream_end", "ai_message": ai_msg})
    await broadcast_chat_event(username, {"type": "session_updated"})

    return {"success": True, "ai_message": ai_msg}


@router.get("/api/chat/stream/{username}")
async def stream_messages(username: str):
    """Stream messages using SSE"""

    async def event_generator():
        queue = asyncio.Queue()
        listeners = chat_event_listeners.setdefault(username, [])
        listeners.append(queue)

        def format_payload(payload: dict) -> str:
            return f"data: {json.dumps(payload)}\n\n"

        try:
            session_id = await get_current_session_id(username)
            if not session_id:
                yield format_payload({"error": "No active session"})
                return

            session = await get_session(username, session_id)
            if not session:
                yield format_payload({"error": "Session not found"})
                return

            yield format_payload({"type": "session_info", "session_id": session_id})
            yield format_payload({"type": "history", "messages": session.get("messages", [])})

            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=25)
                except asyncio.TimeoutError:
                    yield format_payload({"type": "ping"})
                    continue

                yield format_payload(payload)
        finally:
            listeners = chat_event_listeners.get(username)
            if listeners and queue in listeners:
                listeners.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
