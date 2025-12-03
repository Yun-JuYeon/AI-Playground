import os
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from openai import AsyncOpenAI
from dotenv import load_dotenv
import redis.asyncio as redis

load_dotenv()

app = FastAPI()
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Redis connection
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    decode_responses=True
)

SYSTEM_PROMPT = "You are a helpful assistant. Respond in the same language the user uses. Keep responses concise and friendly."

WORDCHAIN_PROMPT = """You are playing a Korean word chain game (끝말잇기).
Rules:
1. The user says a Korean word
2. You must respond with a Korean word that starts with the last character of the user's word
3. Words cannot be repeated (check the used_words list in the conversation)
4. Only use common Korean nouns (no proper nouns, no single characters)
5. If you cannot find a valid word, respond with exactly: 패배

IMPORTANT: Respond ONLY with a single Korean word. No explanations, no punctuation, no extra text."""

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conversation_key(username: str) -> str:
    return f"chat:conversation:{username}"


def get_messages_key(username: str) -> str:
    return f"chat:messages:{username}"


def get_wordchain_key(username: str) -> str:
    return f"wordchain:game:{username}"


def get_wordchain_messages_key(username: str) -> str:
    return f"wordchain:messages:{username}"


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


# 끝말잇기 관련 함수들
async def get_wordchain_game(username: str) -> dict:
    """Get wordchain game state from Redis"""
    key = get_wordchain_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return {"used_words": [], "score": 0, "is_game_over": False}


async def save_wordchain_game(username: str, game_state: dict):
    """Save wordchain game state to Redis"""
    key = get_wordchain_key(username)
    await redis_client.set(key, json.dumps(game_state))


async def get_wordchain_messages(username: str) -> list[dict]:
    """Get wordchain messages for UI display from Redis"""
    key = get_wordchain_messages_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return []


async def save_wordchain_messages(username: str, messages: list[dict]):
    """Save wordchain messages for UI display to Redis"""
    key = get_wordchain_messages_key(username)
    await redis_client.set(key, json.dumps(messages))


async def clear_wordchain(username: str):
    """Clear wordchain game for a user"""
    game_key = get_wordchain_key(username)
    msg_key = get_wordchain_messages_key(username)
    await redis_client.delete(game_key, msg_key)


def get_last_char(word: str) -> str:
    """Get the last character of a Korean word, handling compound consonants"""
    if not word:
        return ""
    return word[-1]


def is_valid_korean_word(word: str) -> bool:
    """Check if a word contains only Korean characters"""
    if not word or len(word) < 2:
        return False
    for char in word:
        if not ('가' <= char <= '힣'):
            return False
    return True


@app.get("/")
async def root():
    return {"message": "Chat Server Running"}


@app.post("/api/clear/{username}")
async def clear_chat(username: str):
    """Clear conversation history and start fresh"""
    await clear_conversation(username)
    return {"success": True, "message": "대화 기록이 초기화되었습니다."}


@app.post("/api/wordchain/restart/{username}")
async def restart_wordchain(username: str):
    """Restart wordchain game"""
    await clear_wordchain(username)
    return {"success": True, "message": "게임이 재시작되었습니다."}


@app.get("/api/history/{username}")
async def get_history(username: str):
    """Get chat history for a user"""
    messages = await get_chat_messages(username)
    return {"messages": messages}


