import pika
import json
import requests
import base64
import cv2
import numpy as np
from PIL import Image
import io
import os
from minio import Minio

# ==========================================
# КОНФИГУРАЦИЯ (Методология 12-Factor App)
# ==========================================
# Читаем из переменных окружения. Если их нет (запуск локально), берем localhost.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
AI_MODEL_NAME = os.getenv("AI_MODEL_NAME", "qwen2.5-vl:3b") # <--- НАЗВАНИЕ МОДЕЛИ

GO_SERVER_URL = os.getenv("GO_SERVER_URL", "http://localhost:8080/api/internal/complete")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "localhost")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

# Настройки статического кроппинга
TOP_CROP_PERCENT = 0.18
BOTTOM_CROP_PERCENT = 0.02
LEFT_CROP_PERCENT = 0.03
RIGHT_CROP_PERCENT = 0.03

# Инициализация клиента MinIO
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

# ==========================================
# 1. ОБРЕЗКА И ПЕРЕВОД В JPEG
# ==========================================
def process_image_in_memory(image_bytes):
    print("   [+] Начинаем обрезку (in-memory)...")
    
    # PIL идеально читает форматы TIFF и JPG
    pil_image = Image.open(io.BytesIO(image_bytes))
    pil_image.seek(0)
    
    cv_image = np.array(pil_image.convert('RGB'))
    image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)

    h, w = image.shape[:2]
    final_cropped = image[
        int(h * TOP_CROP_PERCENT):int(h * (1.0 - BOTTOM_CROP_PERCENT)), 
        int(w * LEFT_CROP_PERCENT):int(w * (1.0 - RIGHT_CROP_PERCENT))
    ]
    
    # Кодируем обрезанную картинку в JPEG
    success, buffer = cv2.imencode('.jpg', final_cropped)
    if not success:
        raise Exception("Не удалось сконвертировать изображение в JPEG")
        
    jpeg_bytes = buffer.tobytes()
    base64_image = base64.b64encode(jpeg_bytes).decode('utf-8')
    
    return base64_image, jpeg_bytes

# ==========================================
# 2. РАСПОЗНАВАНИЕ (VLM / Ollama)
# ==========================================
def recognize_with_ollama(base64_image):
    print(f"   [+] Отправляем скан в Ollama (Модель: {AI_MODEL_NAME})...")
    prompt = """Распознай текст на изображении. 
СТРОГИЕ ПРАВИЛА:
1. Пиши только то, что видишь.
2. Ничего не додумывай. Если слово обрывается, пиши как есть.
3. Не пиши никаких вводных слов."""

    payload = {
        "model": AI_MODEL_NAME, 
        "prompt": prompt,
        "images": [base64_image],
        "stream": False,
        "temperature": 0.0
    }
    
    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code == 200:
        return response.json().get("response", "")
    else:
        raise Exception(f"Ошибка Ollama: {response.text}")

# ==========================================
# 3. ГЛАВНЫЙ ПРОЦЕССОР ЗАДАЧИ
# ==========================================
def process_task(ch, method, properties, body):
    try:
        task_data = json.loads(body.decode('utf-8'))
        doc_id = task_data.get("document_id")
        storage_path = task_data.get("file_path") # пример: "scans/12345.tif"
        
        bucket_name, object_name = storage_path.split("/", 1)
        
        print(f"\n[*] =======================================")
        print(f"[*] ВЗЯТА ЗАДАЧА! Документ ID: {doc_id}")

        # ШАГ 1: Скачиваем оригинал (TIFF/JPG) из MinIO
        response = minio_client.get_object(bucket_name, object_name)
        image_bytes = response.read()
        response.close()
        response.release_conn()

        # ШАГ 2: Обрезаем и конвертируем в JPEG
        base64_image, jpeg_bytes = process_image_in_memory(image_bytes)
        
        # ШАГ 3: Загружаем чистый JPEG обратно в MinIO
        new_object_name = object_name.rsplit('.', 1)[0] + "_cropped.jpg"
        new_storage_path = f"{bucket_name}/{new_object_name}"
        
        print(f"   [+] Сохраняем обрезанный JPEG: {new_object_name}")
        minio_client.put_object(
            bucket_name,
            new_object_name,
            io.BytesIO(jpeg_bytes),
            length=len(jpeg_bytes),
            content_type="image/jpeg"
        )
        
        # ШАГ 4: Распознаем через VLM
        recognized_text = recognize_with_ollama(base64_image)
        print("   [v] Распознавание успешно завершено!")

        # ШАГ 5: Отправляем результат (и новый путь к JPG) в Go-сервер
        print("   [+] Отправляем данные в Go-сервер...")
        result_payload = {
            "document_id": doc_id,
            "parsed_text": recognized_text,
            "new_storage_url": new_storage_path
        }
        
        go_response = requests.post(GO_SERVER_URL, json=result_payload)
        if go_response.status_code != 200:
            raise Exception(f"Go-сервер вернул ошибку: {go_response.status_code}")

        # ШАГ 6: Успешное подтверждение RabbitMQ
        ch.basic_ack(delivery_tag=method.delivery_tag)
        print(f"[*] ЗАДАЧА ID:{doc_id} ПОЛНОСТЬЮ ЗАВЕРШЕНА!")

    except Exception as e:
        print(f"[!] ОШИБКА ОБРАБОТКИ: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

# ==========================================
# ТОЧКА ВХОДА
# ==========================================
if __name__ == "__main__":
    print(f"[*] Запуск ML Worker'a. Подключение к RabbitMQ ({RABBITMQ_HOST})...")
    params = pika.ConnectionParameters(
        host=RABBITMQ_HOST, 
        heartbeat=0, 
        blocked_connection_timeout=0
    )
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.queue_declare(queue='ocr_tasks', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='ocr_tasks', on_message_callback=process_task)

    print(f"[*] Воркер готов к работе! Модель: {AI_MODEL_NAME}. Жду задачи...")
    channel.start_consuming()