import json
from datetime import datetime
from ..core.database import storage_client, openai_client
from ..core.utils import get_last_char


MAX_IDIOM_HISTORY = 20


def _as_list(value):
    if isinstance(value, str):
        return json.loads(value)
    return value or []


async def get_idiom_game(username: str) -> dict:
    """Get idiom game state from PostgreSQL"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT used_words, score, is_game_over, difficulty, current_idiom
            FROM idiom_state
            WHERE username = $1
            """,
            username,
        )

    if not row:
        return {"used_words": [], "score": 0, "is_game_over": False, "difficulty": 3, "current_idiom": None}

    return {
        "used_words": _as_list(row["used_words"]),
        "score": row["score"],
        "is_game_over": row["is_game_over"],
        "difficulty": row["difficulty"],
        "current_idiom": row.get("current_idiom"),
    }


async def save_idiom_game(username: str, game_state: dict):
    """Save idiom game state to PostgreSQL"""
    pool = await storage_client.get_pool()

    used_words = game_state.get("used_words", [])
    score = int(game_state.get("score", 0))
    is_game_over = bool(game_state.get("is_game_over", False))
    difficulty = int(game_state.get("difficulty", 3))
    current_idiom = game_state.get("current_idiom")

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO idiom_state (
                username,
                used_words,
                score,
                is_game_over,
                difficulty,
                current_idiom
            ) VALUES (
                $1,
                $2::jsonb,
                $3,
                $4,
                $5,
                $6
            )
            ON CONFLICT (username)
            DO UPDATE SET
                used_words = EXCLUDED.used_words,
                score = EXCLUDED.score,
                is_game_over = EXCLUDED.is_game_over,
                difficulty = EXCLUDED.difficulty,
                current_idiom = EXCLUDED.current_idiom,
                updated_at = NOW()
            """,
            username,
            json.dumps(used_words),
            score,
            is_game_over,
            difficulty,
            current_idiom,
        )


async def get_idiom_messages(username: str) -> list[dict]:
    """Get idiom messages for current game from PostgreSQL"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT messages
            FROM idiom_state
            WHERE username = $1
            """,
            username,
        )

    if not row:
        return []

    return _as_list(row["messages"])


async def save_idiom_messages(username: str, messages: list[dict]):
    """Save idiom messages to PostgreSQL"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO idiom_state (username, messages)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (username)
            DO UPDATE SET
                messages = EXCLUDED.messages,
                updated_at = NOW()
            """,
            username,
            json.dumps(messages),
        )


async def get_idiom_history(username: str) -> list[dict]:
    """Get all past game history for sidebar"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT score, difficulty, words_count, words, result, played_at
            FROM idiom_history
            WHERE username = $1
            ORDER BY played_at DESC, id DESC
            LIMIT $2
            """,
            username,
            MAX_IDIOM_HISTORY,
        )

    history = []
    for row in rows:
        history.append({
            "score": row["score"],
            "difficulty": row["difficulty"],
            "words_count": row["words_count"],
            "words": _as_list(row["words"]),
            "result": row["result"],
            "timestamp": row["played_at"].isoformat(),
        })

    return history


async def save_game_to_history(username: str, game_result: dict):
    """Save completed game to history"""
    pool = await storage_client.get_pool()

    score = int(game_result.get("score", 0))
    difficulty = int(game_result.get("difficulty", 3))
    words = game_result.get("words", [])
    words_count = int(game_result.get("words_count", len(words)))
    result = str(game_result.get("result", "lose"))
    timestamp = game_result.get("timestamp")
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)

    async with pool.acquire() as conn:
        async with conn.transaction():
            if timestamp:
                await conn.execute(
                    """
                    INSERT INTO idiom_history (
                        username,
                        score,
                        difficulty,
                        words_count,
                        words,
                        result,
                        played_at
                    ) VALUES (
                        $1,
                        $2,
                        $3,
                        $4,
                        $5::jsonb,
                        $6,
                        $7::timestamptz
                    )
                    """,
                    username,
                    score,
                    difficulty,
                    words_count,
                    json.dumps(words),
                    result,
                    timestamp,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO idiom_history (
                        username,
                        score,
                        difficulty,
                        words_count,
                        words,
                        result
                    ) VALUES (
                        $1,
                        $2,
                        $3,
                        $4,
                        $5::jsonb,
                        $6
                    )
                    """,
                    username,
                    score,
                    difficulty,
                    words_count,
                    json.dumps(words),
                    result,
                )

            await conn.execute(
                """
                DELETE FROM idiom_history
                WHERE username = $1
                  AND id IN (
                      SELECT id
                      FROM (
                          SELECT id,
                                 ROW_NUMBER() OVER (
                                     PARTITION BY username
                                     ORDER BY played_at DESC, id DESC
                                 ) AS rn
                          FROM idiom_history
                          WHERE username = $1
                      ) ranked
                      WHERE rn > $2
                  )
                """,
                username,
                MAX_IDIOM_HISTORY,
            )


async def clear_idiom(username: str):
    """Clear current idiom game for a user"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM idiom_state WHERE username = $1",
            username,
        )


async def delete_idiom_history_item(username: str, index: int) -> bool:
    """Delete a specific game from history by index"""
    if index < 0:
        return False

    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id
            FROM idiom_history
            WHERE username = $1
            ORDER BY played_at DESC, id DESC
            OFFSET $2
            LIMIT 1
            """,
            username,
            index,
        )

        if not row:
            return False

        await conn.execute(
            "DELETE FROM idiom_history WHERE id = $1",
            row["id"],
        )

    return True


