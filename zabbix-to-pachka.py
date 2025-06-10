#!/usr/bin/env python3
import sys
import requests
import json
import os
from pathlib import Path


CACHE_DIR = "/var/lib/zabbix/pachca_cache" # директория с кешем
CACHE_FILE = f"{CACHE_DIR}/message_ids.json" # сам файл кеша
API_URL = "https://api.pachca.com/api/shared/v1/messages" # эндпоинт API
ZABBIX_URL = "https://zabbix.sawady.local"  # путь до нашего сервера без слеша в конце 

# инициируем кэш
def init_cache():
    os.makedirs(CACHE_DIR, exist_ok=True)
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'w') as f:
            json.dump({}, f)
# читаем кэш
def read_cache():
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
# пишем данные в кэш
def write_cache(data):
    with open(CACHE_FILE, 'w') as f:
        json.dump(data, f, indent=2)
# формируем пэйлоад и отправляем его в эндпоинт
def send_to_pachca(token, chat_id, text, message_id=None):
    headers = {
        'Authorization': f"Bearer {token}",
        'Content-Type': 'application/json'
    }

    payload = {
        "message": {
            "entity_type": "discussion",
            "entity_id": chat_id,
            "chat_id": chat_id,
            "content": text
        }
    }

    try:
        if message_id:
            response = requests.put(f"{API_URL}/{message_id}", headers=headers, json=payload)
        else:
            response = requests.post(API_URL, headers=headers, json=payload)

        response.raise_for_status()
        return response.json()['data']['id']
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404 and message_id:
            print(f"Message {message_id} not found, sending new one", file=sys.stderr)
            return None
        raise

# форматируем сообщение

def format_message(subject, message, trigger_id, event_id, status):
    # Определение статуса по EVENT.STATUS и содержимому сообщения"""
    # Приоритет у статуса из Zabbix, но проверяем и текст для надежности
    is_resolved = status == "OK" or "Problem has been resolved" in message

    # Очищаем subject от статусов
    clean_subject = subject.replace("Resolved in", "").replace("Problem:", "").strip()

    if is_resolved:
        icon = "✅"
        title = "ПРОБЛЕМА РЕШЕНА"
        # Извлекаем время решения из сообщения
        duration = ""
        for line in message.split('\n'):
            if "Problem duration:" in line:
                duration = f" (решено за {line.split(':', 1)[1].strip()})"
    else:
        icon = "🔴"
        title = "НОВАЯ ПРОБЛЕМА"
        duration = ""

    zabbix_link = f"\n[Открыть в Zabbix]({ZABBIX_URL}/tr_events.php?triggerid={trigger_id}&eventid={event_id})"

    return f"""*{icon} {title}: {clean_subject}{duration}*

*Детали:*
{message}{zabbix_link}"""

def main():
    if len(sys.argv) < 7:
        print("Usage: ./zabbix_to_pachca.py <token> <chat_id> <subject> <message> <trigger_id> <event_id> <status>")
        sys.exit(1)

    token, chat_id, subject, message, trigger_id, event_id, status = sys.argv[1:8]

    init_cache()
    cache = read_cache()
    text = format_message(subject, message, trigger_id, event_id, status)

    try:
        message_id = cache.get(event_id)
        if message_id:
            new_id = send_to_pachca(token, chat_id, text, message_id)
            if not new_id:  # Если сообщение не найдено
                new_id = send_to_pachca(token, chat_id, text)
                cache[event_id] = new_id
        else:
            new_id = send_to_pachca(token, chat_id, text)
            cache[event_id] = new_id

        write_cache(cache)
        print(f"Message {'updated' if message_id else 'sent'}: {new_id}")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()