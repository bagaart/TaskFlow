# app/routes.py
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import render_template, redirect, url_for, flash, Blueprint, request, abort, current_app, send_from_directory
from flask_login import current_user, login_user, login_required, logout_user

from app.forms import RegisterForm, LoginForm
from app.models import User, db, ProjectUser, Project, Task, TaskExecutor, Comment, Report
from flask import jsonify
from datetime import datetime

from fpdf import FPDF
from datetime import datetime
import tempfile
bp = Blueprint('taskflow', __name__)


@bp.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('taskflow.auth'))

    # Получаем задачи, где пользователь исполнитель или менеджер
    executor_tasks = Task.query.join(TaskExecutor).filter(TaskExecutor.user_id == current_user.id).all()
    manager_tasks = Task.query.filter_by(manager_id=current_user.id).all()

    # Получаем проекты пользователя
    user_projects = current_user.projects

    return render_template(
        'main.html',
        executor_tasks=executor_tasks,
        manager_tasks=manager_tasks,
        user_projects=user_projects
    )

@bp.route('/auth', methods=['GET', 'POST'])
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('taskflow.index'))

    login_form = LoginForm()
    register_form = RegisterForm()

    if login_form.validate_on_submit():
        email = login_form.email.data
        password = login_form.password.data
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user)
            flash('Login successful', 'success')
            return redirect(url_for('taskflow.index'))
        else:
            flash('Invalid email or password', 'danger')

    if register_form.validate_on_submit():
        email = register_form.email.data
        password = register_form.password.data
        name = register_form.name.data

        user = User.query.filter_by(email=email).first()
        if user:
            flash('User already exists', 'danger')
        else:
            new_user = User(name=name, email=email)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful', 'success')
            return redirect(url_for('taskflow.index'))

    return render_template('auth.html', login_form=login_form, register_form=register_form)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('taskflow.auth'))

@bp.route('/create_task', methods=['GET', 'POST'])
@login_required
def create_task():
    if request.method == 'POST':
        project_id = request.form.get('project')
        title = request.form.get('task-name')
        executor_ids = request.form.getlist('executors')
        deadline_str = request.form.get('deadline')
        description = request.form.get('description')

        if not project_id or not title or not executor_ids or not deadline_str:
            flash('Все обязательные поля должны быть заполнены.', 'danger')
            return redirect(url_for('taskflow.create_task'))

        deadline = datetime.strptime(deadline_str, '%Y-%m-%d')

        if deadline.date() < datetime.today().date():
            flash('Срок выполнения не может быть в прошлом.', 'danger')
            return redirect(url_for('taskflow.create_task'))

        task = Task(
            title=title,
            description=description,
            deadline=deadline,
            project_id=project_id,
            manager_id=current_user.id
        )
        db.session.add(task)

        # Устанавливаем исполнителей
        for executor_id in executor_ids:
            executor = User.query.get(executor_id)
            if executor:
                task_executor = TaskExecutor(task_id=task.id, user_id=executor_id)
                db.session.add(task_executor)

        db.session.commit()
        flash('Задача успешно создана!', 'success')
        return redirect(url_for('taskflow.index'))

    # Для GET-запроса: передаем только те проекты, где пользователь участник
    user_projects = current_user.projects
    return render_template('task_create.html', user_projects=user_projects)


