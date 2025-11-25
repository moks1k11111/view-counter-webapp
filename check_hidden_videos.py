import requests
import json
from config import RAPIDAPI_KEY, RAPIDAPI_BASE_URL

TEST_USERNAME = "stb_ua_holostyak"

class VideoChecker:
    def __init__(self):
        self.api_key = RAPIDAPI_KEY
        self.base_url = RAPIDAPI_BASE_URL
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "tiktok-api23.p.rapidapi.com"
        }
    
    def get_user_info(self, username):
        """Получение secUid"""
        endpoint = f"{self.base_url}/api/user/info"
        response = requests.get(endpoint, headers=self.headers, params={"uniqueId": username}, timeout=30)
        data = response.json()
        if data.get("statusCode") == 0:
            return data.get("userInfo", {}).get("user", {}).get("secUid")
        return None
    
    def get_all_videos(self, sec_uid):
        """Получение всех видео"""
        endpoint = f"{self.base_url}/api/user/posts"
        all_items = []
        cursor = 0
        has_more = True
        
        while has_more and len(all_items) < 200:
            response = requests.get(
                endpoint, 
                headers=self.headers, 
                params={"secUid": sec_uid, "count": "35", "cursor": str(cursor)},
                timeout=30
            )
            data = response.json()
            
            if "data" in data:
                data_obj = data.get("data", {})
                items = data_obj.get("itemList", [])
                has_more = data_obj.get("hasMore", False)
                cursor = data_obj.get("cursor", cursor)
                all_items.extend(items)
            else:
                break
        
        return all_items
    
    def analyze_videos(self, items):
        """Анализ параметров видео для поиска признаков скрытых"""
        print(f"\n{'='*70}")
        print(f"🔍 АНАЛИЗ {len(items)} ВИДЕО")
        print(f"{'='*70}\n")
        
        # Собираем все уникальные ключи
        all_keys = set()
        for item in items:
            all_keys.update(item.keys())
        
        print(f"📋 Найдено полей в объекте видео: {len(all_keys)}")
        print(f"Основные поля: {', '.join(sorted(list(all_keys))[:20])}...\n")
        
        # Проверяем интересные поля
        interesting_fields = [
            'video', 'privateItem', 'forFriend', 'secret', 'shareEnabled',
            'duetEnabled', 'stitchEnabled', 'itemMute', 'officalItem',
            'vl1', 'isAd', 'status'
        ]
        
        print(f"🔎 Проверяем поля-кандидаты на признак 'скрытости':\n")
        
        field_stats = {}
        
        for field in interesting_fields:
            values = []
            for item in items:
                if field in item:
                    val = item[field]
                    values.append(val)
            
            if values:
                unique_values = set(str(v) for v in values)
                field_stats[field] = {
                    'total': len(values),
                    'unique': unique_values
                }
                print(f"   {field}: найдено в {len(values)}/{len(items)} видео")
                if len(unique_values) <= 5:
                    print(f"      Уникальные значения: {unique_values}")
                print()
        
        # Проверяем поле video.privateItem если есть
        print(f"\n{'='*70}")
        print(f"🎯 ДЕТАЛЬНАЯ ПРОВЕРКА ПОЛЯ 'video'")
        print(f"{'='*70}\n")
        
        video_private_count = 0
        video_public_count = 0
        
        sample_private = None
        sample_public = None
        
        for idx, item in enumerate(items):
            video = item.get('video', {})
            
            # Проверяем различные варианты названий
            is_private = (
                video.get('privateItem') or 
                video.get('isPrivate') or
                item.get('privateItem') or
                item.get('isPrivate') or
                item.get('secret')
            )
            
            if is_private:
                video_private_count += 1
                if sample_private is None:
                    sample_private = {
                        'index': idx,
                        'id': item.get('id'),
                        'desc': item.get('desc', '')[:50],
                        'stats': item.get('stats', {})
                    }
            else:
                video_public_count += 1
                if sample_public is None:
                    sample_public = {
                        'index': idx,
                        'id': item.get('id'),
                        'desc': item.get('desc', '')[:50],
                        'stats': item.get('stats', {})
                    }
        
        print(f"✅ Публичных видео: {video_public_count}")
        print(f"🔒 Приватных видео: {video_private_count}")
        
        if sample_public:
            print(f"\n📌 Пример ПУБЛИЧНОГО видео #{sample_public['index']}:")
            print(f"   ID: {sample_public['id']}")
            print(f"   Описание: {sample_public['desc']}")
            print(f"   Просмотров: {sample_public['stats'].get('playCount', 0):,}")
        
        if sample_private:
            print(f"\n🔒 Пример ПРИВАТНОГО видео #{sample_private['index']}:")
            print(f"   ID: {sample_private['id']}")
            print(f"   Описание: {sample_private['desc']}")
            print(f"   Просмотров: {sample_private['stats'].get('playCount', 0):,}")
        
        # Сохраняем образцы в JSON для детального изучения
        if sample_private or sample_public:
            print(f"\n{'='*70}")
            print(f"💾 СОХРАНЕНИЕ ОБРАЗЦОВ В ФАЙЛЫ")
            print(f"{'='*70}\n")
            
            if sample_public:
                public_item = items[sample_public['index']]
                with open('sample_public_video.json', 'w', encoding='utf-8') as f:
                    json.dump(public_item, f, indent=2, ensure_ascii=False)
                print(f"✅ Публичное видео сохранено в: sample_public_video.json")
            
            if sample_private:
                private_item = items[sample_private['index']]
                with open('sample_private_video.json', 'w', encoding='utf-8') as f:
                    json.dump(private_item, f, indent=2, ensure_ascii=False)
                print(f"✅ Приватное видео сохранено в: sample_private_video.json")
        
        return {
            'total': len(items),
            'public': video_public_count,
            'private': video_private_count
        }
    
    def check_profile(self, username):
        """Полная проверка профиля"""
        print(f"\n{'🔬'*35}")
        print(f"ПРОВЕРКА СКРЫТЫХ ВИДЕО: @{username}")
        print(f"{'🔬'*35}\n")
        
        sec_uid = self.get_user_info(username)
        if not sec_uid:
            print("❌ Не удалось получить secUid")
            return
        
        items = self.get_all_videos(sec_uid)
        print(f"📊 Получено {len(items)} видео через API")
        
        result = self.analyze_videos(items)
        
        print(f"\n{'='*70}")
        print(f"📊 ИТОГОВАЯ СТАТИСТИКА")
        print(f"{'='*70}")
        print(f"Всего видео: {result['total']}")
        print(f"✅ Публичных: {result['public']}")
        print(f"🔒 Приватных: {result['private']}")
        print(f"{'='*70}\n")


if __name__ == "__main__":
    checker = VideoChecker()
    checker.check_profile(TEST_USERNAME)
    
    print("\n" + "="*70)
    print("✅ Анализ завершён!")
    print("📁 Проверьте файлы sample_public_video.json и sample_private_video.json")
    print("="*70 + "\n")
