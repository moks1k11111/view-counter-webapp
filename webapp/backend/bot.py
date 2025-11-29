import logging
import os
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Config
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8325383993:AAGl4tmstfnYIIFtEou2va7fnG37-ErC3Kk")
WEBAPP_URL = "https://moks1k11111.github.io/view-counter-webapp/index.html"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple start handler that just shows the WebApp button"""
    user = update.effective_user

    # Keyboard with WebApp button
    keyboard = [
        [KeyboardButton(
            text="📊 Открыть Аналитику",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True
    )

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Нажми кнопку ниже, чтобы открыть панель аналитики.",
        reply_markup=reply_markup
    )

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    logger.info("🚀 Simple WebApp Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
