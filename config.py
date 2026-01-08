# config.py
import os
from datetime import timedelta


class Config:
    # 基础配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-change-this'

    # 数据库配置（切换为SQLite本地文件）
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'translation_system.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 应用配置
    DEBUG = True
    PORT = 5001
    HOST = '0.0.0.0'

    # 安全配置
    SESSION_COOKIE_SECURE = False  # 开发环境设为False
    SESSION_COOKIE_HTTPONLY = True

    # 注册限制
    MAX_USERNAME_LENGTH = 30
    MIN_USERNAME_LENGTH = 3
    MAX_EMAIL_LENGTH = 100
    MIN_PASSWORD_LENGTH = 6


config = Config()