#!/usr/bin/env python3
"""
Скрипт инициализации базы данных для Render.com
Запускается при старте приложения для создания тестовых данных
"""

import sys
import os

# Добавляем путь к модулям
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from project_manager import ProjectManager
from database_sqlite import SQLiteDatabase
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    """Инициализирует базу данных и создает тестовые данные если их нет"""

    try:
        # Подключаемся к базе данных
        db = SQLiteDatabase("tiktok_analytics.db")
        pm = ProjectManager(db)

        # Check if projects already exist
        all_projects = pm.get_all_projects(active_only=False)

        if len(all_projects) > 0:
            logger.info(f"✅ Database already contains {len(all_projects)} projects")
            return True

        logger.info("📝 Creating test projects...")

        # Test user ID
        test_user_id = "873564841"

        # Create first test project
        project_data = {
            "name": "Ukraine Campaign",
            "google_sheet_name": "Test Project Sheet",
            "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
            "end_date": (datetime.now() + timedelta(days=23)).strftime("%Y-%m-%d"),
            "target_views": 1000000,
            "geo": "Ukraine",
            "kpi_views": 5000
        }

        project = pm.create_project(**project_data)
        if project:
            project_id = project['id']
            pm.add_user_to_project(project_id, test_user_id)
            pm.set_user_current_project(test_user_id, project_id)
            logger.info(f"✅ Project 1 created: {project_data['name']}")

        # Create second test project
        project_data2 = {
            "name": "Russia Campaign",
            "google_sheet_name": "Russia Project Sheet",
            "start_date": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
            "end_date": (datetime.now() + timedelta(days=27)).strftime("%Y-%m-%d"),
            "target_views": 500000,
            "geo": "Russia",
            "kpi_views": 1000
        }

        project2 = pm.create_project(**project_data2)
        if project2:
            project_id2 = project2['id']
            pm.add_user_to_project(project_id2, test_user_id)
            logger.info(f"✅ Project 2 created: {project_data2['name']}")

        logger.info("✅ Database initialized with test data")
        return True

    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}")
        return False

if __name__ == "__main__":
    init_database()
