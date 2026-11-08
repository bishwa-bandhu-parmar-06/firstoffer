"""Minimal Telegram Bot API client: send an HTML-formatted message to a chat or channel."""
import asyncio
import httpx

API = "https://api.telegram.org"
MAX_ATTEMPTS = 4
# Telegram limits a bot to about 20 messages a minute in one group; space consecutive messages out.
SECONDS_BETWEEN_MESSAGES = 3.5


class TelegramError(Exception):
    pass


async def send_message(client: httpx.AsyncClient, token: str, chat_id: str, text: str) -> None:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.post(f"{API}/bot{token}/sendMessage", json=payload)
        except httpx.HTTPError as exc:
            # httpx errors include the request URL, which contains the bot token; never surface it.
            if attempt == MAX_ATTEMPTS - 1:
                raise TelegramError(f"network error talking to Telegram: {type(exc).__name__}") from None
            await asyncio.sleep(2 ** attempt)
            continue
        try:
            data = response.json()
        except ValueError:
            data = {}
        if data.get("ok"):
            return
        if response.status_code == 429:
            retry_after = (data.get("parameters") or {}).get("retry_after", 5)
            await asyncio.sleep(min(int(retry_after), 60) + 1)
            continue
        raise TelegramError(f"Telegram rejected the message ({response.status_code}): {data.get('description', 'no details')}")
    raise TelegramError("Telegram kept rate-limiting the bot; giving up for this digest")