@bp.route('/create_project', methods=['GET', 'POST'])
@login_required
def create_project():
    if request.method == 'POST':
        name = request.form.get('project-name')
        description = request.form.get('project-description')
        deadline_str = request.form.get('project-deadline')
        participant_ids = request.form.getlist('participants')
        manager_id = request.form.get('manager')
        analyst_id = request.form.get('analyst')

        if str(current_user.id) not in participant_ids:
            participant_ids.append(str(current_user.id))

        # Валидация обязательных полей
        if not name:
            flash('Название проекта обязательно.', 'danger')
            return redirect(url_for('taskflow.create_project'))

        if not participant_ids:
            flash('Добавьте хотя бы одного участника.', 'danger')
            return redirect(url_for('taskflow.create_project'))

        if not manager_id:
            manager_id = str(current_user.id)

        # Обработка дедлайна
        deadline = None
        if deadline_str:
            try:
                deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
                if deadline.date() < datetime.today().date():
                    flash('Дедлайн не может быть в прошлом.', 'danger')
                    return redirect(url_for('taskflow.create_project'))
            except ValueError:
                flash('Некорректный формат даты.', 'danger')
                return redirect(url_for('taskflow.create_project'))

        # Создаем проект
        project = Project(
            name=name,
            description=description,
            deadline=deadline
        )
        db.session.add(project)
        db.session.flush()  # Получаем ID проекта до коммита

        # Добавляем участников с ролями
        for user_id in set(participant_ids):
            role = 'member'
            if user_id == manager_id:
                role = 'manager'
            elif user_id == analyst_id:
                role = 'analyst'

            project_user = ProjectUser(
                project_id=project.id,
                user_id=user_id,
                role=role
            )
            db.session.add(project_user)

        db.session.commit()
        flash('Проект успешно создан!', 'success')
        return redirect(url_for('taskflow.projects'))

    users = User.query.all()
    return render_template('project_create.html', users=users)



@bp.route('/api/project/<int:id>/participants')
@login_required
def get_project_participants(id):
    project = Project.query.get_or_404(id)
    # Проверяем, что текущий пользователь — участник проекта
    is_member = any(assoc.user_id == current_user.id for assoc in project.user_associations)
    if not is_member:
        return jsonify({'error': 'Доступ запрещён'}), 403

    participants = [{'id': user.id, 'name': user.name} for user in project.users]
    return jsonify({'participants': participants})


@bp.route('/projects')
@login_required
def projects():
    # Получаем параметр сортировки из запроса
    sort_by = request.args.get('sort', 'created')

    # Копируем список проектов
    user_projects = list(current_user.projects)

    # Сортируем в Python
    if sort_by == 'deadline':
        user_projects.sort(key=lambda p: p.deadline or datetime.max)
    elif sort_by == 'name':
        user_projects.sort(key=lambda p: p.name)
    else:  # по умолчанию сортируем по дате создания (новые сначала)
        user_projects.sort(key=lambda p: p.created_at, reverse=True)

    return render_template('projects.html', user_projects=user_projects)


@bp.route('/api/project/<int:id>/participants_with_roles')
@login_required
def get_project_participants_with_roles(id):
    project = Project.query.get_or_404(id)

    # Проверяем, что текущий пользователь — участник проекта
    is_member = any(assoc.user_id == current_user.id for assoc in project.user_associations)
    if not is_member:
        return jsonify({'error': 'Доступ запрещён'}), 403

    # Получаем информацию об участниках с ролями
    participants = []
    for assoc in project.user_associations:
        user = User.query.get(assoc.user_id)
        participants.append({
            'id': user.id,
            'name': user.name,
            'email': user.email,
            'role': assoc.role
        })

    return jsonify({
        'participants': participants,
        'total': len(participants)
    })


@bp.route('/api/project/<int:id>/stats')
@login_required
def get_project_stats(id):
    project = Project.query.get_or_404(id)

    # Проверка прав доступа
    if not any(assoc.user_id == current_user.id for assoc in project.user_associations):
        return jsonify({'error': 'Доступ запрещён'}), 403

    return jsonify({
        'total_tasks': len(project.tasks),
        'tasks_by_status': {
            'todo': len([t for t in project.tasks if t.status == 'To Do']),
            'in_progress': len([t for t in project.tasks if t.status == 'In Progress']),
            'done': len([t for t in project.tasks if t.status == 'Done'])
        }
    })


