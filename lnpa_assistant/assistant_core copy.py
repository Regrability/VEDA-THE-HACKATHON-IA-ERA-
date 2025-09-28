import os
import re
import time
import json
import logging
import requests
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from gpt4all import GPT4All
import PyPDF2
from docx import Document
import hashlib

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class DocumentChunk:
    text: str
    metadata: Dict
    embedding: Optional[List[float]] = None

class EnhancedLNPAssistant:
    def __init__(self, data_dir="documents", persist_dir="./chroma_db", config_path="config.json"):
        self.data_dir = data_dir
        self.persist_dir = persist_dir
        self.config_path = config_path
        self.config = self.load_config()
        
        self.documents = []
        self.embedding_model = None
        self.llm_client = None
        self.vector_db = None
        self.collection = None
        self.templates = {}
        
        # DeepSeek специфичные атрибуты
        self.deepseek_api_key = None
        self.deepseek_base_url = "https://api.deepseek.com/v1"
        
        self.setup_system()
    
    def load_config(self) -> Dict:
        """Загрузка конфигурации"""
        default_config = {
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "llm_model": "qwen2.5-coder-7b-instruct-q4_0.gguf",
            "llm_provider": "deepseek",  # local, deepseek, openai, azure
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "max_results": 5,
            "temperature": 0.1,
            "max_tokens": 500,
            "deepseek_api_key": None,
            "deepseek_model": "deepseek-chat"
        }
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
        except FileNotFoundError:
            logger.info("Конфиг не найден, используются настройки по умолчанию")
        
        return default_config
    
    def setup_system(self):
        """Расширенная настройка системы"""
        logger.info("🚀 Инициализация AI-ассистента ЛПА/ЛНПА...")
        
        try:
            self.load_models()
            self.setup_vector_db()
            self.load_all_documents()
            self.load_templates()
            logger.info("✅ Система успешно инициализирована!")
        except Exception as e:
            logger.error(f"❌ Ошибка инициализации: {e}")
            raise
    
    def load_models(self):
        """Загрузка моделей с обработкой ошибок"""
        logger.info("📥 Загрузка моделей...")
        
        try:
            # Эмбеддинг модель всегда локальная
            self.embedding_model = SentenceTransformer(self.config["embedding_model"])
            logger.info("✅ Модель для эмбеддингов загружена")
            
            # Настройка LLM клиента в зависимости от провайдера
            llm_provider = self.config["llm_provider"]
            
            if llm_provider == "local":
                self.llm_client = GPT4All(self.config["llm_model"])
                logger.info("✅ Локальная LLM модель загружена")
                
            elif llm_provider == "deepseek":
                # Приоритет: переменная окружения -> конфиг -> ошибка
                api_key = os.getenv("DEEPSEEK_API_KEY") or self.config["deepseek_api_key"]
                if not api_key:
                    raise ValueError("DeepSeek API key not found. Set DEEPSEEK_API_KEY environment variable or add to config")
                
                self.llm_client = None  # Не используем клиент для DeepSeek
                self.llm_model = os.getenv("DEEPSEEK_MODEL") or self.config.get("deepseek_model", "deepseek-chat")
                self.deepseek_api_key = api_key
                
                logger.info(f"✅ DeepSeek настроен (модель: {self.llm_model})")
                
            elif llm_provider == "openai":
                # Реализация для OpenAI (можно добавить позже)
                logger.info("✅ OpenAI провайдер выбран")
                # self.llm_client = openai.OpenAI(api_key=...)
                
            else:
                raise ValueError(f"Неизвестный провайдер LLM: {llm_provider}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки моделей: {e}")
            raise

    def _call_deepseek_api(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str:
        """Прямой вызов DeepSeek API через HTTP запросы"""
        url = f"{self.deepseek_base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.deepseek_api_key}"
        }
        
        data = {
            "model": self.llm_model,
            "messages": [
                {
                    "role": "system", 
                    "content": "Ты - AI-ассистент для работы с юридическими и техническими документами ЛПА/ЛНПА. Отвечай точно и по делу."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                logger.error(f"❌ Неожиданный формат ответа DeepSeek: {result}")
                return "Ошибка: неверный формат ответа от API"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка запроса к DeepSeek API: {e}")
            return f"Ошибка соединения с DeepSeek API: {e}"
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON ответа: {e}")
            return "Ошибка обработки ответа от API"
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка при вызове DeepSeek API: {e}")
            return f"Неизвестная ошибка: {e}"

    def generate_with_online_model(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str:
        """Генерация текста с использованием онлайн-моделей через HTTP запросы"""
        try:
            llm_provider = self.config["llm_provider"]
            
            if llm_provider == "deepseek":
                return self._call_deepseek_api(prompt, max_tokens, temperature)
                
            elif llm_provider in ["openai", "azure"]:
                # Реализация для других провайдеров может быть добавлена здесь
                return f"Провайдер {llm_provider} пока не поддерживается"
                
            else:
                return "Неизвестный провайдер LLM"
                
        except Exception as e:
            logger.error(f"❌ Ошибка генерации с онлайн-моделью: {e}")
            return f"Ошибка: {e}"
    
    def setup_vector_db(self):
        """Настройка векторной БД с метриками"""
        try:
            self.vector_db = chromadb.PersistentClient(path=self.persist_dir)
            
            # Проверяем существующую коллекцию
            try:
                self.collection = self.vector_db.get_collection("lnp_documents")
                logger.info("📊 Найдена существующая коллекция документов")
            except Exception as e:
                logger.info("📊 Создание новой коллекции документов")
                self.collection = self.vector_db.create_collection(
                    name="lnp_documents",
                    metadata={"description": "База ЛПА/ЛНПА документов", "created": datetime.now().isoformat()}
                )
                
        except Exception as e:
            logger.error(f"❌ Ошибка настройки БД: {e}")
            raise
    
    def extract_text_from_pdf(self, filepath: str) -> str:
        """Извлечение текста из PDF"""
        try:
            with open(filepath, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            logger.error(f"❌ Ошибка чтения PDF {filepath}: {e}")
            return ""
    
    def extract_text_from_docx(self, filepath: str) -> str:
        """Извлечение текста из DOCX"""
        try:
            doc = Document(filepath)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text
        except Exception as e:
            logger.error(f"❌ Ошибка чтения DOCX {filepath}: {e}")
            return ""
    
    def get_file_hash(self, filepath: str) -> str:
        """Вычисление хеша файла"""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"❌ Ошибка вычисления хеша {filepath}: {e}")
            return ""
    
    def document_exists(self, filename: str, file_hash: str) -> bool:
        """Проверка существования документа в БД"""
        try:
            # Правильный формат фильтра для ChromaDB
            results = self.collection.get(
                where={"filename": {"$eq": filename}},
                limit=1
            )
            
            if results['ids']:
                # Проверяем хеш первого чанка
                first_metadata = results['metadatas'][0]
                if 'file_hash' in first_metadata and first_metadata['file_hash'] == file_hash:
                    return True
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки документа {filename}: {e}")
            return False
    
    def smart_chunking(self, text: str, filename: str) -> List[DocumentChunk]:
        """Умное чанкование с учетом структуры документа"""
        # Очистка текста
        text = re.sub(r'\s+', ' ', text).strip()
        
        if not text:
            return []
        
        chunks = []
        chunk_size = self.config["chunk_size"]
        overlap = self.config["chunk_overlap"]
        
        # Простое чанкование с перекрытием (упрощенная версия)
        for i in range(0, len(text), chunk_size - overlap):
            chunk_text = text[i:i + chunk_size]
            if len(chunk_text) > 100:  # Минимальный размер чанка
                chunks.append(DocumentChunk(
                    text=chunk_text,
                    metadata={
                        'filename': filename,
                        'chunk_id': len(chunks),
                        'start_char': i,
                        'end_char': i + len(chunk_text)
                    }
                ))
        
        return chunks
    
    def load_all_documents(self):
        """Загрузка документов с проверкой изменений"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            logger.info(f"📁 Создана директория {self.data_dir}")
            return
        
        supported_extensions = ['.txt', '.pdf', '.docx']
        files = []
        
        for ext in supported_extensions:
            files.extend([f for f in os.listdir(self.data_dir) if f.lower().endswith(ext)])
        
        logger.info(f"📚 Найдено {len(files)} документов")
        
        total_loaded = 0
        for filename in files:
            if self.process_document(filename):
                total_loaded += 1
        
        logger.info(f"🎯 Успешно обработано {total_loaded} документов")
    
    def process_document(self, filename: str) -> bool:
        """Обработка одного документа"""
        filepath = os.path.join(self.data_dir, filename)
        
        if not os.path.exists(filepath):
            logger.warning(f"⚠️ Файл {filename} не существует")
            return False
        
        # Проверка хеша для избежания повторной обработки
        file_hash = self.get_file_hash(filepath)
        if not file_hash:
            return False
        
        if self.document_exists(filename, file_hash):
            logger.info(f"📄 Документ {filename} уже обработан")
            return True
        
        try:
            # Извлечение текста
            text = ""
            if filename.lower().endswith('.txt'):
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
            elif filename.lower().endswith('.pdf'):
                text = self.extract_text_from_pdf(filepath)
            elif filename.lower().endswith('.docx'):
                text = self.extract_text_from_docx(filepath)
            
            if not text:
                logger.warning(f"⚠️ Не удалось извлечь текст из {filename}")
                return False
            
            # Чанкование
            chunks = self.smart_chunking(text, filename)
            if not chunks:
                logger.warning(f"⚠️ Не удалось разбить на чанки {filename}")
                return False
            
            # Добавление в векторную БД
            self.add_chunks_to_db(chunks, filename, file_hash)
            logger.info(f"✅ {filename} - {len(chunks)} чанков")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки {filename}: {e}")
            return False
    
    def add_chunks_to_db(self, chunks: List[DocumentChunk], filename: str, file_hash: str):
        """Добавление чанков в БД"""
        texts = [chunk.text for chunk in chunks]
        
        try:
            embeddings = self.embedding_model.encode(texts).tolist()
        except Exception as e:
            logger.error(f"❌ Ошибка создания эмбеддингов для {filename}: {e}")
            return
        
        # Подготовка метаданных
        metadatas = []
        ids = []
        
        for i, chunk in enumerate(chunks):
            metadata = chunk.metadata.copy()
            metadata.update({
                'file_hash': file_hash,
                'timestamp': datetime.now().isoformat()
            })
            metadatas.append(metadata)
            ids.append(f"{filename}_{i}_{hashlib.md5(chunk.text.encode()).hexdigest()[:8]}")
        
        try:
            self.collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
        except Exception as e:
            logger.error(f"❌ Ошибка добавления в БД: {e}")
    
    def semantic_search(self, query: str, n_results: int = 3) -> List[Tuple[str, Dict]]:
        """Семантический поиск по базе документов"""
        try:
            query_embedding = self.embedding_model.encode([query]).tolist()
            
            results = self.collection.query(
                query_embeddings=query_embedding,
                n_results=n_results
            )
            
            # Форматирование результатов
            formatted_results = []
            for i, (doc, metadata) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
                formatted_results.append((doc, metadata))
            
            return formatted_results
        except Exception as e:
            logger.error(f"❌ Ошибка поиска: {e}")
            return []
    
    def ask_question(self, question: str) -> Dict:
        """Ответ на вопрос с цитированием источников"""
        start_time = time.time()
        
        # Поиск релевантных документов
        search_results = self.semantic_search(question, n_results=3)
        
        if not search_results:
            return {
                "answer": "Не найдено релевантной информации в документах.",
                "sources": [],
                "response_time": time.time() - start_time
            }
        
        # Подготовка контекста
        context_parts = []
        sources = []
        
        for i, (text, metadata) in enumerate(search_results):
            context_parts.append(f"[Документ {i+1}: {metadata['filename']}]\n{text}")
            sources.append({
                "filename": metadata['filename'],
                "chunk_id": metadata['chunk_id'],
                "text_excerpt": text[:200] + "..."
            })
        
        context = "\n\n".join(context_parts)
        
        # Генерация ответа
        prompt = f"""На основе приведенных документов ответь на вопрос. Будь точным и цитируй документы.

Документы:
{context}

Вопрос: {question}

Требования:
1. Ответь строго на основе документов
2. Укажи номера документов в ответе
3. Если информации нет - сообщи об этом
4. Будь лаконичным

Ответ:"""
        
        try:
            llm_provider = self.config["llm_provider"]
            
            if llm_provider == "local":
                answer = self.llm_client.generate(prompt, max_tokens=300, temp=0.1)
            else:
                answer = self.generate_with_online_model(prompt, max_tokens=300, temperature=0.1)
            
            return {
                "answer": answer.strip(),
                "sources": sources,
                "response_time": time.time() - start_time
            }
            
        except Exception as e:
            return {
                "answer": f"Ошибка генерации ответа: {e}",
                "sources": [],
                "response_time": time.time() - start_time
            }
    
    def load_templates(self):
        """Загрузка шаблонов документов"""
        templates_dir = "templates"
        if not os.path.exists(templates_dir):
            os.makedirs(templates_dir)
            # Создание базовых шаблонов
            self.create_default_templates(templates_dir)
        
        template_files = [f for f in os.listdir(templates_dir) if f.endswith('.json')]
        
        for template_file in template_files:
            filepath = os.path.join(templates_dir, template_file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    template_name = template_file.replace('.json', '')
                    self.templates[template_name] = json.load(f)
            except Exception as e:
                logger.warning(f"⚠️ Ошибка загрузки шаблона {template_file}: {e}")
        
        logger.info(f"📋 Загружено {len(self.templates)} шаблонов")
    
    def create_default_templates(self, templates_dir):
        """Создание базовых шаблонов"""
        # Шаблон Технического задания
        tz_template = {
            "name": "Техническое задание",
            "sections": [
                {"name": "Общие положения", "fields": ["наименование", "основание", "цели"]},
                {"name": "Технические требования", "fields": ["требования", "стандарты", "сроки"]},
                {"name": "Порядок приемки", "fields": ["процедура", "критерии", "документы"]}
            ],
            "prompt": "Сгенерируй техническое задание на основе следующих требований: {context}"
        }
        
        try:
            with open(os.path.join(templates_dir, "ТЗ.json"), 'w', encoding='utf-8') as f:
                json.dump(tz_template, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка создания шаблона ТЗ: {e}")
    
    def generate_document(self, doc_type: str, requirements: str) -> Dict:
        """Генерация документа по шаблону"""
        if doc_type not in self.templates:
            return {"error": f"Шаблон {doc_type} не найден"}
        
        template = self.templates[doc_type]
        
        # Поиск релевантной информации
        search_results = self.semantic_search(requirements, n_results=2)
        context = " ".join([text for text, _ in search_results])
        
        # Генерация промпта
        prompt = template["prompt"].format(context=context, requirements=requirements)
        
        try:
            llm_provider = self.config["llm_provider"]
            
            if llm_provider == "local":
                generated_content = self.llm_client.generate(prompt, max_tokens=500, temp=0.2)
            else:
                generated_content = self.generate_with_online_model(prompt, max_tokens=500, temperature=0.2)
            
            return {
                "document_type": doc_type,
                "content": generated_content.strip(),
                "sections": template["sections"],
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Ошибка генерации: {e}"}
    
    def interactive_mode(self):
        """Интерактивный режим работы"""
        print("\n" + "="*60)
        print("🤖 AI-ассистент ЛПА/ЛНПА готов к работе!")
        print(f"📡 Режим: {self.config['llm_provider']}")
        print("Команды:")
        print("  /вопрос [текст] - задать вопрос")
        print("  /генерация [тип] [требования] - создать документ")
        print("  /шаблоны - список доступных шаблонов")
        print("  /статус - информация о системе")
        print("  /выход - завершить работу")
        print("="*60)
        
        while True:
            try:
                user_input = input("\n🎯 Введите команду: ").strip()
                
                if user_input.lower() in ['/выход', '/exit']:
                    break
                
                elif user_input.startswith('/вопрос '):
                    question = user_input[8:].strip()
                    if question:
                        result = self.ask_question(question)
                        print(f"\n🤖 Ответ ({result['response_time']:.1f}сек):")
                        print(result['answer'])
                        if result['sources']:
                            print("\n📚 Источники:")
                            for source in result['sources']:
                                print(f"   - {source['filename']} (фрагмент {source['chunk_id']})")
                
                elif user_input.startswith('/генерация '):
                    parts = user_input[11:].split(' ', 1)
                    if len(parts) == 2:
                        doc_type, requirements = parts
                        result = self.generate_document(doc_type, requirements)
                        if 'error' not in result:
                            print(f"\n📄 Сгенерирован документ: {result['document_type']}")
                            print(result['content'])
                        else:
                            print(f"❌ {result['error']}")
                    else:
                        print("❌ Использование: /генерация [тип] [требования]")
                
                elif user_input == '/шаблоны':
                    print("\n📋 Доступные шаблоны:")
                    for template in self.templates.keys():
                        print(f"   - {template}")
                
                elif user_input == '/статус':
                    try:
                        count = self.collection.count()
                        print(f"\n📊 Статус системы:")
                        print(f"   Документов в базе: {count}")
                        print(f"   Загружено шаблонов: {len(self.templates)}")
                        print(f"   Провайдер LLM: {self.config['llm_provider']}")
                    except Exception as e:
                        print(f"❌ Ошибка получения статуса: {e}")
                
                else:
                    print("❌ Неизвестная команда")
                    
            except KeyboardInterrupt:
                print("\n👋 Завершение работы...")
                break
            except Exception as e:
                print(f"❌ Ошибка: {e}")

def main():
    """Основная функция"""
    try:
        assistant = EnhancedLNPAssistant()
        assistant.interactive_mode()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())