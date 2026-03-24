from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.idiom_service import (
    clear_idiom,
    delete_idiom_history_item,
    get_ai_word,
    get_idiom_game,
    get_idiom_history,
    get_idiom_meaning,
    get_idiom_messages,
    get_idiom_prefix,
    get_idiom_suffix,
    is_valid_full_idiom,
    is_valid_idiom_suffix,
    save_game_to_history,
    save_idiom_game,
    save_idiom_messages,
)

router = APIRouter()

DIFFICULTY_NAMES = {1: "아주 쉬움", 2: "쉬움", 3: "보통", 4: "어려움", 5: "전문가"}


@router.post("/api/idiom/restart/{username}")
async def restart_idiom(username: str, difficulty: int = 3):
    await clear_idiom(username)
    return {"success": True, "message": "게임이 재시작되었습니다."}


@router.get("/api/idiom/history/{username}")
async def get_game_history(username: str):
    history = await get_idiom_history(username)
    return {"history": history}


@router.delete("/api/idiom/history/{username}/{index}")
async def delete_game_history(username: str, index: int):
    success = await delete_idiom_history_item(username, index)
    if success:
        return {"success": True}
    return {"success": False, "message": "기록을 찾을 수 없습니다."}


async def _pick_next_idiom(used_words: list[str], difficulty: int) -> str | None:
    for _ in range(6):
        candidate = await get_ai_word(used_words, None, difficulty)
        if not is_valid_full_idiom(candidate):
            continue
        if candidate in used_words:
            continue
        return candidate
    return None


async def _send_new_quiz_round(
    websocket: WebSocket,
    wc_messages: list[dict],
    current_idiom: str,
) -> None:
    quiz_msg = {
        "type": "message",
        "username": "AI",
        "message": f"{get_idiom_prefix(current_idiom)}??",
        "timestamp": datetime.now().isoformat(),
    }
    wc_messages.append(quiz_msg)
    await websocket.send_json(quiz_msg)


