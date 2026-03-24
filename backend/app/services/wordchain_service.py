import json
from datetime import datetime
from ..core.database import storage_client, openai_client
from ..core.config import get_difficulty_prompt
from ..core.utils import get_last_char, is_valid_korean_word, is_valid_korean_format


MAX_WORDCHAIN_HISTORY = 20


def _as_list(value):
    if isinstance(value, str):
        return json.loads(value)
    return value or []


async def get_wordchain_game(username: str) -> dict:
    """Get wordchain game state from PostgreSQL"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT used_words, score, is_game_over, difficulty
            FROM wordchain_state
            WHERE username = $1
            """,
            username,
        )

    if not row:
        return {"used_words": [], "score": 0, "is_game_over": False, "difficulty": 3}

    return {
        "used_words": _as_list(row["used_words"]),
        "score": row["score"],
        "is_game_over": row["is_game_over"],
        "difficulty": row["difficulty"],
    }


async def save_wordchain_game(username: str, game_state: dict):
    """Save wordchain game state to PostgreSQL"""
    pool = await storage_client.get_pool()

    used_words = game_state.get("used_words", [])
    score = int(game_state.get("score", 0))
    is_game_over = bool(game_state.get("is_game_over", False))
    difficulty = int(game_state.get("difficulty", 3))

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO wordchain_state (
                username,
                used_words,
                score,
                is_game_over,
                difficulty
            ) VALUES (
                $1,
                $2::jsonb,
                $3,
                $4,
                $5
            )
            ON CONFLICT (username)
            DO UPDATE SET
                used_words = EXCLUDED.used_words,
                score = EXCLUDED.score,
                is_game_over = EXCLUDED.is_game_over,
                difficulty = EXCLUDED.difficulty,
                updated_at = NOW()
            """,
            username,
            json.dumps(used_words),
            score,
            is_game_over,
            difficulty,
        )


async def get_wordchain_messages(username: str) -> list[dict]:
    """Get wordchain messages for current game from PostgreSQL"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT messages
            FROM wordchain_state
            WHERE username = $1
            """,
            username,
        )

    if not row:
        return []

    return _as_list(row["messages"])


async def save_wordchain_messages(username: str, messages: list[dict]):
    """Save wordchain messages to PostgreSQL"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO wordchain_state (username, messages)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (username)
            DO UPDATE SET
                messages = EXCLUDED.messages,
                updated_at = NOW()
            """,
            username,
            json.dumps(messages),
        )


async def get_wordchain_history(username: str) -> list[dict]:
    """Get all past game history for sidebar"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT score, difficulty, words_count, words, result, played_at
            FROM wordchain_history
            WHERE username = $1
            ORDER BY played_at DESC, id DESC
            LIMIT $2
            """,
            username,
            MAX_WORDCHAIN_HISTORY,
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
                    INSERT INTO wordchain_history (
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
                    INSERT INTO wordchain_history (
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
                DELETE FROM wordchain_history
                WHERE username = $1
                  AND id IN (
                      SELECT id
                      FROM (
                          SELECT id,
                                 ROW_NUMBER() OVER (
                                     PARTITION BY username
                                     ORDER BY played_at DESC, id DESC
                                 ) AS rn
                          FROM wordchain_history
                          WHERE username = $1
                      ) ranked
                      WHERE rn > $2
                  )
                """,
                username,
                MAX_WORDCHAIN_HISTORY,
            )


async def clear_wordchain(username: str):
    """Clear current wordchain game for a user"""
    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM wordchain_state WHERE username = $1",
            username,
        )


async def delete_wordchain_history_item(username: str, index: int) -> bool:
    """Delete a specific game from history by index"""
    if index < 0:
        return False

    pool = await storage_client.get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id
            FROM wordchain_history
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
            "DELETE FROM wordchain_history WHERE id = $1",
            row["id"],
        )

    return True


