"""
Скрипт для импорта аккаунтов из Google Sheets в PostgreSQL
"""

import os
import uuid
from datetime import datetime
from database_adapter import get_database
from project_sheets_manager import ProjectSheetsManager

# Название листа в Google Sheets
SHEET_NAME = "MainBD"


def import_from_sheets():
    """Импорт аккаунтов из Google Sheets в PostgreSQL"""

    # Подключаемся к PostgreSQL
    pg_db = get_database()

    # Подключаемся к Google Sheets
    credentials_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if not credentials_json:
        print("❌ GOOGLE_SHEETS_CREDENTIALS_JSON не установлен")
        return

    sheets_manager = ProjectSheetsManager(
        credentials_file="",
        spreadsheet_name="MainBD",
        credentials_json=credentials_json
    )

    print(f"🔄 Начинаем импорт из Google Sheets '{SHEET_NAME}'...")

    # Получаем список всех листов (проектов)
    worksheets = sheets_manager.spreadsheet.worksheets()
    print(f"📋 Найдено листов: {len(worksheets)}")

    for worksheet in worksheets:
        sheet_title = worksheet.title

        # Пропускаем служебные листы
        if sheet_title in ["Sheet1", "Лист1"]:
            print(f"⏭️  Пропускаем служебный лист: {sheet_title}")
            continue

        print(f"\n📄 Обрабатываем лист: {sheet_title}")

        # Проверяем, есть ли проект с таким названием в БД
        pg_db.cursor.execute("SELECT id FROM projects WHERE name = %s", (sheet_title,))
        project_row = pg_db.cursor.fetchone()

        if not project_row:
            print(f"  ⚠️  Проект '{sheet_title}' не найден в БД, создаём...")
            # Создаём проект
            project_id = str(uuid.uuid4())
            pg_db.cursor.execute("""
                INSERT INTO projects (id, name, google_sheet_name, start_date, end_date,
                                     target_views, geo, kpi_views, created_at, is_active, allowed_platforms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (project_id, sheet_title, "MainBD",
                  datetime.now().strftime("%Y-%m-%d"),
                  (datetime.now().replace(year=datetime.now().year + 1)).strftime("%Y-%m-%d"),
                  1000000, "", 1000, datetime.now().isoformat(), True,
                  '{"tiktok": true, "instagram": true, "facebook": true, "youtube": true, "threads": true}'))
            pg_db.conn.commit()
            print(f"  ✅ Создан проект '{sheet_title}' ({project_id})")
        else:
            project_id = project_row[0]
            print(f"  ✅ Найден проект '{sheet_title}' ({project_id})")

        # Читаем все записи из листа
        try:
            all_records = worksheet.get_all_records()
            print(f"  📊 Найдено записей в листе: {len(all_records)}")
        except Exception as e:
            print(f"  ❌ Ошибка чтения листа: {e}")
            continue

        imported_count = 0
        for record in all_records:
            try:
                # Извлекаем данные из Google Sheets
                telegram_user = record.get('@Username', 'Unknown')
                link = record.get('Link', '')
                platform = record.get('Platform', 'unknown').lower()
                username = record.get('Username', 'Unknown')
                followers = int(record.get('Followers', 0) or 0)
                likes = int(record.get('Likes', 0) or 0)
                videos = int(record.get('Videos', 0) or 0)
                views = int(record.get('Views', 0) or 0)
                status = record.get('Status', 'NEW')
                topic = record.get('Тематика', '')

                # Пропускаем пустые записи
                if not link:
                    continue

                # Проверяем, есть ли уже такой аккаунт
                pg_db.cursor.execute("""
                    SELECT id FROM project_social_accounts
                    WHERE project_id = %s AND profile_link = %s
                """, (project_id, link))

                if pg_db.cursor.fetchone():
                    print(f"    ⏭️  Аккаунт {username} уже существует, пропускаем")
                    continue

                # Добавляем аккаунт (без статистики - она будет в snapshots)
                account_id = str(uuid.uuid4())
                pg_db.cursor.execute("""
                    INSERT INTO project_social_accounts
                    (id, project_id, platform, profile_link, username,
                     telegram_user, added_at, is_active, status, topic)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (account_id, project_id, platform, link, username,
                      telegram_user, datetime.now().isoformat(),
                      True, status, topic))

                # Создаём первый снапшот
                snapshot_id = str(uuid.uuid4())
                pg_db.cursor.execute("""
                    INSERT INTO account_snapshots
                    (id, account_id, followers, likes, comments, videos, views,
                     total_videos_fetched, snapshot_time)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (snapshot_id, account_id, followers, likes, 0, videos, views, 0,
                      datetime.now().isoformat()))

                pg_db.conn.commit()
                imported_count += 1
                print(f"    ✅ Импортирован аккаунт: {username} ({platform})")

            except Exception as e:
                print(f"    ❌ Ошибка импорта записи: {e}")
                pg_db.conn.rollback()
                continue

        print(f"  ✅ Импортировано аккаунтов из '{sheet_title}': {imported_count}")

    pg_db.conn.close()
    print("\n✅ Импорт завершён!")


if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL"):
        print("❌ DATABASE_URL не установлен")
        exit(1)

    if not os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON"):
        print("❌ GOOGLE_SHEETS_CREDENTIALS_JSON не установлен")
        exit(1)

    import_from_sheets()
