# config.py
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'key')
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:postgres@localhost:5432/taskflow_db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
