"""
Database adapter - универсальный адаптер для SQLite и PostgreSQL
Автоматически определяет тип БД по наличию DATABASE_URL
"""
import os
import logging

logger = logging.getLogger(__name__)


def get_database():
    """
    Фабрика для создания подключения к БД

    - Если DATABASE_URL задан - используем PostgreSQL
    - Иначе - используем SQLite
    """
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        logger.info("🐘 Using PostgreSQL database")
        from database_postgres import PostgreSQLDatabase
        return PostgreSQLDatabase(database_url)
    else:
        logger.info("💾 Using SQLite database")
        from database_sqlite import SQLiteDatabase
        return SQLiteDatabase()
