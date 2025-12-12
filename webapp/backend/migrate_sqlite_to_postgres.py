"""
Скрипт для миграции данных из SQLite в PostgreSQL
Переносит проекты, пользователей и аккаунты
"""

import os
import sqlite3
from database_adapter import get_database
from project_manager import ProjectManager

# Путь к SQLite базе
SQLITE_DB_PATH = "tiktok_analytics.db"


def migrate_data():
    """Миграция данных из SQLite в PostgreSQL"""

    # Подключаемся к SQLite
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    # Подключаемся к PostgreSQL (через DATABASE_URL)
    pg_db = get_database()
    project_manager = ProjectManager(pg_db)

    print("🔄 Начинаем миграцию из SQLite в PostgreSQL...")

    # 1. Мигрируем пользователей
    print("\n👥 Миграция пользователей...")
    sqlite_cursor.execute("SELECT * FROM users")
    users = sqlite_cursor.fetchall()

    for user in users:
        try:
            pg_db.cursor.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (user['user_id'], user['username'], user['first_name'], user['last_name'], user['created_at']))
            print(f"  ✅ Пользователь {user['username']} ({user['user_id']})")
        except Exception as e:
            print(f"  ⚠️ Ошибка при миграции пользователя {user['user_id']}: {e}")

    pg_db.conn.commit()
    print(f"✅ Мигрировано пользователей: {len(users)}")

    # 2. Мигрируем проекты
    print("\n📁 Миграция проектов...")
    sqlite_cursor.execute("SELECT * FROM projects")
    projects = sqlite_cursor.fetchall()

    for project in projects:
        try:
            # Проверяем, есть ли колонка allowed_platforms
            allowed_platforms = project['allowed_platforms'] if 'allowed_platforms' in project.keys() else '{"tiktok": true, "instagram": true, "facebook": true, "youtube": true, "threads": true}'

            pg_db.cursor.execute("""
                INSERT INTO projects (id, name, google_sheet_name, start_date, end_date,
                                     target_views, geo, kpi_views, created_at, is_active, allowed_platforms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (project['id'], project['name'], project['google_sheet_name'],
                  project['start_date'], project['end_date'], project['target_views'],
                  project['geo'], project['kpi_views'], project['created_at'],
                  bool(project['is_active']), allowed_platforms))
            print(f"  ✅ Проект '{project['name']}' ({project['id']})")
        except Exception as e:
            print(f"  ⚠️ Ошибка при миграции проекта {project['name']}: {e}")

    pg_db.conn.commit()
    print(f"✅ Мигрировано проектов: {len(projects)}")

    # 3. Мигрируем связи пользователей с проектами
    print("\n🔗 Миграция связей пользователь-проект...")
    sqlite_cursor.execute("SELECT * FROM project_users")
    project_users = sqlite_cursor.fetchall()

    for pu in project_users:
        try:
            pg_db.cursor.execute("""
                INSERT INTO project_users (id, project_id, user_id, added_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (project_id, user_id) DO NOTHING
            """, (pu['id'], pu['project_id'], pu['user_id'], pu['added_at']))
            print(f"  ✅ Связь проект {pu['project_id'][:8]}... → user {pu['user_id']}")
        except Exception as e:
            print(f"  ⚠️ Ошибка при миграции связи: {e}")

    pg_db.conn.commit()
    print(f"✅ Мигрировано связей: {len(project_users)}")

    # 4. Мигрируем аккаунты соцсетей
    print("\n📱 Миграция аккаунтов соцсетей...")
    sqlite_cursor.execute("SELECT * FROM project_social_accounts")
    accounts = sqlite_cursor.fetchall()

    for account in accounts:
        try:
            pg_db.cursor.execute("""
                INSERT INTO project_social_accounts
                (id, project_id, user_id, platform, profile_link, username,
                 followers, likes, videos, views, added_at, is_active, status, topic)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (account['id'], account['project_id'], account['user_id'],
                  account['platform'], account['profile_link'], account['username'],
                  account['followers'], account['likes'], account['videos'],
                  account['views'], account['added_at'], bool(account['is_active']),
                  account.get('status', 'active'), account.get('topic', '')))
            print(f"  ✅ Аккаунт {account['username']} ({account['platform']})")
        except Exception as e:
            print(f"  ⚠️ Ошибка при миграции аккаунта {account['username']}: {e}")

    pg_db.conn.commit()
    print(f"✅ Мигрировано аккаунтов: {len(accounts)}")

    # 5. Мигрируем снапшоты
    print("\n📊 Миграция снапшотов...")
    sqlite_cursor.execute("SELECT * FROM account_snapshots")
    snapshots = sqlite_cursor.fetchall()

    for snapshot in snapshots:
        try:
            # Проверяем наличие total_videos_fetched
            total_videos = snapshot['total_videos_fetched'] if 'total_videos_fetched' in snapshot.keys() else 0

            pg_db.cursor.execute("""
                INSERT INTO account_snapshots
                (id, account_id, followers, likes, comments, videos, views,
                 total_videos_fetched, snapshot_time)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (snapshot['id'], snapshot['account_id'], snapshot['followers'],
                  snapshot['likes'], snapshot['comments'], snapshot['videos'],
                  snapshot['views'], total_videos, snapshot['snapshot_time']))
        except Exception as e:
            print(f"  ⚠️ Ошибка при миграции снапшота: {e}")

    pg_db.conn.commit()
    print(f"✅ Мигрировано снапшотов: {len(snapshots)}")

    # Закрываем подключения
    sqlite_conn.close()
    pg_db.conn.close()

    print("\n✅ Миграция завершена!")


if __name__ == "__main__":
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"❌ SQLite база не найдена: {SQLITE_DB_PATH}")
        exit(1)

    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL не установлен. Запустите скрипт с DATABASE_URL")
        exit(1)

    migrate_data()