@bp.route('/tasks')
@login_required
def tasks():
    # Получаем задачи, где пользователь исполнитель или менеджер
    executor_tasks = Task.query.join(TaskExecutor).filter(TaskExecutor.user_id == current_user.id).all()
    manager_tasks = Task.query.filter_by(manager_id=current_user.id).all()

    # Объединяем и убираем дубликаты
    all_tasks = list(set(executor_tasks + manager_tasks))

    # Получаем проекты пользователя для фильтра
    user_projects = current_user.projects

    # Передаем текущую дату в шаблон
    return render_template('tasks.html', tasks=all_tasks, user_projects=user_projects, datetime=datetime)


@bp.route('/api/task/<int:id>/people')
@login_required
def get_task_people(id):
    task = Task.query.get_or_404(id)

    # Проверка прав доступа
    is_executor = any(executor.user_id == current_user.id for executor in task.executors_link)
    is_manager = task.manager_id == current_user.id

    if not (is_executor or is_manager):
        return jsonify({'error': 'Доступ запрещён'}), 403

    # Получаем менеджера
    manager = None
    if task.manager_id:
        manager_user = User.query.get(task.manager_id)
        manager = {
            'id': manager_user.id,
            'name': manager_user.name,
            'email': manager_user.email
        }

    # Получаем исполнителей
    executors = []
    for executor in task.executors:
        executors.append({
            'id': executor.id,
            'name': executor.name,
            'email': executor.email
        })

    return jsonify({
        'manager': manager,
        'executors': executors
    })


@bp.route('/board/<int:project_id>')
@login_required
def board(project_id):
    project = Project.query.get_or_404(project_id)

    # Проверка, что пользователь имеет доступ к проекту
    if not any(p.id == project_id for p in current_user.projects):
        return abort(403)

    # Группируем задачи по статусам
    tasks_by_status = {
        'todo': [t for t in project.tasks if t.status == 'To Do'],
        'in_progress': [t for t in project.tasks if t.status == 'In Progress'],
        'done': [t for t in project.tasks if t.status == 'Done']
    }

    # Добавляем информацию о днях до дедлайна
    for status, tasks in tasks_by_status.items():
        for task in tasks:
            if task.deadline:
                task.days_remaining = (task.deadline.date() - datetime.now().date()).days
            else:
                task.days_remaining = float('inf')

    return render_template('board.html', project=project, tasks_by_status=tasks_by_status)


@bp.route('/api/task/<int:id>', methods=['GET'])
@login_required
def get_task_2(id):
    task = Task.query.get_or_404(id)

    # Проверка прав доступа
    if not any(p.id == task.project_id for p in current_user.projects):
        abort(403)

    return jsonify({
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'priority': task.priority,
        'deadline': task.deadline.isoformat() if task.deadline else None,
        'status': task.status,
        'project_id': task.project_id,
        'project': {
            'id': task.project.id,
            'name': task.project.name
        } if task.project else None,
        'executors': [{'id': e.id, 'name': e.name} for e in task.executors],
        'created_at': task.created_at.isoformat() if task.created_at else None
    })


@bp.route('/api/task/<int:id>', methods=['PUT'])
@login_required
def update_task_2(id):
    task = Task.query.get_or_404(id)

    # Проверка прав доступа
    if not any(p.id == task.project_id for p in current_user.projects):
        abort(403)

    data = request.get_json()

    # Обновляем данные задачи
    task.title = data.get('title', task.title)
    task.description = data.get('description', task.description)
    task.priority = data.get('priority', task.priority).capitalize()

    if data.get('deadline'):
        task.deadline = datetime.fromisoformat(data['deadline'])
    elif 'deadline' in data and data['deadline'] is None:
        task.deadline = None

    # Обновляем статус, если он изменился
    new_status = data.get('status')
    if new_status and new_status != task.status:
        task.status = new_status

    db.session.commit()

    return jsonify({
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'priority': task.priority,
        'deadline': task.deadline.isoformat() if task.deadline else None,
        'status': task.status
    })


