# models.py
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import re

db = SQLAlchemy()


class User(db.Model):
    """用户模型 - 完全匹配您现有的数据库表结构"""
    __tablename__ = 'users'

    # 字段与您的数据库表完全一致
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(30), unique=True, nullable=False, index=True)
    qq_email = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

    # 添加关系（方便查询用户的翻译历史）
    translation_histories = db.relationship('TranslationHistory', backref='user', lazy=True,
                                            cascade='all, delete-orphan')

    def __init__(self, username, qq_email, password):
        self.username = username
        self.qq_email = qq_email
        self.set_password(password)

    def set_password(self, password):
        """设置密码（使用werkzeug的密码哈希）"""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """验证密码"""
        return check_password_hash(self.password, password)

    @staticmethod
    def validate_qq_email(email):
        """验证QQ邮箱格式"""
        if not email:
            return False, "邮箱不能为空"

        pattern = r'^[1-9][0-9]{4,10}@qq\.com$'
        if not re.match(pattern, email, re.IGNORECASE):
            return False, "请输入正确的QQ邮箱格式（如：123456@qq.com）"

        return True, "邮箱格式正确"

    @staticmethod
    def validate_username(username):
        """验证用户名格式"""
        if not username:
            return False, "用户名不能为空"

        if len(username) < 3:
            return False, "用户名长度至少3个字符"

        if len(username) > 30:
            return False, "用户名长度不能超过30个字符"

        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return False, "用户名只能包含字母、数字和下划线"

        return True, "用户名格式正确"

    @staticmethod
    def validate_password(password):
        """验证密码强度"""
        if not password:
            return False, "密码不能为空"

        if len(password) < 6:
            return False, "密码长度至少6位"

        return True, "密码强度足够"

    def to_dict(self):
        """转换为字典（用于JSON响应）"""
        return {
            'id': self.id,
            'username': self.username,
            'qq_email': self.qq_email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f'<User {self.username}>'


class TranslationHistory(db.Model):
    """翻译历史记录模型"""
    __tablename__ = 'translation_history'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # 翻译相关字段
    original_text = db.Column(db.Text, nullable=False)
    source_lang = db.Column(db.String(10), default='auto')
    target_lang = db.Column(db.String(10), default='zh')
    translated_text = db.Column(db.Text)

    # 操作类型：ocr（文字识别）、translate（翻译）、tts（语音合成）
    operation_type = db.Column(db.String(20), default='translate')

    # OCR相关字段（可选）
    image_path = db.Column(db.String(255))
    confidence = db.Column(db.Float)

    # 时间戳
    created_at = db.Column(db.TIMESTAMP, server_default=db.func.current_timestamp())

    # 索引
    __table_args__ = (
        db.Index('idx_user_created', 'user_id', 'created_at'),
        db.Index('idx_operation_type', 'operation_type'),
    )

    def __init__(self, user_id, original_text, **kwargs):
        self.user_id = user_id
        self.original_text = original_text

        # 设置可选字段
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def to_dict(self):
        """转换为字典（用于JSON响应）"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'original_text': self.original_text,
            'source_lang': self.source_lang,
            'target_lang': self.target_lang,
            'translated_text': self.translated_text,
            'operation_type': self.operation_type,
            'image_path': self.image_path,
            'confidence': self.confidence,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def get_preview_text(self, max_length=100):
        """获取文本预览"""
        if self.original_text and len(self.original_text) > max_length:
            return self.original_text[:max_length] + '...'
        return self.original_text or ''

    @classmethod
    def get_user_history(cls, user_id, operation_type=None, limit=20):
        """获取用户的翻译历史记录"""
        query = cls.query.filter_by(user_id=user_id)

        if operation_type:
            query = query.filter_by(operation_type=operation_type)

        return query.order_by(cls.created_at.desc()).limit(limit).all()

    def __repr__(self):
        return f'<TranslationHistory {self.id} - {self.operation_type}>'