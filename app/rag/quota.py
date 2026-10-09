"""Conservative daily token reservations, shared by API and indexing workers."""
from datetime import datetime, timezone
from functools import lru_cache

from redis.asyncio import Redis
from app.config.settings import settings
from app.rag.embedding import ProviderUnavailable

RESERVE = """
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
local amount = tonumber(ARGV[1])
local budget = tonumber(ARGV[2])
if used + amount > budget then return 0 end
redis.call('INCRBY', KEYS[1], amount)
redis.call('EXPIRE', KEYS[1], ARGV[3])
return 1
"""


class TokenBudgetExceeded(RuntimeError):
    pass


@lru_cache(maxsize=1)
def quota_client():
    return Redis.from_url(settings.RATE_LIMIT_STORAGE_URI,
                          socket_connect_timeout=2, socket_timeout=2)


async def reserve_tokens(user_id, amount):
    if amount <= 0 or settings.RAG_TEST_MODE:
        return
    if not settings.RATE_LIMIT_STORAGE_URI.startswith(('redis://', 'rediss://')):
        if settings.ENVIRONMENT == 'production':
            raise ProviderUnavailable('Shared token budgets are not configured.')
        return  # Explicitly documented development-only behavior.
    now = datetime.now(timezone.utc)
    amount *= settings.RAG_PROVIDER_MAX_RETRIES + 1
    key = f'rag:token-budget:{user_id}:{now:%Y-%m-%d}'
    # Retain keys slightly beyond the day boundary; the date selects the budget.
    try:
        allowed = await quota_client().eval(RESERVE, 1, key, amount,
                                           settings.RAG_DAILY_TOKEN_BUDGET, 172800)
    except Exception as exc:
        raise ProviderUnavailable('Token budget storage unavailable.') from exc
    if not allowed:
        raise TokenBudgetExceeded('Daily AI token budget exhausted.')