@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()

    # Load conversation history from Redis
    conversation = await get_conversation(username)
    chat_messages = await get_chat_messages(username)

    is_new_user = len(conversation) <= 1

    # Send welcome message
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

    # Send previous chat messages if exists
    if chat_messages:
        await websocket.send_json({
            "type": "history",
            "messages": chat_messages
        })

    try:
        while True:
            # Receive user message
            data = await websocket.receive_text()

            timestamp = datetime.now().isoformat()

            # User message for UI
            user_msg = {
                "type": "message",
                "username": username,
                "message": data,
                "timestamp": timestamp
            }

            # Echo user's message back
            await websocket.send_json(user_msg)

            # Add to chat messages and conversation
            chat_messages.append(user_msg)
            conversation.append({"role": "user", "content": data})

            # Save to Redis
            await save_chat_messages(username, chat_messages)
            await save_conversation(username, conversation)

            # Get AI response
            try:
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=conversation,
                    max_tokens=1000,
                )

                ai_message = response.choices[0].message.content

                # Add AI response to conversation history
                conversation.append({"role": "assistant", "content": ai_message})

                ai_timestamp = datetime.now().isoformat()
                ai_msg = {
                    "type": "message",
                    "username": "AI",
                    "message": ai_message,
                    "timestamp": ai_timestamp
                }

                # Add to chat messages
                chat_messages.append(ai_msg)

                # Save to Redis
                await save_chat_messages(username, chat_messages)
                await save_conversation(username, conversation)

                # Send AI response
                await websocket.send_json(ai_msg)

            except Exception as e:
                await websocket.send_json({
                    "type": "system",
                    "message": f"AI 응답 오류: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })

    except WebSocketDisconnect:
        print(f"[{username}] 연결 종료 - 대화 기록은 Redis에 저장됨")


@app.websocket("/ws/wordchain/{username}")
async def wordchain_endpoint(websocket: WebSocket, username: str):
    await websocket.accept()

    # Load game state from Redis
    game_state = await get_wordchain_game(username)
    wc_messages = await get_wordchain_messages(username)

    used_words = game_state.get("used_words", [])
    score = game_state.get("score", 0)
    is_game_over = game_state.get("is_game_over", False)

    # Send welcome message
    if not wc_messages:
        welcome_msg = {
            "type": "system",
            "message": f"{username}님, 끝말잇기를 시작합니다! 아무 단어나 입력하세요.",
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_json(welcome_msg)
    else:
        # Send history
        await websocket.send_json({
            "type": "history",
            "messages": wc_messages,
            "score": score,
            "isGameOver": is_game_over
        })
        if not is_game_over:
            await websocket.send_json({
                "type": "system",
                "message": "이전 게임을 이어갑니다!",
                "timestamp": datetime.now().isoformat()
            })

    last_word = used_words[-1] if used_words else None

    try:
        while True:
            data = await websocket.receive_text()
            word = data.strip()
            timestamp = datetime.now().isoformat()

            # Check if game is over
            if is_game_over:
                await websocket.send_json({
                    "type": "system",
                    "message": "게임이 끝났습니다. 다시 시작하려면 '다시 시작' 버튼을 누르세요.",
                    "timestamp": timestamp
                })
                continue

            # Validate Korean word
            if not is_valid_korean_word(word):
                await websocket.send_json({
                    "type": "system",
                    "message": "올바른 한글 단어를 입력하세요 (2글자 이상)",
                    "timestamp": timestamp
                })
                continue

            # Check if word was already used
            if word in used_words:
                await websocket.send_json({
                    "type": "system",
                    "message": f"'{word}'은(는) 이미 사용된 단어입니다!",
                    "timestamp": timestamp
                })
                continue

            # Check if word starts with correct character
            if last_word:
                expected_char = get_last_char(last_word)
                if word[0] != expected_char:
                    await websocket.send_json({
                        "type": "system",
                        "message": f"'{expected_char}'(으)로 시작하는 단어를 입력하세요!",
                        "timestamp": timestamp
                    })
                    continue

            # Valid word from user
            user_msg = {
                "type": "message",
                "username": username,
                "message": word,
                "timestamp": timestamp
            }
            await websocket.send_json(user_msg)
            wc_messages.append(user_msg)
            used_words.append(word)
            score += 1

            # Send score update
            await websocket.send_json({"type": "score", "score": score})

            # Save state
            game_state = {"used_words": used_words, "score": score, "is_game_over": False}
            await save_wordchain_game(username, game_state)
            await save_wordchain_messages(username, wc_messages)

            # Get AI response
            try:
                last_char = get_last_char(word)

                prompt = f"""끝말잇기 게임입니다.
사용된 단어들: {', '.join(used_words)}
'{last_char}'(으)로 시작하는 한국어 단어를 하나만 말하세요.
위에 나온 단어는 사용할 수 없습니다.
단어만 출력하세요. 설명 없이 단어 하나만."""

                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": WORDCHAIN_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=50,
                    temperature=0.7
                )

                ai_word = response.choices[0].message.content.strip()

                # Clean up AI response
                ai_word = ai_word.replace(".", "").replace(",", "").replace("!", "").replace("?", "").strip()

                ai_timestamp = datetime.now().isoformat()

                # Check if AI gave up
                if "패배" in ai_word or not is_valid_korean_word(ai_word):
                    game_over_msg = {
                        "type": "game_over",
                        "message": f"🎉 축하합니다! AI가 단어를 찾지 못했습니다. 최종 점수: {score}점",
                        "timestamp": ai_timestamp
                    }
                    await websocket.send_json(game_over_msg)
                    wc_messages.append(game_over_msg)
                    is_game_over = True
                    game_state = {"used_words": used_words, "score": score, "is_game_over": True}
                    await save_wordchain_game(username, game_state)
                    await save_wordchain_messages(username, wc_messages)
                    continue

                # Validate AI's word
                if ai_word[0] != last_char:
                    game_over_msg = {
                        "type": "game_over",
                        "message": f"🎉 축하합니다! AI가 규칙을 어겼습니다. 최종 점수: {score}점",
                        "timestamp": ai_timestamp
                    }
                    await websocket.send_json(game_over_msg)
                    wc_messages.append(game_over_msg)
                    is_game_over = True
                    game_state = {"used_words": used_words, "score": score, "is_game_over": True}
                    await save_wordchain_game(username, game_state)
                    await save_wordchain_messages(username, wc_messages)
                    continue

                if ai_word in used_words:
                    game_over_msg = {
                        "type": "game_over",
                        "message": f"🎉 축하합니다! AI가 이미 사용된 단어를 말했습니다. 최종 점수: {score}점",
                        "timestamp": ai_timestamp
                    }
                    await websocket.send_json(game_over_msg)
                    wc_messages.append(game_over_msg)
                    is_game_over = True
                    game_state = {"used_words": used_words, "score": score, "is_game_over": True}
                    await save_wordchain_game(username, game_state)
                    await save_wordchain_messages(username, wc_messages)
                    continue

                # AI's valid response
                ai_msg = {
                    "type": "message",
                    "username": "AI",
                    "message": ai_word,
                    "timestamp": ai_timestamp
                }
                await websocket.send_json(ai_msg)
                wc_messages.append(ai_msg)
                used_words.append(ai_word)
                last_word = ai_word

                # Save state
                game_state = {"used_words": used_words, "score": score, "is_game_over": False}
                await save_wordchain_game(username, game_state)
                await save_wordchain_messages(username, wc_messages)

            except Exception as e:
                await websocket.send_json({
                    "type": "system",
                    "message": f"AI 응답 오류: {str(e)}",
                    "timestamp": datetime.now().isoformat()
                })

    except WebSocketDisconnect:
        print(f"[{username}] 끝말잇기 연결 종료")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