@bp.route('/api/task/<int:id>', methods=['DELETE'])
@login_required
def delete_task(id):
    task = Task.query.get_or_404(id)

    # Проверяем, является ли текущий пользователь менеджером проекта
    project_user = ProjectUser.query.filter_by(
        project_id=task.project_id,
        user_id=current_user.id
    ).first()

    # Если пользователь не менеджер проекта - запрещаем доступ
    if not project_user or project_user.role != 'manager':
        abort(403, description="Только менеджер проекта может удалять задачи")

    db.session.delete(task)
    db.session.commit()

    return jsonify({'success': True})


@bp.route('/api/task/<int:id>/status', methods=['POST'])
@login_required
def update_task_status(id):
    task = Task.query.get_or_404(id)

    # Проверка прав доступа
    if not any(p.id == task.project_id for p in current_user.projects):
        abort(403)

    data = request.get_json()
    new_status = data.get('status')

    if new_status not in ['To Do', 'In Progress', 'Done']:
        return jsonify({'error': 'Недопустимый статус'}), 400

    task.status = new_status
    db.session.commit()

    return jsonify({'success': True, 'new_status': new_status})


@bp.route('/task/<int:id>')
@login_required
def task_details(id):
    # Получаем задачу по ID
    task = Task.query.get_or_404(id)

    # Проверяем, что текущий пользователь имеет доступ к задаче
    # (является исполнителем, менеджером или участником проекта)
    is_executor = any(executor.user_id == current_user.id for executor in task.executors_link)
    is_manager = task.manager_id == current_user.id
    is_project_member = any(pu.user_id == current_user.id for pu in task.project.user_associations)

    if not (is_executor or is_manager or is_project_member):
        abort(403)

    # Форматируем даты для шаблона
    created_at = task.created_at.strftime('%d.%m.%Y %H:%M') if task.created_at else None
    deadline = task.deadline.strftime('%d.%m.%Y') if task.deadline else None

    # Рассчитываем дни до дедлайна
    days_remaining = None
    if task.deadline:
        delta = task.deadline.date() - datetime.now().date()
        days_remaining = delta.days

    # Получаем информацию о менеджере
    manager = User.query.get(task.manager_id) if task.manager_id else None

    # Получаем список исполнителей
    executors = task.executors

    return render_template(
        'task_details.html',
        task=task,
        created_at=created_at,
        deadline=deadline,
        days_remaining=days_remaining,
        manager=manager,
        executors=executors,
        current_user=current_user
    )


# Добавим эти endpoint'ы в routes.py

@bp.route('/api/task/<int:task_id>/comments', methods=['GET'])
@login_required
def get_task_comments(task_id):
    task = Task.query.get_or_404(task_id)

    # Проверка прав доступа
    if not any(p.id == task.project_id for p in current_user.projects):
        abort(403)

    # Получаем комментарии для задачи
    comments = []
    for comment in task.comments:
        comments.append({
            'id': comment.id,
            'content': comment.content,
            'timestamp': comment.timestamp.strftime('%d.%m.%Y %H:%M'),
            'author': {
                'id': comment.author.id,
                'name': comment.author.name,
                'email': comment.author.email
            }
        })

    return jsonify({'comments': comments})


@bp.route('/api/task/<int:task_id>/comments', methods=['POST'])
@login_required
def add_task_comment(task_id):
    task = Task.query.get_or_404(task_id)

    # Проверка прав доступа
    if not any(p.id == task.project_id for p in current_user.projects):
        abort(403)

    data = request.get_json()
    content = data.get('content')

    if not content:
        return jsonify({'error': 'Текст комментария не может быть пустым'}), 400

    # Создаем новый комментарий
    new_comment = Comment(
        content=content,
        author_id=current_user.id,
        task_id=task_id
    )

    db.session.add(new_comment)
    db.session.commit()

    return jsonify({
        'id': new_comment.id,
        'content': new_comment.content,
        'timestamp': new_comment.timestamp.strftime('%d.%m.%Y %H:%M'),
        'author': {
            'id': current_user.id,
            'name': current_user.name,
            'email': current_user.email
        }
    }), 201