@router.websocket("/ws/idiom/{username}/{difficulty}")
async def idiom_endpoint(websocket: WebSocket, username: str, difficulty: int = 3):
    await websocket.accept()

    if difficulty < 1 or difficulty > 5:
        difficulty = 3

    game_state = await get_idiom_game(username)
    wc_messages = await get_idiom_messages(username)

    used_words = game_state.get("used_words", [])
    score = int(game_state.get("score", 0))
    is_game_over = bool(game_state.get("is_game_over", False))
    current_idiom = game_state.get("current_idiom")

    game_state["difficulty"] = difficulty
    await save_idiom_game(username, game_state)

    if wc_messages:
        await websocket.send_json(
            {
                "type": "history",
                "messages": wc_messages,
                "score": score,
                "isGameOver": is_game_over,
                "difficulty": difficulty,
            }
        )
    else:
        welcome_msg = {
            "type": "system",
            "message": (
                f"난이도: {DIFFICULTY_NAMES[difficulty]} | "
                "AI가 앞 두 글자를 제시하면, 뒷 두 글자를 맞혀보세요!"
            ),
            "timestamp": datetime.now().isoformat(),
        }
        wc_messages.append(welcome_msg)
        await websocket.send_json(welcome_msg)

    if (not is_game_over) and (not current_idiom):
        next_idiom = await _pick_next_idiom(used_words, difficulty)
        if next_idiom is None:
            fail_msg = {
                "type": "game_over",
                "message": f"🎉 승리! AI가 문제를 준비하지 못했어요. 최종 점수: {score}점",
                "timestamp": datetime.now().isoformat(),
            }
            wc_messages.append(fail_msg)
            is_game_over = True
            await save_idiom_game(
                username,
                {
                    "used_words": used_words,
                    "score": score,
                    "is_game_over": True,
                    "difficulty": difficulty,
                    "current_idiom": None,
                },
            )
            await save_idiom_messages(username, wc_messages)
            await save_game_to_history(
                username,
                {
                    "score": score,
                    "difficulty": difficulty,
                    "words_count": len(used_words),
                    "words": used_words,
                    "result": "win",
                    "timestamp": datetime.now().isoformat(),
                },
            )
            await websocket.send_json(fail_msg)
        else:
            current_idiom = next_idiom
            await _send_new_quiz_round(websocket, wc_messages, current_idiom)
            await save_idiom_game(
                username,
                {
                    "used_words": used_words,
                    "score": score,
                    "is_game_over": is_game_over,
                    "difficulty": difficulty,
                    "current_idiom": current_idiom,
                },
            )
            await save_idiom_messages(username, wc_messages)

    try:
        while True:
            data = await websocket.receive_text()
            answer = data.strip()
            timestamp = datetime.now().isoformat()

            if is_game_over:
                await websocket.send_json(
                    {
                        "type": "system",
                        "message": "게임이 끝났습니다. 다시 시작하려면 버튼을 누르세요.",
                        "timestamp": timestamp,
                    }
                )
                continue

            if not current_idiom:
                await websocket.send_json(
                    {
                        "type": "system",
                        "message": "문제를 준비 중입니다. 잠시 후 다시 시도해주세요.",
                        "timestamp": timestamp,
                    }
                )
                continue

            expected_suffix = get_idiom_suffix(current_idiom)

            if not is_valid_idiom_suffix(answer) or answer != expected_suffix:
                try:
                    meaning = await get_idiom_meaning(current_idiom)
                except Exception:
                    meaning = "해석 정보를 가져오지 못했습니다."

                wrong_msg = {
                    "type": "message",
                    "username": "AI",
                    "message": "오답 ❌",
                    "timestamp": timestamp,
                }
                answer_msg = {
                    "type": "message",
                    "username": "AI",
                    "message": f"정답: {current_idiom} ({expected_suffix})",
                    "timestamp": timestamp,
                }
                meaning_msg = {
                    "type": "message",
                    "username": "AI",
                    "message": f"({meaning})",
                    "timestamp": timestamp,
                }
                game_over_msg = {
                    "type": "game_over",
                    "message": f"게임 종료! 최종 점수: {score}점",
                    "timestamp": timestamp,
                }

                wc_messages.extend([wrong_msg, answer_msg, meaning_msg, game_over_msg])
                is_game_over = True

                await save_idiom_game(
                    username,
                    {
                        "used_words": used_words,
                        "score": score,
                        "is_game_over": True,
                        "difficulty": difficulty,
                        "current_idiom": current_idiom,
                    },
                )
                await save_idiom_messages(username, wc_messages)
                await save_game_to_history(
                    username,
                    {
                        "score": score,
                        "difficulty": difficulty,
                        "words_count": len(used_words),
                        "words": used_words,
                        "result": "lose",
                        "timestamp": timestamp,
                    },
                )

                await websocket.send_json(wrong_msg)
                await websocket.send_json(answer_msg)
                await websocket.send_json(meaning_msg)
                await websocket.send_json(game_over_msg)
                continue

            user_msg = {
                "type": "message",
                "username": username,
                "message": answer,
                "timestamp": timestamp,
            }
            wc_messages.append(user_msg)
            await websocket.send_json(user_msg)

            # 정답 후 해석 추가
            try:
                meaning = await get_idiom_meaning(current_idiom)
            except Exception:
                meaning = "해석 정보를 가져오지 못했습니다."
            meaning_msg = {
                "type": "message",
                "username": "AI",
                "message": f"({meaning})",
                "timestamp": timestamp,
            }
            wc_messages.append(meaning_msg)
            await websocket.send_json(meaning_msg)

            used_words.append(current_idiom)
            score += 1
            await websocket.send_json({"type": "score", "score": score})

            next_idiom = await _pick_next_idiom(used_words, difficulty)
            if next_idiom is None:
                win_msg = {
                    "type": "game_over",
                    "message": f"🎉 승리! AI가 다음 문제를 만들지 못했어요. 최종 점수: {score}점",
                    "timestamp": datetime.now().isoformat(),
                }
                wc_messages.append(win_msg)
                is_game_over = True

                await save_idiom_game(
                    username,
                    {
                        "used_words": used_words,
                        "score": score,
                        "is_game_over": True,
                        "difficulty": difficulty,
                        "current_idiom": None,
                    },
                )
                await save_idiom_messages(username, wc_messages)
                await save_game_to_history(
                    username,
                    {
                        "score": score,
                        "difficulty": difficulty,
                        "words_count": len(used_words),
                        "words": used_words,
                        "result": "win",
                        "timestamp": win_msg["timestamp"],
                    },
                )
                await websocket.send_json(win_msg)
                continue

            current_idiom = next_idiom
            await _send_new_quiz_round(websocket, wc_messages, current_idiom)

            await save_idiom_game(
                username,
                {
                    "used_words": used_words,
                    "score": score,
                    "is_game_over": False,
                    "difficulty": difficulty,
                    "current_idiom": current_idiom,
                },
            )
            await save_idiom_messages(username, wc_messages)

    except WebSocketDisconnect:
        print(f"[{username}] 사자성어 이어말하기 연결 종료")
