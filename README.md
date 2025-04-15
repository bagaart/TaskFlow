# TaskFlow

## Технологии
- Python (Flask)
- SQLAlchemy (PostgreSQL)
- Flask-Login для аутентификации
- HTML/CSS/JavaScript

## Установка и запуск

1. **Клонирование репозитория:**
   ```bash
   git clone https://github.com/bagaart/TaskFlow.git
   cd TaskFlow
   ```
2. **Создание виртуального окружения (рекомендуется):**
   ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/Mac
    venv\Scripts\activate     # Windows
   ```

3. **Установка зависимостей:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Настройка базы данных (PostgreSQL):**
   - Убедитесь, что PostgreSQL установлен и запущен.
   - Создайте базу данных taskflow_db.
   - Измените параметры подключения в config.py при необходимости.

5. **Запуск приложения:**
   ```bash
   python run.py
   ```

6. **Доступ к приложению:**
   - По умолчанию, приложение будет доступно по адресу http://localhost:5000.

## Структура проекта
    ```
    TaskFlow
    ├─ app
    │  ├─ forms.py
    │  ├─ models.py
    │  ├─ routes.py
    │  ├─ static
    │  │  ├─ scripts
    │  │  │  └─ auth.js
    │  │  └─ styles
    │  │     ├─ auth.css
    │  │     └─ main.css
    │  ├─ templates
    │  │  ├─ auth.html
    │  │  ├─ main.html
    │  │  └─ main.html~
    │  └─ __init__.py
    ├─ config.py
    ├─ README.md
    └─ run.py
    ```
## Лицензия

MIT License
