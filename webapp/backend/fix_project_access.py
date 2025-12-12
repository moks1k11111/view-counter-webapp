"""
Скрипт для добавления доступа пользователя ко всем проектам
"""

import os
import uuid
from datetime import datetime
from database_adapter import get_database

USER_ID = "873564841"  # Твой Telegram user ID


def fix_project_access():
    """Добавляем пользователя ко всем проектам"""

    pg_db = get_database()

    print(f"🔄 Добавляем пользователя {USER_ID} ко всем проектам...")

    # Получаем все проекты
    pg_db.cursor.execute("SELECT id, name FROM projects")
    projects = pg_db.cursor.fetchall()

    print(f"📊 Найдено проектов: {len(projects)}")

    added_count = 0
    for project in projects:
        project_id = project[0]
        project_name = project[1]

        # Проверяем, есть ли уже связь
        pg_db.cursor.execute("""
            SELECT id FROM project_users
            WHERE project_id = %s AND user_id = %s
        """, (project_id, USER_ID))

        if pg_db.cursor.fetchone():
            print(f"  ⏭️  Проект '{project_name}' - доступ уже есть")
            continue

        # Добавляем связь
        link_id = str(uuid.uuid4())
        pg_db.cursor.execute("""
            INSERT INTO project_users (id, project_id, user_id, added_at)
            VALUES (%s, %s, %s, %s)
        """, (link_id, project_id, USER_ID, datetime.now().isoformat()))

        pg_db.conn.commit()
        added_count += 1
        print(f"  ✅ Проект '{project_name}' - доступ добавлен")

    pg_db.conn.close()
    print(f"\n✅ Готово! Добавлено доступов: {added_count}")


if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL не установлен")
        exit(1)

    fix_project_access()