@bp.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        abort(403)
    return render_template('admin_panel.html')


@bp.route('/admin/create_backup', methods=['POST'])
@login_required
def create_backup():
    if not current_user.is_admin:
        abort(403)

    data = request.get_json()
    backup_dir = data.get('path')
    backup_name = data.get('name')

    if not backup_dir or not backup_name:
        return jsonify({'error': 'Не указаны путь или имя резервной копии'}), 400

    try:
        # Нормализуем путь для Windows
        backup_dir = os.path.normpath(backup_dir)

        # Создаем папку для резервных копий, если её нет
        Path(backup_dir).mkdir(parents=True, exist_ok=True)
        test_file = os.path.join(backup_dir, '.write_test')
        try:
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except PermissionError:
            return "Нет прав на запись в указанную папку", 403

        # Формируем имя файла с датой
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"{backup_name}_{timestamp}.sql"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Получаем параметры подключения из конфига Flask
        db_uri = current_app.config['SQLALCHEMY_DATABASE_URI']

        # Парсим параметры подключения
        from urllib.parse import urlparse
        parsed = urlparse(db_uri)

        db_name = parsed.path[1:]  # убираем первый слэш
        db_user = parsed.username
        db_password = parsed.password
        db_host = parsed.hostname
        db_port = parsed.port or 5432  # стандартный порт PostgreSQL

        # Формируем команду pg_dump
        pg_dump_cmd = [
            r"C:\Program Files\PostgreSQL\16\bin\pg_dump.exe",
            '-h', db_host,
            '-p', str(db_port),
            '-U', db_user,
            '-d', db_name,
            '-f', backup_path
        ]

        # Устанавливаем переменную окружения с паролем
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password

        # Выполняем команду
        subprocess.run(pg_dump_cmd, env=env, check=True)

        # Логируем действие
        report = Report(
            timestamp=datetime.now(),
            backup_path=backup_path,
            description=f"Резервная копия создана администратором {current_user.name}"
        )
        db.session.add(report)
        db.session.commit()

        return jsonify({
            'success': True,
            'file_path': backup_path
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            'error': f'Ошибка при создании SQL-дампа: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'error': f'Ошибка при создании резервной копии: {str(e)}'
        }), 500


@bp.route('/admin/reports')
@login_required
def reports_dashboard():
    if not current_user.is_admin:
        abort(403)

    reports = Report.query.order_by(Report.timestamp.desc()).limit(50).all()
    return render_template('reports_dashboard.html', reports=reports)


@bp.route('/admin/generate_report', methods=['POST'])
@login_required
def generate_report():
    if not current_user.is_admin:
        abort(403)

    data = request.get_json()
    report_type = data.get('type')
    format_type = data.get('format', 'json')  # Добавляем параметр формата
    parameters = data.get('parameters', {})

    if not report_type:
        return jsonify({'error': 'Не указан тип отчета'}), 400

    try:
        # Создаем запись о отчете
        report = Report(
            report_type=report_type,
            format=format_type,  # Сохраняем формат отчета
            parameters=parameters,
            generator_id=current_user.id,
            status='pending'
        )
        db.session.add(report)
        db.session.commit()

        # Запускаем генерацию отчета в фоне
        generate_report_background(report.id)

        return jsonify({
            'success': True,
            'report_id': report.id
        })

    except Exception as e:
        return jsonify({
            'error': f'Ошибка при создании отчета: {str(e)}'
        }), 500


