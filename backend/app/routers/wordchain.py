from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from datetime import datetime
from pydantic import BaseModel
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

class WordRequest(BaseModel):
    answer: str

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


@router.post("/api/wordchain/send/{username}/{difficulty}")
async def send_wordchain_message(username: str, difficulty: int, request: WordRequest):
    if difficulty < 1 or difficulty > 5:
        difficulty = 3

    game_state = await get_wordchain_game(username)
    wc_messages = await get_wordchain_messages(username)

    used_words = game_state.get("used_words", [])
    score = game_state.get("score", 0)
    is_game_over = game_state.get("is_game_over", False)

    game_state["difficulty"] = difficulty
    await save_wordchain_game(username, game_state)

    word = request.answer.strip()
    timestamp = datetime.now().isoformat()

    messages_to_send = []

    if is_game_over:
        messages_to_send.append({
            "type": "system",
            "message": "게임이 끝났습니다. 다시 시작하려면 버튼을 누르세요.",
            "timestamp": timestamp
        })
    else:
        last_word = used_words[-1] if used_words else None

        # Validate user's word (with dictionary check)
        is_valid, error_msg = await validate_user_word_async(word, used_words, last_word)
        if not is_valid:
            # 사용자가 잘못된 단어를 입력하면 패배
            game_over_msg = {
                "type": "game_over",
                "message": f"💔 패배! {error_msg} 최종 점수: {score}점",
                "timestamp": timestamp
            }
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
            messages_to_send.append(game_over_msg)
        else:
            user_msg = {
                "type": "message",
                "username": username,
                "message": word,
                "timestamp": timestamp
            }
            wc_messages.append(user_msg)
            used_words.append(word)
            score += 1

            messages_to_send.extend([user_msg, {"type": "score", "score": score}])

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
                    messages_to_send.append(game_over_msg)
                else:
                    ai_msg = {
                        "type": "message",
                        "username": "AI",
                        "message": ai_word,
                        "timestamp": ai_timestamp
                    }
                    wc_messages.append(ai_msg)
                    used_words.append(ai_word)

                    messages_to_send.append(ai_msg)

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
                wc_messages.append(game_over_msg)
                is_game_over = True
                game_state = {"used_words": used_words, "score": score, "is_game_over": True, "difficulty": difficulty}
                await save_wordchain_game(username, game_state)
                await save_wordchain_messages(username, wc_messages)
                await save_game_to_history(username, {
                    "score": score,
                    "difficulty": difficulty,
                    "words_count": len(used_words),
                    "words": used_words,
                    "result": "win",
                    "timestamp": error_timestamp
                })
                messages_to_send.append(game_over_msg)

    return {"messages": messages_to_send}


@router.get("/api/wordchain/init/{username}/{difficulty}")
async def init_wordchain_game(username: str, difficulty: int):
    if difficulty < 1 or difficulty > 5:
        difficulty = 3

    game_state = await get_wordchain_game(username)
    wc_messages = await get_wordchain_messages(username)

    used_words = game_state.get("used_words", [])
    score = game_state.get("score", 0)
    is_game_over = game_state.get("is_game_over", False)

    game_state["difficulty"] = difficulty
    await save_wordchain_game(username, game_state)

    messages_to_send = []

    if not wc_messages:
        welcome_msg = {
            "type": "system",
            "message": f"난이도: {DIFFICULTY_NAMES[difficulty]} | 아무 단어나 입력해서 시작하세요!",
            "timestamp": datetime.now().isoformat()
        }
        wc_messages.append(welcome_msg)
        messages_to_send.append(welcome_msg)
        await save_wordchain_messages(username, wc_messages)
    else:
        messages_to_send = wc_messages

    return {
        "messages": messages_to_send,
        "score": score,
        "isGameOver": is_game_over,
        "difficulty": difficulty
    }