async def verify_word_exists(word: str) -> tuple[bool, str]:
    """Verify if a word is a real Korean word using OpenAI"""
    prompt = f"""'{word}'가 끝말잇기에서 사용할 수 있는 단어인지 확인해주세요.

허용되는 단어 (거의 다 허용!):
- 일반 명사, 음식 이름, 동물, 식물
- 브랜드명 (람보르기니, 맥도날드, 삼성, 나이키 등 OK!)
- 지명, 나라 이름 (서울, 미국, 파리 등)
- 외래어, 외국어 단어
- 유명인 이름도 OK (아이유, 손흥민 등)
- 한국에서 알려진 단어면 대부분 OK

허용 안 되는 단어:
- 완전히 지어낸 말 (의미 없는 글자 조합)
- 1글자 단어

답변: YES 또는 NO"""

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "당신은 관대한 끝말잇기 심판입니다. 실제로 존재하거나 사람들이 아는 단어면 거의 다 허용합니다. 매우 관대하게 판단하세요."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=50,
        temperature=0
    )

    result = response.choices[0].message.content.strip().upper()

    # "YES"가 응답에 포함되어 있으면 유효한 단어
    if "YES" in result:
        return True, ""
    else:
        # NO인 경우 이유 추출
        original = response.choices[0].message.content.strip()
        reason = original.replace("NO:", "").replace("NO", "").replace("답변:", "").strip()
        return False, reason if reason else "끝말잇기에 사용할 수 없는 단어입니다"


async def get_ai_word(used_words: list[str], last_char: str, difficulty: int) -> str:
    """Get AI's word response"""
    try:
        prompt = f"""끝말잇기 게임입니다.
사용된 단어들: {', '.join(used_words)}
'{last_char}'(으)로 시작하는 한국어 단어를 하나만 말하세요.

조건:
- 표준국어대사전에 등재된 명사만 가능
- 고유명사(사람 이름, 지명, 브랜드명) 불가
- 위에 나온 단어는 사용 불가
- 단어만 출력하세요"""

        system_prompt = get_difficulty_prompt(difficulty)

        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.7 + (difficulty * 0.1)
        )

        ai_word = response.choices[0].message.content.strip()
        # Clean up
        ai_word = ai_word.replace(".", "").replace(",", "").replace("!", "").replace("?", "").strip()
        return ai_word
    except Exception as e:
        print(f"AI word generation failed: {e}")
        # Fallback words starting with last_char
        fallbacks = ["사과", "바나나", "학교", "가방", "나무", "구름", "토끼", "꽃", "하늘", "바다"]
        for fb in fallbacks:
            if fb.startswith(last_char) and fb not in used_words:
                return fb
        return "사과"  # Last resort


async def validate_user_word_async(word: str, used_words: list[str], last_word: str | None) -> tuple[bool, str]:
    """Validate user's word with dictionary check. Returns (is_valid, error_message)"""
    # 기본 형식 검사
    if not is_valid_korean_format(word):
        return False, "올바른 한글 단어를 입력하세요 (2글자 이상)"

    # 중복 검사
    if word in used_words:
        return False, f"'{word}'은(는) 이미 사용된 단어입니다!"

    # 끝말잇기 규칙 검사 (두음법칙 적용)
    if last_word:
        expected_char = get_last_char(last_word)
        # 두음법칙: 원래 글자와 변환된 글자 모두 허용
        if word[0] != expected_char and word[0] != last_word[-1]:
            return False, f"'{expected_char}'(으)로 시작하는 단어를 입력하세요!"

    # 사전 검증 (실제 단어인지 확인)
    is_real_word, reason = await verify_word_exists(word)
    if not is_real_word:
        return False, f"'{word}'은(는) {reason}"

    return True, ""


# 동기 버전 (하위 호환성)
def validate_user_word(word: str, used_words: list[str], last_word: str | None) -> tuple[bool, str]:
    """Validate user's word (basic check only). Returns (is_valid, error_message)"""
    if not is_valid_korean_format(word):
        return False, "올바른 한글 단어를 입력하세요 (2글자 이상)"

    if word in used_words:
        return False, f"'{word}'은(는) 이미 사용된 단어입니다!"

    if last_word:
        expected_char = get_last_char(last_word)
        if word[0] != expected_char and word[0] != last_word[-1]:
            return False, f"'{expected_char}'(으)로 시작하는 단어를 입력하세요!"

    return True, ""


def validate_ai_word(ai_word: str, used_words: list[str], last_char: str) -> tuple[bool, str]:
    """Validate AI's word. Returns (is_valid, win_message)"""
    if "패배" in ai_word or not is_valid_korean_format(ai_word):
        return False, "🎉 축하합니다! AI가 단어를 찾지 못했습니다!"

    if ai_word[0] != last_char and ai_word[0] != last_char:
        return False, "🎉 축하합니다! AI가 규칙을 어겼습니다!"

    if ai_word in used_words:
        return False, "🎉 축하합니다! AI가 중복 단어를 말했습니다!"

    return True, ""
