#!/usr/bin/env python3
"""
Скрипт для создания тестового проекта в базе данных
"""

import sys
import os

# Добавляем путь к модулям
backend_path = os.path.join(os.path.dirname(__file__), 'webapp', 'backend')
sys.path.insert(0, backend_path)

from project_manager import ProjectManager
from database_sqlite import SQLiteDatabase
from datetime import datetime, timedelta

def create_test_project():
    """Создает тестовый проект для демонстрации"""

    # Подключаемся к базе данных
    db = SQLiteDatabase("tiktok_analytics.db")
    pm = ProjectManager(db)

    # ID тестового пользователя
    test_user_id = "873564841"

    # Создаем тестовый проект
    project_data = {
        "name": "Тестовый проект Украина",
        "google_sheet_name": "Test Project Sheet",
        "start_date": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"),
        "end_date": (datetime.now() + timedelta(days=23)).strftime("%Y-%m-%d"),
        "target_views": 1000000,
        "geo": "Украина"
    }

    print(f"Создаю проект: {project_data['name']}")
    project = pm.create_project(**project_data)

    if project:
        project_id = project['id']
        print(f"✅ Проект создан с ID: {project_id}")

        # Добавляем пользователя в проект
        success = pm.add_user_to_project(project_id, test_user_id)
        if success:
            print(f"✅ Пользователь {test_user_id} добавлен в проект")
        else:
            print(f"⚠️  Не удалось добавить пользователя в проект")

        # Устанавливаем как текущий проект
        pm.set_user_current_project(test_user_id, project_id)
        print(f"✅ Проект установлен как текущий для пользователя")

    else:
        print("❌ Ошибка создания проекта")

    # Создаем еще один проект
    project_data2 = {
        "name": "Проект Россия",
        "google_sheet_name": "Russia Project Sheet",
        "start_date": (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"),
        "end_date": (datetime.now() + timedelta(days=27)).strftime("%Y-%m-%d"),
        "target_views": 500000,
        "geo": "Россия"
    }

    print(f"\nСоздаю проект: {project_data2['name']}")
    project2 = pm.create_project(**project_data2)

    if project2:
        project_id2 = project2['id']
        print(f"✅ Проект создан с ID: {project_id2}")
        pm.add_user_to_project(project_id2, test_user_id)
        print(f"✅ Пользователь {test_user_id} добавлен в проект")

    print("\n✅ Готово! Тестовые проекты созданы")
    print(f"\nПроверьте базу данных: tiktok_analytics.db")

if __name__ == "__main__":
    create_test_project()
