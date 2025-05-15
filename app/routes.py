# app/routes.py

from flask import render_template, redirect, url_for, flash, Blueprint, request, abort
from flask_login import current_user, login_user, login_required, logout_user
from app.forms import RegisterForm, LoginForm
from app.models import User, db, ProjectUser, Project, Task, TaskExecutor
from flask import jsonify
from datetime import datetime

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