"""Telegram alerts to the operator when a job source starts failing or recovers."""
import html
import httpx
from app.config import settings
from app.telegram import TelegramError, send_message


def build_alert(results: list[dict]) -> str | None:
    failing = [r for r in results if r.get("alert") == "failing"]
    recovered = [r for r in results if r.get("alert") == "recovered"]
    if not failing and not recovered:
        return None
    lines = []
    if failing:
        lines.append(f"⚠️ <b>{html.escape(settings.brand_name)}: {len(failing)} job source(s) failed {settings.alert_after_failures} polls in a row</b>")
        for r in failing:
            lines.append(f"• {html.escape(r['company'])} (<code>{html.escape(r['key'])}</code>): {html.escape((r['error'] or '')[:300])}")
    if recovered:
        if lines:
            lines.append("")
        lines.append(f"✅ <b>Working again:</b> {html.escape(', '.join(r['company'] for r in recovered))}")
    return "\n".join(lines)


async def send_source_alerts(results: list[dict]) -> bool:
    """Send one alert message for this poll's failing/recovered sources. Returns whether one was sent."""
    text = build_alert(results)
    if not text or not (settings.telegram_bot_token and settings.alert_chat_id):
        if text:
            print(text)
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            await send_message(client, settings.telegram_bot_token, settings.alert_chat_id, text)
        except TelegramError as exc:
            print(f"Could not send source alert: {exc}")
            return False
    return True
