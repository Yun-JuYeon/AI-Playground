import redis.asyncio as redis
from openai import AsyncOpenAI
from .config import OPENAI_API_KEY, REDIS_HOST, REDIS_PORT

# Redis client
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    decode_responses=True
)

# OpenAI client
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
