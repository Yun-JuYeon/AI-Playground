from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime
from ..services.chat_service import (
    create_new_session,
    get_current_session_id,
    get_session,
    save_session,
    switch_session,
    get_all_sessions,
    get_ai_response,
    delete_session
)

router = APIRouter()


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


@router.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()

    # Get or create current session
    session_id = await get_current_session_id(username)
    session = await get_session(username, session_id)

    if not session:
        session_id = await create_new_session(username)
        session = await get_session(username, session_id)

    conversation = session.get("conversation", [])
    chat_messages = session.get("messages", [])

    is_new_session = len(chat_messages) == 0

    if is_new_session:
        welcome_msg = {
            "type": "system",
            "message": f"{username}님, 환영합니다! AI와 대화를 시작하세요.",
            "timestamp": datetime.now().isoformat()
        }
    else:
        welcome_msg = {
            "type": "system",
            "message": f"{username}님, 다시 오셨네요! 이전 대화를 이어갑니다.",
            "timestamp": datetime.now().isoformat()
        }

    # Send current session ID first
    await websocket.send_json({
        "type": "session_info",
        "session_id": session_id
    })

    await websocket.send_json(welcome_msg)

    if chat_messages:
        await websocket.send_json({
            "type": "history",
            "messages": chat_messages
        })

    try:
        while True:
            data = await websocket.receive_text()
            timestamp = datetime.now().isoformat()

            user_msg = {
                "type": "message",
                "username": username,
                "message": data,
                "timestamp": timestamp
            }

            await websocket.send_json(user_msg)

            chat_messages.append(user_msg)
            conversation.append({"role": "user", "content": data})

            # Save session
            session["conversation"] = conversation
            session["messages"] = chat_messages
            await save_session(username, session_id, session)

            # Notify client to update sidebar
            await websocket.send_json({"type": "session_updated"})

            try:
                ai_message = await get_ai_response(conversation)
                conversation.append({"role": "assistant", "content": ai_message})

                ai_timestamp = datetime.now().isoformat()
                ai_msg = {
                    "type": "message",
                    "username": "AI",
                    "message": ai_message,
                    "timestamp": ai_timestamp
                }

                chat_messages.append(ai_msg)

                # Save session again with AI response
                session["conversation"] = conversation
                session["messages"] = chat_messages
                await save_session(username, session_id, session)

                await websocket.send_json(ai_msg)

                # Notify client to update sidebar again
                await websocket.send_json({"type": "session_updated"})

            except Exception as e:
                await websocket.send_json({
                    "type": "system",
                    "message": f"AI 응답 오류: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })

    except WebSocketDisconnect:
        print(f"[{username}] 연결 종료")
