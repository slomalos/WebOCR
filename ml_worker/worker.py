import pika
import json
import requests
import base64
import cv2
import numpy as np
from PIL import Image
import io
from minio import Minio

OLLAMA_URL = "http://localhost:11434/api/generate"
GO_SERVER_URL = "http://localhost:8080/api/internal/complete" 

MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"

TOP_CROP_PERCENT = 0.214
BOTTOM_CROP_PERCENT = 0.05
LEFT_CROP_PERCENT = 0.03
RIGHT_CROP_PERCENT = 0.05

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

def process_image_in_memory(image_bytes):
    print("   [+] Начинаем обрезку (in-memory)...")
    
    pil_image = Image.open(io.BytesIO(image_bytes))
    pil_image.seek(0)
    
    cv_image = np.array(pil_image.convert('RGB'))
    image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2BGR)

    h, w = image.shape[:2]
    final_cropped = image[
        int(h * TOP_CROP_PERCENT):int(h * (1.0 - BOTTOM_CROP_PERCENT)), 
        int(w * LEFT_CROP_PERCENT):int(w * (1.0 - RIGHT_CROP_PERCENT))
    ]
    
    success, buffer = cv2.imencode('.jpg', final_cropped)
    if not success:
        raise Exception("Не удалось сконвертировать изображение в JPEG")
        
    jpeg_bytes = buffer.tobytes()
    base64_image = base64.b64encode(jpeg_bytes).decode('utf-8')
    
    return base64_image, jpeg_bytes

def recognize_with_ollama(base64_image):
    print("Отправка готового скана на распознавание")
    prompt = """Распознай текст на изображении. 
СТРОГИЕ ПРАВИЛА:
1. Пиши только то, что видишь.
2. Ничего не додумывай. Если слово обрывается, пиши как есть.
3. Не пиши никаких вводных слов."""

    payload = {
        "model": "qwen2.5vl:3b", 
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

def process_task(ch, method, properties, body):
    try:
        task_data = json.loads(body.decode('utf-8'))
        doc_id = task_data.get("document_id")
        storage_path = task_data.get("file_path")
        
        bucket_name, object_name = storage_path.split("/", 1)
        
        print(f"Задача: {doc_id}")

        response = minio_client.get_object(bucket_name, object_name)
        image_bytes = response.read()
        response.close()
        response.release_conn()

        base64_image, jpeg_bytes = process_image_in_memory(image_bytes)

        new_object_name = object_name.rsplit('.', 1)[0] + "_cropped.jpg"
        new_storage_path = f"{bucket_name}/{new_object_name}"
        
        print(f"Сохранение в MiniO: {new_object_name}")
        minio_client.put_object(
            bucket_name,
            new_object_name,
            io.BytesIO(jpeg_bytes),
            length=len(jpeg_bytes),
            content_type="image/jpeg"
        )
        
        recognized_text = recognize_with_ollama(base64_image)

        print("Отправляем текст на сервер")
        result_payload = {
            "document_id": doc_id,
            "parsed_text": recognized_text,
            "new_storage_url": new_storage_path
        }
        
        go_response = requests.post(GO_SERVER_URL, json=result_payload)
        if go_response.status_code != 200:
            raise Exception("Go-сервер не принял результат!")

        ch.basic_ack(delivery_tag=method.delivery_tag)
        print(f"[*] ЗАДАЧА ID:{doc_id} ПОЛНОСТЬЮ ЗАВЕРШЕНА")

    except Exception as e:
        print(f"[!] ОШИБКА ОБРАБОТКИ: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


if __name__ == "__main__":
    print("Запуск")
    params = pika.ConnectionParameters(host='localhost', heartbeat=0, blocked_connection_timeout=0)
    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    channel.queue_declare(queue='ocr_tasks', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='ocr_tasks', on_message_callback=process_task)

    print('Готов к работе')
    channel.start_consuming()