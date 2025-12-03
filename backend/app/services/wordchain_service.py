import json
from ..core.database import redis_client, openai_client
from ..core.config import get_difficulty_prompt
from ..core.utils import get_last_char, is_valid_korean_word, is_valid_korean_format


def get_wordchain_key(username: str) -> str:
    return f"wordchain:game:{username}"


def get_wordchain_messages_key(username: str) -> str:
    return f"wordchain:messages:{username}"


def get_wordchain_history_key(username: str) -> str:
    return f"wordchain:history:{username}"


async def get_wordchain_game(username: str) -> dict:
    """Get wordchain game state from Redis"""
    key = get_wordchain_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return {"used_words": [], "score": 0, "is_game_over": False, "difficulty": 3}


async def save_wordchain_game(username: str, game_state: dict):
    """Save wordchain game state to Redis"""
    key = get_wordchain_key(username)
    await redis_client.set(key, json.dumps(game_state))


async def get_wordchain_messages(username: str) -> list[dict]:
    """Get wordchain messages for current game from Redis"""
    key = get_wordchain_messages_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return []


async def save_wordchain_messages(username: str, messages: list[dict]):
    """Save wordchain messages to Redis"""
    key = get_wordchain_messages_key(username)
    await redis_client.set(key, json.dumps(messages))


async def get_wordchain_history(username: str) -> list[dict]:
    """Get all past game history for sidebar"""
    key = get_wordchain_history_key(username)
    data = await redis_client.get(key)
    if data:
        return json.loads(data)
    return []


async def save_game_to_history(username: str, game_result: dict):
    """Save completed game to history"""
    key = get_wordchain_history_key(username)
    history = await get_wordchain_history(username)
    history.insert(0, game_result)  # 최신 게임을 맨 앞에
    # 최대 20개만 저장
    if len(history) > 20:
        history = history[:20]
    await redis_client.set(key, json.dumps(history))


async def clear_wordchain(username: str):
    """Clear current wordchain game for a user"""
    game_key = get_wordchain_key(username)
    msg_key = get_wordchain_messages_key(username)
    await redis_client.delete(game_key, msg_key)


async def delete_wordchain_history_item(username: str, index: int) -> bool:
    """Delete a specific game from history by index"""
    key = get_wordchain_history_key(username)
    history = await get_wordchain_history(username)
    if 0 <= index < len(history):
        history.pop(index)
        await redis_client.set(key, json.dumps(history))
        return True
    return False


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