def generate_report_background(report_id):
    from app import create_app
    app = create_app()

    with app.app_context():
        report = Report.query.get(report_id)
        if not report:
            return

        try:
            # Создаем директорию для отчетов, если ее нет
            reports_dir = os.path.join(app.instance_path, 'reports')
            os.makedirs(reports_dir, exist_ok=True)

            filename = f"{report.report_type}_{report.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            if report.report_type == 'tasks':
                # Генерация отчета по задачам
                tasks = Task.query.all()
                report_data = [{
                    'id': t.id,
                    'title': t.title,
                    'status': t.status,
                    'project': t.project.name if t.project else None,
                    'created_at': t.created_at.strftime('%d.%m.%Y %H:%M') if t.created_at else None,
                    'deadline': t.deadline.strftime('%d.%m.%Y') if t.deadline else None,
                    'manager': t.manager.name if t.manager else None,
                    'executors': ', '.join([e.name for e in t.executors])
                } for t in tasks]

                if report.format == 'pdf':
                    file_path = os.path.join(reports_dir, f"{filename}.pdf")
                    generate_pdf_report(
                        title=f"Отчет по задачам",
                        data=report_data,
                        filename=file_path,
                        columns=[
                            ('ID', 'id', 10),
                            ('Название', 'title', 50),
                            ('Статус', 'status', 20),
                            ('Проект', 'project', 30),
                            ('Дата создания', 'created_at', 25),
                            ('Дедлайн', 'deadline', 20),
                            ('Менеджер', 'manager', 30),
                            ('Исполнители', 'executors', 40)
                        ]
                    )
                else:
                    file_path = os.path.join(reports_dir, f"{filename}.json")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(report_data, f, ensure_ascii=False, indent=2)

            elif report.report_type == 'projects':
                # Генерация отчета по проектам
                projects = Project.query.all()
                report_data = []
                for p in projects:
                    project_data = {
                        'id': p.id,
                        'name': p.name,
                        'description': p.description,
                        'created_at': p.created_at.strftime('%d.%m.%Y %H:%M') if p.created_at else None,
                        'deadline': p.deadline.strftime('%d.%m.%Y') if p.deadline else None,
                        'total_tasks': len(p.tasks),
                        'tasks_by_status': {
                            'todo': len([t for t in p.tasks if t.status == 'To Do']),
                            'in_progress': len([t for t in p.tasks if t.status == 'In Progress']),
                            'done': len([t for t in p.tasks if t.status == 'Done'])
                        },
                        'participants': ', '.join(
                            [f"{u.name} ({pu.role})" for u, pu in zip(p.users, p.user_associations)])
                    }
                    report_data.append(project_data)

                if report.format == 'pdf':
                    file_path = os.path.join(reports_dir, f"{filename}.pdf")
                    generate_pdf_report(
                        title=f"Отчет по проектам",
                        data=report_data,
                        filename=file_path,
                        columns=[
                            ('ID', 'id', 10),
                            ('Название', 'name', 40),
                            ('Описание', 'description', 60),
                            ('Дата создания', 'created_at', 25),
                            ('Дедлайн', 'deadline', 20),
                            ('Всего задач', 'total_tasks', 20),
                            ('Участники', 'participants', 60)
                        ],
                        charts=[
                            {
                                'type': 'pie',
                                'data': {
                                    'labels': ['To Do', 'In Progress', 'Done'],
                                    'values': [
                                        sum(p['tasks_by_status']['todo'] for p in report_data),
                                        sum(p['tasks_by_status']['in_progress'] for p in report_data),
                                        sum(p['tasks_by_status']['done'] for p in report_data)
                                    ],
                                    'title': 'Распределение задач по статусам'
                                }
                            }
                        ]
                    )
                else:
                    file_path = os.path.join(reports_dir, f"{filename}.json")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(report_data, f, ensure_ascii=False, indent=2)

            elif report.report_type == 'users':
                # Генерация отчета по пользователям
                users = User.query.all()
                report_data = []
                for u in users:
                    user_data = {
                        'id': u.id,
                        'name': u.name,
                        'email': u.email,
                        'total_projects': len(u.projects),
                        'total_tasks_assigned': len(u.assigned_tasks),
                        'tasks_by_status': {
                            'todo': len([t for t in u.assigned_tasks if t.status == 'To Do']),
                            'in_progress': len([t for t in u.assigned_tasks if t.status == 'In Progress']),
                            'done': len([t for t in u.assigned_tasks if t.status == 'Done'])
                        }
                    }
                    report_data.append(user_data)

                if report.format == 'pdf':
                    file_path = os.path.join(reports_dir, f"{filename}.pdf")
                    generate_pdf_report(
                        title=f"Отчет по пользователям",
                        data=report_data,
                        filename=file_path,
                        columns=[
                            ('ID', 'id', 10),
                            ('Имя', 'name', 30),
                            ('Email', 'email', 50),
                            ('Дата регистрации', 'registration_date', 25),
                            ('Последний вход', 'last_login', 25),
                            ('Проектов', 'total_projects', 20),
                            ('Задач', 'total_tasks_assigned', 20)
                        ],
                        charts=[
                            {
                                'type': 'bar',
                                'data': {
                                    'labels': [u['name'] for u in report_data],
                                    'values': [u['total_tasks_assigned'] for u in report_data],
                                    'title': 'Количество задач на пользователя'
                                }
                            }
                        ]
                    )
                else:
                    file_path = os.path.join(reports_dir, f"{filename}.json")
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(report_data, f, ensure_ascii=False, indent=2)

            # Обновляем отчет
            report.file_path = file_path
            report.status = 'completed'
            report.completed_at = datetime.now()
            db.session.commit()

        except Exception as e:
            report.status = 'failed'
            report.error_message = str(e)
            db.session.commit()
            app.logger.error(f"Failed to generate report {report.id}: {str(e)}")


