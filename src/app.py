from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import sys
import json
import tempfile
from datetime import datetime

# Добавляем текущую директорию в путь для импорта нашего основного кода
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Импортируем наш основной код
from finr import AIAssistant, get_document_data, get_doc_full_name

app = Flask(__name__template_folder='.')
CORS(app)

# Глобальная переменная для ассистента
assistant = None

def initialize_assistant():
    """Инициализация AI ассистента"""
    global assistant
    try:
        assistant = AIAssistant()
        # Попытка загрузить существующую базу знаний
        try:
            assistant.setup_knowledge_base("./documents")
            print("✅ База знаний загружена успешно")
        except Exception as e:
            print(f"⚠️ Не удалось загрузить базу знаний: {e}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка инициализации ассистента: {e}")
        return False

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Статус системы"""
    if not assistant:
        return jsonify({
            'status': 'error',
            'message': 'Ассистент не инициализирован'
        })
    
    try:
        stats = assistant.get_statistics()
        return jsonify({
            'status': 'success',
            'data': {
                'assistant_ready': True,
                'documents_count': stats['total_documents'],
                'llm_available': stats['has_llm'],
                'docx_available': stats['docx_available'],
                'index_built': stats['has_embeddings']
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route('/api/ask', methods=['POST'])
def ask_question():
    """Обработка вопросов"""
    if not assistant:
        return jsonify({
            'status': 'error',
            'message': 'Ассистент не инициализирован'
        })
    
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        use_llm = data.get('use_llm', False)
        
        if not question:
            return jsonify({
                'status': 'error',
                'message': 'Вопрос не может быть пустым'
            })
        
        # Получаем ответ от ассистента
        result = assistant.ask(question, use_llm=use_llm)
        
        return jsonify({
            'status': 'success',
            'data': {
                'answer': result['answer'],
                'sources': result['sources'],
                'confidence': result['confidence'],
                'timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка обработки вопроса: {str(e)}'
        })

@app.route('/api/search', methods=['POST'])
def search_documents():
    """Поиск по документам"""
    if not assistant:
        return jsonify({
            'status': 'error',
            'message': 'Ассистент не инициализирован'
        })
    
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        method = data.get('method', 'combined')
        top_k = data.get('top_k', 5)
        
        if not query:
            return jsonify({
                'status': 'error',
                'message': 'Поисковый запрос не может быть пустым'
            })
        
        results = assistant.kb.search(query, top_k=top_k, method=method)
        
        formatted_results = []
        for result in results:
            formatted_results.append({
                'question': result['question'],
                'answer': result['answer'][:200] + '...' if len(result['answer']) > 200 else result['answer'],
                'document': result.get('document', ''),
                'link': result.get('link', ''),
                'similarity_score': result['similarity_score'],
                'source_file': result.get('source_file', '')
            })
        
        return jsonify({
            'status': 'success',
            'data': {
                'results': formatted_results,
                'count': len(results),
                'query': query
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка поиска: {str(e)}'
        })

@app.route('/api/generate-document', methods=['POST'])
def generate_document():
    """Генерация документа"""
    if not assistant:
        return jsonify({
            'status': 'error',
            'message': 'Ассистент не инициализирован'
        })
    
    try:
        data = request.get_json()
        doc_type = data.get('doc_type', '').upper()
        document_data = data.get('data', {})
        format_type = data.get('format', 'txt')
        
        if doc_type not in ['ТЗ', 'ЗНЗ', 'КП']:
            return jsonify({
                'status': 'error',
                'message': 'Неверный тип документа. Допустимые значения: ТЗ, ЗНЗ, КП'
            })
        
        # Дополняем данные стандартными значениями
        if not document_data:
            document_data = get_document_data(doc_type)
        else:
            # Добавляем обязательные поля, если их нет
            default_data = get_document_data(doc_type)
            for key, value in default_data.items():
                if key not in document_data:
                    document_data[key] = value
        
        # Генерируем документ
        if format_type == 'docx' and assistant.generator.document:
            result = assistant.generator.create_document(doc_type, document_data)
            filename = f"{doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
            
            # Сохраняем временный файл
            temp_dir = tempfile.gettempdir()
            filepath = os.path.join(temp_dir, filename)
            assistant.generator.save_document(filepath)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'message': 'Документ успешно создан',
                    'filename': filename,
                    'filepath': filepath,
                    'format': 'docx',
                    'download_url': f'/api/download/{filename}'
                }
            })
        else:
            # Текстовый формат
            context = {
                'subject': document_data.get('title', ''),
                'general_provisions': '\n'.join(document_data.get('general_requirements', [])),
                'requirements': '\n'.join(document_data.get('technical_specifications', [])),
                'timeline': document_data.get('delivery_terms', [''])[0],
                'responsibility': document_data.get('participant_requirements', [''])[0]
            }
            
            if doc_type == 'ТЗ':
                doc_text = assistant.generator._create_text_document('tz', context)
            elif doc_type == 'ЗНЗ':
                doc_text = assistant.generator._create_text_document('znz', context)
            else:  # КП
                doc_text = assistant.generator._create_text_document('kp', context)
            
            return jsonify({
                'status': 'success',
                'data': {
                    'content': doc_text,
                    'format': 'txt',
                    'filename': f"{doc_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                }
            })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка генерации документа: {str(e)}'
        })

@app.route('/api/download/<filename>')
def download_file(filename):
    """Скачивание сгенерированного файла"""
    try:
        temp_dir = tempfile.gettempdir()
        filepath = os.path.join(temp_dir, filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                'status': 'error',
                'message': 'Файл не найден'
            }), 404
        
        from flask import send_file
        return send_file(filepath, as_attachment=True)
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка загрузки файла: {str(e)}'
        }), 500

@app.route('/api/upload-documents', methods=['POST'])
def upload_documents():
    """Загрузка документов в базу знаний"""
    if not assistant:
        return jsonify({
            'status': 'error',
            'message': 'Ассистент не инициализирован'
        })
    
    try:
        if 'files' not in request.files:
            return jsonify({
                'status': 'error',
                'message': 'Файлы не предоставлены'
            })
        
        files = request.files.getlist('files')
        uploaded_files = []
        
        # Создаем временную папку для загрузки
        upload_dir = os.path.join(tempfile.gettempdir(), 'ai_assistant_uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        for file in files:
            if file.filename == '':
                continue
            
            if file.filename.endswith('.txt'):
                filename = os.path.join(upload_dir, file.filename)
                file.save(filename)
                uploaded_files.append(filename)
        
        # Добавляем документы в базу знаний
        for filepath in uploaded_files:
            assistant.kb.add_document_from_file(filepath)
        
        # Перестраиваем индекс
        assistant.kb.build_index()
        
        return jsonify({
            'status': 'success',
            'data': {
                'message': f'Загружено {len(uploaded_files)} документов',
                'files': [os.path.basename(f) for f in uploaded_files],
                'total_documents': len(assistant.kb.documents)
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Ошибка загрузки документов: {str(e)}'
        })

if __name__ == '__main__':
    print("🚀 Запуск AI Assistant Web Server...")
    
    # Инициализируем ассистента
    if initialize_assistant():
        print("✅ AI Assistant инициализирован успешно")
    else:
        print("❌ Не удалось инициализировать AI Assistant")
    
    # Запускаем сервер
    app.run(debug=True, host='0.0.0.0', port=5000)