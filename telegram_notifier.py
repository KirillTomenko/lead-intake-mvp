import os
import logging
import aiohttp

logger = logging.getLogger(__name__)

async def send_telegram_notification(message: str):
    """Отправка уведомления в Telegram"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not set, skipping notification")
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                if response.status == 200:
                    logger.info(f"✅ Telegram notification sent: {message[:50]}...")
                else:
                    logger.error(f"❌ Telegram API error: {response.status}")
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram notification: {e}")