def generate_pdf_report(title, data, filename, columns, charts=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    from fpdf.enums import XPos, YPos
    import tempfile
    import os
    import numpy as np

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)

    # Добавляем шрифты с проверкой
    fonts_dir = os.path.join(os.path.dirname(__file__), 'fonts')
    try:
        pdf.add_font('DejaVu', '', os.path.join(fonts_dir, 'DejaVuSansCondensed.ttf'), uni=True)
        pdf.add_font('DejaVu', 'B', os.path.join(fonts_dir, 'DejaVuSansCondensed-Bold.ttf'), uni=True)
    except Exception as e:
        print(f"Font loading error: {e}")
        return

    # Заголовок
    pdf.set_font('DejaVu', 'B', 16)
    pdf.cell(0, 10, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(10)

    # Дата генерации
    pdf.set_font('DejaVu', '', 10)
    pdf.cell(0, 5, f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
    pdf.ln(10)

    # Расчет ширины столбцов
    col_widths = []
    pdf.set_font('DejaVu', 'B', 12)
    for col in columns:
        max_width = pdf.get_string_width(col[0]) + 8  # Минимальная ширина заголовка

        # Проверяем все данные
        for row in data:
            value = str(row.get(col[1], ''))
            lines = value.split('\n')
            for line in lines:
                cell_width = pdf.get_string_width(line) + 8
                if cell_width > max_width:
                    max_width = cell_width

        col_widths.append(max_width)

    # Автоматическое масштабирование
    total_width = sum(col_widths)
    if total_width > pdf.epw:
        scale_factor = pdf.epw / total_width * 0.95  # Небольшой запас
        col_widths = [w * scale_factor for w in col_widths]

    # Заголовки таблицы
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font('DejaVu', 'B', 12)
    for i, col in enumerate(columns):
        pdf.cell(col_widths[i], 10, col[0], border=1, align='C', fill=True)
    pdf.ln()

    # Данные таблицы
    pdf.set_font('DejaVu', '', 10)
    fill = False

    for row in data:
        # Определяем высоту строки
        line_heights = []
        for i, col in enumerate(columns):
            value = str(row.get(col[1], ''))
            lines = pdf.multi_cell(col_widths[i], 5, value, border=0, align='L',
                                   split_only=True)
            line_heights.append(len(lines))

        row_height = max(line_heights) * 6  # Высота строки с учетом всех ячеек

        # Проверка на выход за границы страницы
        if pdf.get_y() + row_height > pdf.page_break_trigger:
            pdf.add_page()
            # Повторяем заголовки
            pdf.set_font('DejaVu', 'B', 12)
            for i, col in enumerate(columns):
                pdf.cell(col_widths[i], 10, col[0], border=1, align='C', fill=True)
            pdf.ln()
            pdf.set_font('DejaVu', '', 10)

        # Рисуем строку
        y_start = pdf.get_y()
        pdf.set_fill_color(245 if fill else 255)
        for i, col in enumerate(columns):
            value = str(row.get(col[1], ''))
            x = pdf.get_x()
            y = y_start

            # Ячейка с фоном
            pdf.set_xy(x, y)
            pdf.cell(col_widths[i], row_height, '', border=1, fill=fill)

            # Текст в ячейке
            pdf.set_xy(x + 2, y + 2)
            pdf.multi_cell(col_widths[i] - 4, 5, value, border=0, align='L')

            pdf.set_x(x + col_widths[i])

        pdf.set_y(y_start + row_height)
        fill = not fill  # Чередуем цвет фона

    # Графики
    if charts:
        pdf.add_page()
        pdf.set_font('DejaVu', 'B', 14)
        pdf.cell(0, 10, "Визуализация данных", 0, 1, 'C')
        pdf.ln(10)

        for chart in charts:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmpfile:
                try:
                    plt.figure(figsize=(8, 5), dpi=100)  # Уменьшаем размер и DPI для лучшего качества

                    if chart['type'] == 'pie':
                        plt.pie(
                            chart['data']['values'],
                            labels=chart['data']['labels'],
                            autopct='%1.1f%%',
                            startangle=90,
                            textprops={'fontsize': 8}  # Уменьшаем размер шрифта
                        )
                        plt.title(chart['data']['title'], fontsize=10)
                        plt.tight_layout()

                    elif chart['type'] == 'bar':
                        sns.set(font_scale=0.8)  # Уменьшаем размер шрифта
                        barplot = sns.barplot(
                            x=chart['data']['labels'],
                            y=chart['data']['values']
                        )
                        plt.title(chart['data']['title'], fontsize=10)
                        plt.xticks(rotation=45, ha='right', fontsize=8)
                        plt.yticks(fontsize=8)

                        # Добавляем значения на столбцы
                        for p in barplot.patches:
                            barplot.annotate(
                                format(p.get_height(), '.1f'),
                                (p.get_x() + p.get_width() / 2., p.get_height()),
                                ha='center', va='center',
                                xytext=(0, 5),
                                textcoords='offset points',
                                fontsize=8
                            )

                        plt.tight_layout()

                    plt.savefig(tmpfile.name, bbox_inches='tight', dpi=150)  # Уменьшаем DPI
                    plt.close()

                    # Добавляем график в PDF
                    pdf.set_font('DejaVu', '', 12)
                    pdf.cell(0, 10, chart['data']['title'], 0, 1, 'C')
                    pdf.image(tmpfile.name, x=10, y=None, w=180)
                    pdf.ln(10)

                finally:
                    try:
                        os.unlink(tmpfile.name)
                    except:
                        pass

    pdf.output(filename)
@bp.route('/admin/download_report/<int:report_id>')
@login_required
def download_report(report_id):
    if not current_user.is_admin:
        abort(403)

    report = Report.query.get_or_404(report_id)
    if not report.file_path or not os.path.exists(report.file_path):
        abort(404)

    # Определяем MIME-тип в зависимости от формата отчета
    mimetype = 'application/pdf' if report.format == 'pdf' else 'application/json'

    return send_from_directory(
        directory=os.path.dirname(report.file_path),
        path=os.path.basename(report.file_path),
        as_attachment=True,
        mimetype=mimetype
    )
