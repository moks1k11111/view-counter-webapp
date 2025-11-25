"""
Telegram бот для запуска View Counter Mini App
"""

import logging
import os
from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

# Получаем токен из переменной окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8325383993:AAGl4tmstfnYIIFtEou2va7fnG37-ErC3Kk")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# URL твоего Mini App
WEBAPP_URL = "https://moks1k11111.github.io/view-counter-webapp/"  # Frontend URL на GitHub Pages


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user

    # Создаем кнопку с WebApp
    keyboard = [
        [KeyboardButton(
            text="📊 Открыть Analytics",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False
    )

    welcome_message = f"""
👋 Привет, {user.first_name}!

Добро пожаловать в **View Counter Analytics** -
первое в мире приложение для отслеживания
статистики по соц. сетям прямо в Telegram! 🚀

📊 *Что ты можешь:*
• Смотреть статистику по проектам
• Анализировать просмотры по платформам
• Отслеживать прогресс к цели
• Видеть топ участников
• Получать бонусы

🎯 *Нажми кнопку ниже, чтобы открыть приложение!*
    """

    await update.message.reply_text(
        welcome_message,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """
📖 *Справка*

Используй кнопку "📊 Открыть Analytics" для доступа к приложению.

*Доступные функции:*
📊 Статистика - общая статистика проекта
📂 Проекты - список твоих проектов
👤 Профиль - твоя личная статистика

*Возникли вопросы?*
Пиши @your_support_username
    """

    await update.message.reply_text(
        help_text,
        parse_mode='Markdown'
    )


def main() -> None:
    """Запуск бота"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Запускаем бота
    logger.info("🚀 WebApp Bot запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
