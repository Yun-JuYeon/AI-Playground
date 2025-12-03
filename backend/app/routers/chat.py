from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime
from ..services.chat_service import (
    get_conversation,
    save_conversation,
    get_chat_messages,
    save_chat_messages,
    clear_conversation,
    get_ai_response,
    get_chat_history,
    save_chat_to_history
)

router = APIRouter()


@router.post("/api/clear/{username}")
async def clear_chat(username: str):
    # 현재 대화를 히스토리에 저장
    chat_messages = await get_chat_messages(username)
    if len(chat_messages) > 0:
        # 첫 메시지와 메시지 수 저장
        first_msg = next((m for m in chat_messages if m.get("type") == "message"), None)
        await save_chat_to_history(username, {
            "preview": first_msg["message"][:30] + "..." if first_msg and len(first_msg["message"]) > 30 else (first_msg["message"] if first_msg else "대화"),
            "message_count": len([m for m in chat_messages if m.get("type") == "message"]),
            "timestamp": datetime.now().isoformat()
        })

    await clear_conversation(username)
    return {"success": True, "message": "대화 기록이 초기화되었습니다."}


@router.get("/api/history/{username}")
async def get_history(username: str):
    messages = await get_chat_messages(username)
    return {"messages": messages}


@router.get("/api/chat/sessions/{username}")
async def get_chat_sessions(username: str):
    """Get past chat sessions for sidebar"""
    history = await get_chat_history(username)
    return {"sessions": history}


@router.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()

    conversation = await get_conversation(username)
    chat_messages = await get_chat_messages(username)

    is_new_user = len(conversation) <= 1

    if is_new_user:
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

            await save_chat_messages(username, chat_messages)
            await save_conversation(username, conversation)

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

                await save_chat_messages(username, chat_messages)
                await save_conversation(username, conversation)

                await websocket.send_json(ai_msg)

            except Exception as e:
                await websocket.send_json({
                    "type": "system",
                    "message": f"AI 응답 오류: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })

    except WebSocketDisconnect:
        print(f"[{username}] 연결 종료")
