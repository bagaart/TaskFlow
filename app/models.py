# models.py
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash
from . import db, login_manager
from flask_login import UserMixin


class User(db.Model, UserMixin):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(1024), nullable=False)

    # Relationships
    assigned_tasks = db.relationship('Task', foreign_keys='Task.executor_id', back_populates='executor', lazy=True)
    managed_tasks = db.relationship('Task', foreign_keys='Task.manager_id', back_populates='manager', lazy=True)
    comments = db.relationship('Comment', back_populates='author', lazy=True)
    notifications = db.relationship('Notification', back_populates='recipient', lazy=True)
    project_associations = db.relationship('ProjectUser', back_populates='user', lazy=True)
    projects = db.relationship('Project', secondary='project_user', back_populates='users',
                               overlaps="project_associations", lazy=True)
    changes_made = db.relationship('ChangeHistory', back_populates='user', lazy=True)
    assigned_tasks_link = db.relationship('TaskExecutor', back_populates='user')
    assigned_tasks = db.relationship('Task', secondary='task_executor', back_populates='executors')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.name}>'


class Task(db.Model):
    __tablename__ = "task"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime)
    priority = db.Column(db.String(50))
    status = db.Column(db.String(50), default='To Do')
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())

    # Foreign keys
    executor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    manager_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)

    # Relationships
    executor = db.relationship('User', foreign_keys=[executor_id], back_populates='assigned_tasks', lazy=True)
    manager = db.relationship('User', foreign_keys=[manager_id], back_populates='managed_tasks', lazy=True)
    project = db.relationship('Project', back_populates='tasks', lazy=True)
    task_card = db.relationship('TaskCard', back_populates='task', uselist=False, lazy=True)
    change_history = db.relationship('ChangeHistory', back_populates='task', lazy=True)
    executors_link = db.relationship('TaskExecutor', back_populates='task', cascade='all, delete-orphan')
    executors = db.relationship('User', secondary='task_executor', back_populates='assigned_tasks')

    def __repr__(self):
        return f'<Task {self.title}>'


class Project(db.Model):
    __tablename__ = "project"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.now())
    deadline = db.Column(db.DateTime)

    @property
    def formatted_created_at(self):
        return self.created_at.strftime('%d.%m.%Y')

    @property
    def formatted_deadline(self):
        if self.deadline:
            return self.deadline.strftime('%d.%m.%Y')
        return "Нет дедлайна"

    @property
    def days_remaining(self):
        if self.deadline:
            return (self.deadline - datetime.now()).days
        return None

    # Relationships
    kanban_board = db.relationship('KanbanBoard', back_populates='project', uselist=False, lazy=True)
    tasks = db.relationship('Task', back_populates='project', lazy=True)
    user_associations = db.relationship('ProjectUser', back_populates='project', lazy=True)
    users = db.relationship('User', secondary='project_user', back_populates='projects',
                            overlaps="user_associations", lazy=True)

    def __repr__(self):
        return f'<Project {self.name}>'


class ProjectUser(db.Model):
    __tablename__ = 'project_user'

    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    role = db.Column(db.String(50), nullable=False, default='member')  # 'member', 'manager', 'analyst'

    # Отношения
    project = db.relationship('Project', back_populates='user_associations')
    user = db.relationship('User', back_populates='project_associations')

    def __repr__(self):
        return f'<ProjectUser project_id={self.project_id} user_id={self.user_id}>'


class KanbanBoard(db.Model):
    __tablename__ = "kanban_board"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    columns = db.Column(db.JSON, default=lambda: {"To Do": [], "In Progress": [], "Done": []})

    # Foreign key
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)

    # Relationships
    project = db.relationship('Project', back_populates='kanban_board')
    task_cards = db.relationship('TaskCard', back_populates='kanban_board', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<KanbanBoard {self.name}>'


class TaskCard(db.Model):
    __tablename__ = "task_card"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    position = db.Column(db.String(50), nullable=False)

    # Foreign keys
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    kanban_board_id = db.Column(db.Integer, db.ForeignKey('kanban_board.id'))

    # Relationships
    task = db.relationship('Task', back_populates='task_card')
    kanban_board = db.relationship('KanbanBoard', back_populates='task_cards')
    comments = db.relationship('Comment', back_populates='task_card', lazy=True, cascade="all, delete-orphan")
    attached_files = db.relationship('AttachedFile', back_populates='task_card', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<TaskCard {self.position}>'


class Comment(db.Model):
    __tablename__ = "comment"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=db.func.now())

    # Foreign keys
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    task_card_id = db.Column(db.Integer, db.ForeignKey('task_card.id'), nullable=False)

    # Relationships
    author = db.relationship('User', back_populates='comments')
    task_card = db.relationship('TaskCard', back_populates='comments')

    def __repr__(self):
        return f'<Comment {self.content[:30]}>'


class AttachedFile(db.Model):
    __tablename__ = "attached_file"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    size = db.Column(db.Float)
    file_type = db.Column(db.String(50))
    file_path = db.Column(db.String(255), nullable=False)

    # Foreign key
    task_card_id = db.Column(db.Integer, db.ForeignKey('task_card.id'), nullable=False)

    # Relationship
    task_card = db.relationship('TaskCard', back_populates='attached_files')

    def __repr__(self):
        return f'<AttachedFile {self.name}>'


class Notification(db.Model):
    __tablename__ = "notification"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    type = db.Column(db.String(50))
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    is_read = db.Column(db.Boolean, default=False)

    # Foreign key
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Relationship
    recipient = db.relationship('User', back_populates='notifications')

    def __repr__(self):
        return f'<Notification {self.type}>'


class Report(db.Model):
    __tablename__ = "report"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, default=db.func.now())
    backup_path = db.Column(db.String(1024), nullable=False)
    description = db.Column(db.Text)

    def __repr__(self):
        return f'<Report {self.timestamp}>'


class ChangeHistory(db.Model):
    __tablename__ = "change_history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    changes = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.now())

    # Foreign keys
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    # Relationships
    task = db.relationship('Task', back_populates='change_history')
    user = db.relationship('User', back_populates='changes_made')

    def __repr__(self):
        return f'<ChangeHistory {self.timestamp}>'

class TaskExecutor(db.Model):
    __tablename__ = 'task_executor'

    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)

    task = db.relationship('Task', back_populates='executors_link')
    user = db.relationship('User', back_populates='assigned_tasks_link')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))