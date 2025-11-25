import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
from datetime import datetime
import tempfile
import numpy as np

def format_number(num, full=False):
    """
    Форматирует число для отображения
    
    Args:
        num: число для форматирования
        full: если True, показывает полное число с пробелами как разделителями
    """
    if num is None:
        return "Н/Д"
        
    try:
        num = int(num)
    except (ValueError, TypeError):
        return "Н/Д"
    
    # Если нужно полное число - показываем с разделителями (пробелами)
    if full:
        return f"{num:,}".replace(",", " ")
    
    # Иначе сокращаем
    if num < 1000:
        return str(num)
    elif num < 1000000:
        return f"{num/1000:.1f}K".replace('.0K', 'K')
    else:
        return f"{num/1000000:.1f}M".replace('.0M', 'M')

def format_growth(value, show_zero=False):
    """
    Форматирует значение прироста с плюсом или минусом и эмодзи
    
    Args:
        value: значение прироста (число)
        show_zero: показывать ли нулевой прирост
    
    Returns:
        Отформатированная строка с эмодзи
    """
    if value == 0:
        if show_zero:
            return "➖ без изменений"
        else:
            return ""
    
    # Выбираем эмодзи в зависимости от знака
    if value > 0:
        emoji = "📈"
        sign = "+"
        color = "green"
    else:
        emoji = "📉"
        sign = ""
        color = "red"
    
    # Форматируем число
    formatted_value = format_number(abs(value), full=True)
    
    return f"{emoji} {sign}{formatted_value}"

def format_growth_compact(value):
    """
    Компактное форматирование прироста (только число со знаком)
    
    Args:
        value: значение прироста
    
    Returns:
        Компактная строка типа "+1 234" или "-567"
    """
    if value == 0:
        return ""
    
    sign = "+" if value > 0 else ""
    return f"{sign}{format_number(value, full=True)}"

def get_growth_emoji(value):
    """
    Возвращает эмодзи в зависимости от знака прироста
    
    Args:
        value: значение прироста
    
    Returns:
        Эмодзи строка
    """
    if value > 0:
        return "📈"
    elif value < 0:
        return "📉"
    else:
        return "➖"

def create_growth_chart(analytics, metric, title):
    """Создает график роста определенной метрики"""
    try:
        # Проверяем наличие данных
        if not analytics or len(analytics) < 2:
            return None
            
        # Сортируем данные по времени (от старых к новым)
        analytics_sorted = sorted(analytics, key=lambda x: x["timestamp"])
        
        # Извлекаем даты и значения
        dates = [entry["timestamp"] for entry in analytics_sorted]
        
        values = []
        for entry in analytics_sorted:
            stat_value = entry["stats"].get(metric, 0)
            values.append(int(stat_value) if stat_value is not None else 0)
        
        # Создаем временный файл для графика
        fd, path = tempfile.mkstemp(suffix='.png')
        os.close(fd)
        
        # Создаем график
        plt.figure(figsize=(10, 6))
        plt.plot(dates, values, 'b-o', linewidth=2, markersize=8)
        
        # Стилизуем график
        plt.title(title, fontsize=16)
        plt.grid(True, linestyle='--', alpha=0.7)
        
        # Форматирование оси X (дат)
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
        plt.gcf().autofmt_xdate()
        
        # Добавляем значения над точками
        for i, (d, v) in enumerate(zip(dates, values)):
            plt.text(d, v + max(values) * 0.02, format_number(v), 
                    ha='center', va='bottom', fontsize=9)
        
        # Устанавливаем пределы оси Y
        min_value = min(values)
        max_value = max(values)
        plt.ylim(min_value - max_value * 0.05, max_value * 1.1)
        
        # Добавляем подписи осей
        metric_labels = {
            "followers": "Подписчики",
            "likes": "Лайки",
            "views": "Просмотры",
            "total_views": "Просмотры",
            "comments": "Комментарии",
            "shares": "Репосты",
            "videos": "Видео"
        }
        plt.ylabel(metric_labels.get(metric, metric), fontsize=12)
        plt.xlabel("Дата", fontsize=12)
        
        # Сохраняем график в файл
        plt.tight_layout()
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        
        return path
    
    except Exception as e:
        print(f"Ошибка создания графика: {e}")
        return None

def format_growth_line(value, label="Прирост"):
    """
    Форматирует строку для отображения прироста в заданном формате.
    Например: "📈 Прирост: +3 000" или "📈 Общий прирост: +0".
    
    Args:
        value: значение прироста (число)
        label: подпись для прироста
    
    Returns:
        Отформатированная строка с эмодзи и числом
    """
    # Если значение None или не является числом, не выводим строку
    if value is None or not isinstance(value, (int, float)):
        return ""
    
    # Если прирост нулевой, показываем "+0", как в примере
    if value == 0:
        return f"📈 {label}: +0"
    
    if value > 0:
        emoji = "📈"
        sign = "+"
    else:
        emoji = "📉"
        sign = ""  # Минус будет в самом числе
    
    formatted_value = f"{int(value):,}".replace(",", " ")
    return f"{emoji} {label}: {sign}{formatted_value}"
