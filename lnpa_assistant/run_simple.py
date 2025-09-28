import os
import sys
import subprocess

def check_and_install():
    """Проверка и установка пакетов"""
    packages = [
        "gpt4all",
        "PyPDF2", 
        "python-docx",
        "beautifulsoup4",
        "html2text",
        "lxml"
    ]
    
    print("🔧 Проверяем установленные пакеты...")
    
    for package in packages:
        try:
            if package == "python-docx":
                import docx
            else:
                __import__(package.replace("-", ""))
            print(f"✅ {package} - установлен")
        except ImportError:
            print(f"📦 Устанавливаю {package}...")
            try:
                # Используем py команду для установки
                result = subprocess.run([
                    sys.executable, "-m", "pip", "install", package
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"✅ {package} - успешно установлен")
                else:
                    print(f"❌ Ошибка установки {package}: {result.stderr}")
            except Exception as e:
                print(f"❌ Ошибка: {e}")

def main():
    print("🤖 Запуск ассистента ЛНПА")
    print("=" * 40)
    
    # Проверяем и устанавливаем пакеты
    check_and_install()
    
    # Создаем папку для документов
    docs_dir = "documents"
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
        print(f"\n📁 Создана папка '{docs_dir}'")
        print("Добавьте в нее файлы ЛНПА (PDF, DOCX, HTML, TXT)")
        input("Нажмите Enter после добавления файлов...")
    
    # Продолжаем только если есть документы
    files = os.listdir(docs_dir)
    if not files:
        print("❌ Папка documents пуста. Добавьте файлы и запустите снова.")
        return
    
    print(f"\n📁 Найдено файлов: {len(files)}")
    
    # Запускаем основной функционал
    try:
        from assistant_core import LNPAssistant
        assistant = LNPAssistant()
        assistant.run()
    except ImportError:
        print("❌ Основной модуль не загружен. Запускаю простой режим...")
        simple_mode()

def simple_mode():
    """Простой режим без сложных зависимостей"""
    print("\n🔍 Простой режим чтения документов")
    
    docs_dir = "documents"
    for filename in os.listdir(docs_dir):
        filepath = os.path.join(docs_dir, filename)
        print(f"\n📄 Файл: {filename}")
        
        # Просто показываем размер файла
        size = os.path.getsize(filepath)
        print(f"📏 Размер: {size} байт")
        
        # Пытаемся прочитать текстовые файлы
        if filename.lower().endswith('.txt'):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read(500)  # Первые 500 символов
                    print(f"📝 Содержимое: {content}...")
            except:
                print("❌ Не удалось прочитать файл")

if __name__ == "__main__":
    main()