async def verify_word_exists(word: str) -> tuple[bool, str]:
    """Verify if an idiom is a valid Korean four-character idiom using OpenAI"""
    prompt = f"""'{word}'이(가) 한국어 사자성어(4글자)로 실제로 널리 쓰이는 표현인지 확인해주세요.

판정 기준:
- 실제로 알려진 사자성어면 YES
- 사자성어가 아니거나 임의 조합이면 NO
- 정확히 4글자 한글 표현만 허용

답변 형식: YES 또는 NO"""

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "당신은 사자성어 판정 심판입니다. 실제로 통용되는 사자성어만 YES로 답하세요.",
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=30,
        temperature=0,
    )

    result = response.choices[0].message.content.strip().upper()
    if "YES" in result:
        return True, ""

    original = response.choices[0].message.content.strip()
    reason = original.replace("NO:", "").replace("NO", "").replace("답변:", "").strip()
    return False, reason if reason else "사자성어 이어말하기에 사용할 수 없는 표현입니다"


async def get_ai_word(used_words: list[str], last_char: str | None, difficulty: int) -> str:
    """Get AI idiom response"""
    try:
        difficulty_guide = {
            1: "아주 쉬운, 잘 알려진 사자성어만 사용",
            2: "쉬운 사자성어 중심으로 사용",
            3: "보편적인 사자성어를 균형 있게 사용",
            4: "상대적으로 어려운 사자성어를 섞어 사용",
            5: "전문가처럼 어려운 사자성어도 적극 사용",
        }

        prompt = f"""사자성어 이어말하기 게임입니다.
사용된 사자성어: {', '.join(used_words) if used_words else '(없음)'}
{f"'{last_char}'(으)로 시작하는 " if last_char else ''}한국어 사자성어(정확히 4글자)를 하나만 말하세요.

조건:
- 정확히 4글자 한글 사자성어
- 이미 사용한 표현은 금지
- 모르면 정확히 '패배'라고 답변
- 출력은 사자성어 한 개만"""

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"너는 사자성어 이어말하기 AI 플레이어다. 난이도 가이드: {difficulty_guide.get(difficulty, difficulty_guide[3])}",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=30,
            temperature=0.4 + (difficulty * 0.1),
        )

        ai_word = response.choices[0].message.content.strip()
        ai_word = ai_word.replace(".", "").replace(",", "").replace("!", "").replace("?", "").strip()
        return ai_word
    except Exception as e:
        print(f"AI idiom generation failed: {e}")
        # Fallback idioms (4-letter Korean idioms)
        fallbacks = ["사필귀정", "개과천선", "호기심", "용감한", "지혜로운"]
        for fb in fallbacks:
            if fb not in used_words and _is_valid_idiom_format(fb):
                return fb
        return "사필귀정"  # Last resort


def _is_valid_idiom_format(word: str) -> bool:
    return len(word) == 4 and all("가" <= ch <= "힣" for ch in word)


def is_valid_full_idiom(word: str) -> bool:
    return _is_valid_idiom_format(word)


async def validate_user_word_async(word: str, used_words: list[str], last_word: str | None) -> tuple[bool, str]:
    """Validate user's idiom with dictionary check. Returns (is_valid, error_message)"""
    if not _is_valid_idiom_format(word):
        return False, "사자성어는 한글 4글자로 입력하세요"

    if word in used_words:
        return False, f"'{word}'은(는) 이미 사용된 사자성어입니다!"

    if last_word:
        expected_char = get_last_char(last_word)
        if word[0] != expected_char:
            return False, f"'{expected_char}'(으)로 시작하는 사자성어를 입력하세요!"

    is_real_word, reason = await verify_word_exists(word)
    if not is_real_word:
        return False, f"'{word}'은(는) {reason}"

    return True, ""


def validate_ai_word(ai_word: str, used_words: list[str], last_char: str) -> tuple[bool, str]:
    """Validate AI's idiom. Returns (is_valid, win_message)"""
    if "패배" in ai_word or not _is_valid_idiom_format(ai_word):
        return False, "축하합니다! AI가 사자성어를 찾지 못했습니다!"

    if ai_word[0] != last_char:
        return False, "축하합니다! AI가 규칙을 어겼습니다!"

    if ai_word in used_words:
        return False, "축하합니다! AI가 중복 사자성어를 말했습니다!"

    return True, ""



def is_valid_idiom_suffix(answer: str) -> bool:
    return len(answer) == 2 and all("가" <= ch <= "힣" for ch in answer)


def get_idiom_prefix(idiom: str) -> str:
    return idiom[:2] if idiom else ""


def get_idiom_suffix(idiom: str) -> str:
    return idiom[2:] if idiom else ""


async def get_idiom_meaning(idiom: str) -> str:
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 사자성어 해설가다. 해석을 한국어 한 문장으로 간결하게 설명한다."},
            {"role": "user", "content": f"{idiom}의 뜻을 한국어로 짧게 설명해줘."},
        ],
        max_tokens=80,
        temperature=0.2,
    )
    meaning = response.choices[0].message.content.strip()
    return meaning or "해석 정보를 가져오지 못했습니다."
