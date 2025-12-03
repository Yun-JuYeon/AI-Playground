import os
from dotenv import load_dotenv

load_dotenv()

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# Prompts
SYSTEM_PROMPT = "You are a helpful assistant. Respond in the same language the user uses. Keep responses concise and friendly."

DIFFICULTY_PROMPTS = {
    1: """You are playing a Korean word chain game (끝말잇기) on VERY EASY mode.
You are playing against a beginner, so you should:
- Use only very simple, common words (2-3 syllables)
- Use words that children would know (초등학교 수준)
- Avoid difficult or uncommon words
- Sometimes pretend you can't find a word and say "패배" (about 30% chance when words get hard)

Examples of easy words: 사과, 바나나, 학교, 가방, 나무, 구름, 토끼""",

    2: """You are playing a Korean word chain game (끝말잇기) on EASY mode.
You should:
- Use simple, common words (2-4 syllables)
- Use words that middle schoolers would know
- Avoid very difficult or technical words
- Sometimes give up when it gets hard and say "패배" (about 20% chance)

Examples: 사과, 과학, 학생, 생일, 일기""",

    3: """You are playing a Korean word chain game (끝말잇기) on NORMAL mode.
You should:
- Use common Korean nouns
- Balance between easy and moderately difficult words
- Use a mix of 2-4 syllable words
- Give up only when truly stuck and say "패배"

Play fairly and competitively.""",

    4: """You are playing a Korean word chain game (끝말잇기) on HARD mode.
You should:
- Use more advanced vocabulary
- Try to end words with difficult characters (like ㄹ받침)
- Use 3-4 syllable words more often
- Use words that are valid but less commonly used
- Rarely give up - try very hard to find words

Examples: 철학자, 자동차, 차별화, 화학식""",

    5: """You are playing a Korean word chain game (끝말잇기) on EXPERT mode.
You are an expert player trying to WIN. You should:
- Use the most difficult words possible
- Strategically use words ending in hard characters (륨, 늄, 즘 등)
- Use technical, academic, or rare words
- Try to trap the player with difficult endings
- NEVER give up - always find a word
- Use words like: 알루미늄, 나트륨, 스펙트럼, 플라토늄

Your goal is to make the player unable to respond."""
}

WORDCHAIN_BASE = """Rules:
1. The user says a Korean word
2. You must respond with a Korean word that starts with the last character of the user's word
3. Words cannot be repeated (check the used_words list)
4. Only use Korean nouns (no proper nouns, no single characters)
5. If you cannot find a valid word, respond with exactly: 패배

IMPORTANT: Respond ONLY with a single Korean word. No explanations, no punctuation, no extra text."""


def get_difficulty_prompt(difficulty: int) -> str:
    return DIFFICULTY_PROMPTS.get(difficulty, DIFFICULTY_PROMPTS[3]) + "\n\n" + WORDCHAIN_BASE
