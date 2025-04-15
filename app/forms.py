# forms.py

from flask_wtf import FlaskForm
from wtforms.fields.simple import StringField, SubmitField, PasswordField
from wtforms.validators import DataRequired, Length, EqualTo


class RegisterForm(FlaskForm):
    name = StringField(
        'Name',
        validators=[DataRequired(), Length(min=2, max=255)]
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Length(min=2, max=255)]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(), Length(min=8, max=255)]
    )
    confirm_password = PasswordField(
        'Confirm Password',
        validators=[
            DataRequired(),
            EqualTo('password', message='Passwords must match')
        ]
    )

    submit = SubmitField('Register')


class LoginForm(FlaskForm):
    email = StringField(
        'Email',
        validators=[DataRequired(), Length(min=2, max=255)]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(), Length(min=8, max=255)]
    )

    submit = SubmitField('Login')