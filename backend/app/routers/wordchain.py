from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime
from ..services.wordchain_service import (
    get_wordchain_game,
    save_wordchain_game,
    get_wordchain_messages,
    save_wordchain_messages,
    clear_wordchain,
    get_wordchain_history,
    save_game_to_history,
    delete_wordchain_history_item,
    get_ai_word,
    validate_user_word_async,
    validate_ai_word
)
from ..core.utils import get_last_char

router = APIRouter()

DIFFICULTY_NAMES = {1: "아주 쉬움", 2: "쉬움", 3: "보통", 4: "어려움", 5: "전문가"}


@router.post("/api/wordchain/restart/{username}")
async def restart_wordchain(username: str, difficulty: int = 3):
    await clear_wordchain(username)
    return {"success": True, "message": "게임이 재시작되었습니다."}


@router.get("/api/wordchain/history/{username}")
async def get_game_history(username: str):
    """Get past game history for sidebar"""
    history = await get_wordchain_history(username)
    return {"history": history}


@router.delete("/api/wordchain/history/{username}/{index}")
async def delete_game_history(username: str, index: int):
    """Delete a specific game from history"""
    success = await delete_wordchain_history_item(username, index)
    if success:
        return {"success": True}
    return {"success": False, "message": "기록을 찾을 수 없습니다."}


@router.websocket("/ws/wordchain/{username}/{difficulty}")
async def wordchain_endpoint(websocket: WebSocket, username: str, difficulty: int = 3):
    await websocket.accept()

    # Validate difficulty
    if difficulty < 1 or difficulty > 5:
        difficulty = 3

    game_state = await get_wordchain_game(username)
    wc_messages = await get_wordchain_messages(username)

    used_words = game_state.get("used_words", [])
    score = game_state.get("score", 0)
    is_game_over = game_state.get("is_game_over", False)

    # Update difficulty
    game_state["difficulty"] = difficulty
    await save_wordchain_game(username, game_state)

    if not wc_messages:
        welcome_msg = {
            "type": "system",
            "message": f"난이도: {DIFFICULTY_NAMES[difficulty]} | 아무 단어나 입력해서 시작하세요!",
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_json(welcome_msg)
    else:
        await websocket.send_json({
            "type": "history",
            "messages": wc_messages,
            "score": score,
            "isGameOver": is_game_over,
            "difficulty": difficulty
        })

    last_word = used_words[-1] if used_words else None

    try:
        while True:
            data = await websocket.receive_text()
            word = data.strip()
            timestamp = datetime.now().isoformat()

            if is_game_over:
                await websocket.send_json({
                    "type": "system",
                    "message": "게임이 끝났습니다. 다시 시작하려면 버튼을 누르세요.",
                    "timestamp": timestamp
                })
                continue

            # Validate user's word (with dictionary check)
            is_valid, error_msg = await validate_user_word_async(word, used_words, last_word)
            if not is_valid:
                # 사용자가 잘못된 단어를 입력하면 패배
                game_over_msg = {
                    "type": "game_over",
                    "message": f"💔 패배! {error_msg} 최종 점수: {score}점",
                    "timestamp": timestamp
                }
                await websocket.send_json(game_over_msg)
                wc_messages.append(game_over_msg)
                is_game_over = True
                game_state = {"used_words": used_words, "score": score, "is_game_over": True, "difficulty": difficulty}
                await save_wordchain_game(username, game_state)
                await save_wordchain_messages(username, wc_messages)

                # Save to history as loss
                await save_game_to_history(username, {
                    "score": score,
                    "difficulty": difficulty,
                    "words_count": len(used_words),
                    "words": used_words,
                    "result": "lose",
                    "timestamp": timestamp
                })
                continue

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

            await websocket.send_json({"type": "score", "score": score})

            game_state = {"used_words": used_words, "score": score, "is_game_over": False, "difficulty": difficulty}
            await save_wordchain_game(username, game_state)
            await save_wordchain_messages(username, wc_messages)

            try:
                last_char = get_last_char(word)
                ai_word = await get_ai_word(used_words, last_char, difficulty)

                ai_timestamp = datetime.now().isoformat()

                # Validate AI's word
                ai_valid, win_message = validate_ai_word(ai_word, used_words, last_char)

                if not ai_valid:
                    game_over_msg = {
                        "type": "game_over",
                        "message": f"{win_message} 최종 점수: {score}점",
                        "timestamp": ai_timestamp
                    }
                    await websocket.send_json(game_over_msg)
                    wc_messages.append(game_over_msg)
                    is_game_over = True
                    game_state = {"used_words": used_words, "score": score, "is_game_over": True, "difficulty": difficulty}
                    await save_wordchain_game(username, game_state)
                    await save_wordchain_messages(username, wc_messages)

                    # Save to history
                    await save_game_to_history(username, {
                        "score": score,
                        "difficulty": difficulty,
                        "words_count": len(used_words),
                        "words": used_words,
                        "result": "win",
                        "timestamp": ai_timestamp
                    })
                    continue

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

                game_state = {"used_words": used_words, "score": score, "is_game_over": False, "difficulty": difficulty}
                await save_wordchain_game(username, game_state)
                await save_wordchain_messages(username, wc_messages)

            except Exception as e:
                # AI 오류시 사용자 승리로 처리
                error_timestamp = datetime.now().isoformat()
                game_over_msg = {
                    "type": "game_over",
                    "message": f"🎉 AI 오류로 승리! 최종 점수: {score}점",
                    "timestamp": error_timestamp
                }
                await websocket.send_json(game_over_msg)
                is_game_over = True
                await save_game_to_history(username, {
                    "score": score,
                    "difficulty": difficulty,
                    "words_count": len(used_words),
                    "words": used_words,
                    "result": "win",
                    "timestamp": error_timestamp
                })
                continue

    except WebSocketDisconnect:
        print(f"[{username}] 끝말잇기 연결 종료")
