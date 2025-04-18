# app/routes.py

from flask import render_template, redirect, url_for, flash, Blueprint
from flask_login import current_user, login_user, login_required, logout_user
from app.forms import RegisterForm, LoginForm
from app.models import User, db

bp = Blueprint('taskflow', __name__)

@bp.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('taskflow.auth'))
    return render_template('main.html')

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
            return render_template(url_for('taskflow.index'))

    return render_template('auth.html', login_form=login_form, register_form=register_form)

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('taskflow.auth'))

@bp.route('/create_task')
@login_required
def task_create():
    return render_template('task_create.html')

@bp.route('/create_project')
@login_required
def create_project():
    return render_template('project_create.html')