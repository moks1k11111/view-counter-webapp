import logging
import asyncio
import os
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Config
# Пытаемся взять токен из ENV, иначе берем жестко заданный
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8325383993:AAGl4tmstfnYIIFtEou2va7fnG37-ErC3Kk")
# Твоя рабочая ссылка
WEBAPP_URL = "https://moks1k11111.github.io/view-counter-webapp/index.html"

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /start command"""
    logger.info(f"Received /start from {update.effective_user.id}")

    try:
        keyboard = [
            [KeyboardButton(
                text="📊 Открыть Аналитику",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "👋 Бот обновлен и работает!\nНажми кнопку ниже:",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error in start: {e}")

async def main():
    """Start the bot"""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))

    # ВАЖНО: Удаляем вебхук перед поллингом, чтобы избежать конфликтов
    logger.info("Deleting webhook...")
    await application.bot.delete_webhook(drop_pending_updates=True)

    logger.info("🚀 Bot is starting polling...")
    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    try:
        # Используем asyncio.run для корректного запуска асинхронного кода
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}")
