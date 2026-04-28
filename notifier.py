import logging
import os
import asyncio
from datetime import datetime
from email.message import EmailMessage

# Async HTTP for Telegram
try:
    import aiohttp
except ImportError:
    aiohttp = None

logger = logging.getLogger(__name__)

async def send_telegram_notification(message: str):
    """Отправка уведомления в Telegram с поддержкой системного прокси"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram credentials not set, skipping notification")
        return
    
    if not aiohttp:
        logger.error("aiohttp not installed")
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    
    logger.info(f"📤 Sending Telegram to chat_id={chat_id}")
    
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        
        # 🔑 КЛЮЧЕВОЕ: trust_env=True заставляет aiohttp использовать системный прокси/VPN
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.post(url, json=data) as response:
                result = await response.json()
                if response.status == 200:
                    logger.info(f"✅ Telegram notification sent")
                else:
                    logger.error(f"❌ Telegram API error {response.status}: {result}")
                    
    except asyncio.TimeoutError:
        logger.error("❌ Telegram request timed out (30s)")
    except aiohttp.ClientConnectionError as e:
        logger.error(f"❌ Telegram connection error: {e}")
        logger.info("💡 Убедись, что VPN включён ПЕРЕД запуском сервера")
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram: {type(e).__name__}: {e}")

async def send_email_notification(lead_id: int, contact: str, name: str = None):
    """Отправка email уведомления через Gmail"""
    smtp_host = os.getenv("EMAIL_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_PORT", 587))
    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")
    email_recipient = os.getenv("EMAIL_RECIPIENT", email_user)
    
    if not all([email_user, email_password, email_recipient]):
        logger.warning("Email credentials not set, skipping notification")
        return
    
    try:
        import aiosmtplib
    except ImportError:
        logger.error("aiosmtplib not installed, install with: pip install aiosmtplib")
        return
    
    subject = f"🔔 Новая заявка #{lead_id}"
    body = f"""
Новая заявка получена!

📋 ID: #{lead_id}
👤 Имя: {name or 'Не указано'}
📞 Контакт: {contact}
⏰ Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---
Lead Intake MVP
    """.strip()
    
    msg = EmailMessage()
    msg.set_content(body)
    msg['Subject'] = subject
    msg['From'] = email_user
    msg['To'] = email_recipient
    
    try:
        await aiosmtplib.send(
            msg,
            hostname=smtp_host,
            port=smtp_port,
            start_tls=True,
            username=email_user,
            password=email_password,
        )
        logger.info(f"✅ Email sent to {email_recipient}")
    except Exception as e:
        logger.error(f"❌ Failed to send email: {e}")

async def notify_new_lead(lead_id: int, contact: str, name: str = None):
    """Главная функция уведомления (лог + Telegram + Email)"""
    message = f"🟢 New lead saved: id={lead_id}, contact={contact}, name={name or 'N/A'}"
    logger.info(message)
    
    # Telegram
    telegram_msg = f"""
🔔 <b>Новая заявка!</b>

📋 <b>ID:</b> #{lead_id}
👤 <b>Имя:</b> {name or 'Не указано'}
📞 <b>Контакт:</b> {contact}
⏰ <b>Время:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """.strip()
    await send_telegram_notification(telegram_msg)
    
    # Email
    await send_email_notification(lead_id, contact, name)

def log_error(message: str):
    """Логирование ошибок"""
    logger.error(f"🔴 {message}")