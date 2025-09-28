from gpt4all import GPT4All
import os
import time

def log(message):
    """Добавляет метку времени к каждому сообщению"""
    print(f"[{time.strftime('%H:%M:%S')}] {message}")

def download_model():
    """Скачивание конкретной модели"""
    log("📥 Начинаем попытку скачать модель...")

    models_to_try = [
        "orca-mini-3b.ggmlv3.q4_0.bin",
        "mistral-7b-openorca.ggmlv3.q4_0.bin", 
        "gpt4all-falcon-newbpe-q4_0.gguf",
        "orca-2-7b.Q4_0.gguf"
    ]

    for model_name in models_to_try:
        try:
            log(f"🔄 Пробуем: {model_name}")
            GPT4All(model_name)  # Просто проверка, что модель доступна
            log(f"✅ Успешно скачана: {model_name}")
            return model_name  # ВАЖНО: возвращаем имя модели
        except Exception as e:
            log(f"❌ Ошибка при скачивании {model_name}: {e}")
    
    log("❌ Ни одна модель не была скачана.")
    return None


def check_existing_models():
    """Проверяем существующие модели"""
    models_dir = os.path.expanduser("~/.cache/gpt4all")
    log(f"🔍 Проверяем папку моделей: {models_dir}")

    if os.path.exists(models_dir):
        models = os.listdir(models_dir)
        if models:
            log("📋 Найдены следующие модели:")
            for model in models:
                print(f"  - {model}")
            return models
        else:
            log("⚠️ Папка пуста — моделей нет.")
    else:
        log("❌ Папка моделей не существует.")
    return []

if __name__ == "__main__":
    log("🚀 Запуск скрипта download_model.py")
    existing_models = check_existing_models()

    if not existing_models:
        log("📦 Модели не найдены. Начинаем скачивание...")
        download_model()
    else:
        log("✅ Модели уже установлены. Можно запускать assistant_core.py")
