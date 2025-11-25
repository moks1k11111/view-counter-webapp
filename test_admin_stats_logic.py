#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Симуляция логики admin_stats_command для отладки
"""

import sys
sys.path.insert(0, '/home/claude')

from utils import format_growth_line, format_number

print("=" * 70)
print("Симуляция логики admin_stats_command")
print("=" * 70)

# Симулируем platforms_stats
platforms_stats = {
    "tiktok": {"total": 45, "new": 35, "old": 5, "ban": 5, "followers": 12000, "views": 5000000, "videos": 850, "total_views": 5000000},
    "instagram": {"total": 38, "new": 30, "old": 3, "ban": 5, "followers": 9800, "views": 1548543, "videos": 520, "total_views": 1548543},
    "facebook": {"total": 7, "new": 7, "old": 0, "ban": 0, "followers": 0, "views": 1894762, "videos": 347, "total_views": 1894762},
    "youtube": {"total": 8, "new": 4, "old": 0, "ban": 4, "followers": 0, "views": 231029, "videos": 193, "total_views": 231029}
}

# Симулируем daily_growth (как будто calculate_global_growth вернул это)
daily_growth_scenario1 = {
    "tiktok": {"views": 0},
    "instagram": {"views": 0},
    "facebook": {"views": 0},
    "youtube": {"views": 0}
}

daily_growth_scenario2 = {
    "tiktok": {"views": 50000},
    "instagram": {"views": 12000},
    "facebook": {"views": 5000},
    "youtube": {"views": 3000}
}

daily_growth_scenario3 = {
    "tiktok": {"views": -10000},
    "instagram": {"views": 5000},
    "facebook": {"views": 0},
    "youtube": {"views": 2000}
}

scenarios = [
    ("Сценарий 1: Все нули (первый запуск)", daily_growth_scenario1),
    ("Сценарий 2: Положительный прирост", daily_growth_scenario2),
    ("Сценарий 3: Смешанный прирост", daily_growth_scenario3),
]

for scenario_name, daily_growth in scenarios:
    print(f"\n{'=' * 70}")
    print(f"{scenario_name}")
    print(f"{'=' * 70}")
    
    # Расчет total_views_growth (как в коде)
    total_views_growth = 0
    if daily_growth:
        total_views_growth = sum(daily_growth.get(p, {}).get("views", 0) for p in platforms_stats.keys())
    
    print(f"\ndaily_growth: {daily_growth}")
    print(f"total_views_growth: {total_views_growth}")
    
    # Формирование строки (как в коде)
    growth_line = format_growth_line(total_views_growth, label="Общий прирост")
    
    print(f"\ngrowth_line: {repr(growth_line)}")
    print(f"len(growth_line): {len(growth_line)}")
    print(f"bool(growth_line): {bool(growth_line)}")
    
    # Итоговый блок
    total_profiles = sum(p["total"] for p in platforms_stats.values())
    total_followers = sum(p["followers"] for p in platforms_stats.values())
    total_content = sum(p["videos"] for p in platforms_stats.values())
    total_views = sum(p["views"] for p in platforms_stats.values())
    
    message2 = (
        f'━━━━━━━━━━━━━━━\n'
        f'📈 *ИТОГО:*\n'
        f'📱 Всего профилей: {total_profiles}\n'
        f'👥 Всего подписчиков: {format_number(total_followers)}\n'
        f'🎬 Контента: {total_content}\n'
    )
    
    # Добавляем строку прироста (БЕЗ проверки if)
    message2 += f'{growth_line}\n'
    
    message2 += f'👁 Всего просмотров: {format_number(total_views, full=True)}'
    
    print(f"\n--- Итоговое сообщение ---")
    print(message2)

print(f"\n{'=' * 70}")
print("Тест завершен")
print("=" * 70)
