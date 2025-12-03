import json
from ..core.database import redis_client, openai_client
from ..core.config import get_difficulty_prompt
from ..core.utils import get_last_char, is_valid_korean_word


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


async def get_ai_word(used_words: list[str], last_char: str, difficulty: int) -> str:
    """Get AI's word response"""
    prompt = f"""끝말잇기 게임입니다.
사용된 단어들: {', '.join(used_words)}
'{last_char}'(으)로 시작하는 한국어 단어를 하나만 말하세요.
위에 나온 단어는 사용할 수 없습니다.
단어만 출력하세요."""

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


def validate_user_word(word: str, used_words: list[str], last_word: str | None) -> tuple[bool, str]:
    """Validate user's word. Returns (is_valid, error_message)"""
    if not is_valid_korean_word(word):
        return False, "올바른 한글 단어를 입력하세요 (2글자 이상)"

    if word in used_words:
        return False, f"'{word}'은(는) 이미 사용된 단어입니다!"

    if last_word:
        expected_char = get_last_char(last_word)
        if word[0] != expected_char:
            return False, f"'{expected_char}'(으)로 시작하는 단어를 입력하세요!"

    return True, ""


def validate_ai_word(ai_word: str, used_words: list[str], last_char: str) -> tuple[bool, str]:
    """Validate AI's word. Returns (is_valid, win_message)"""
    if "패배" in ai_word or not is_valid_korean_word(ai_word):
        return False, "🎉 축하합니다! AI가 단어를 찾지 못했습니다!"

    if ai_word[0] != last_char:
        return False, "🎉 축하합니다! AI가 규칙을 어겼습니다!"

    if ai_word in used_words:
        return False, "🎉 축하합니다! AI가 중복 단어를 말했습니다!"

    return True, ""
