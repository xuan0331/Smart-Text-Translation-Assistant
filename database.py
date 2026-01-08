# database.py
import os
import sqlite3
from config import config


class DatabaseManager:
    """数据库管理类（SQLite）"""

    @staticmethod
    def _get_db_path():
        uri = getattr(config, 'SQLALCHEMY_DATABASE_URI', '')
        prefix = 'sqlite:///'
        if uri.startswith(prefix):
            return uri[len(prefix):]
        return os.path.join(os.path.abspath(os.path.dirname(__file__)), 'translation_system.db')

    @staticmethod
    def test_connection():
        """测试数据库连接 (SQLite)"""
        try:
            db_path = DatabaseManager._get_db_path()
            connection = sqlite3.connect(db_path)
            connection.row_factory = sqlite3.Row

            with connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                table_exists = cursor.fetchone() is not None

                if table_exists:
                    cursor.execute("PRAGMA table_info(users)")
                    columns = cursor.fetchall()
                    column_names = [col['name'] for col in columns]

                    print("✅ 数据库连接成功！")
                    print("📊 users表结构：")
                    for col in columns:
                        print(f"  - {col['name']}: {col['type']} (notnull={col['notnull']})")

                    required_columns = ['id', 'username', 'qq_email', 'password', 'created_at']
                    missing_columns = [col for col in required_columns if col not in column_names]

                    if missing_columns:
                        print(f"⚠️  缺少字段: {', '.join(missing_columns)}")
                    else:
                        print("✅ 表结构正确！")
                        cursor.execute("SELECT COUNT(*) as count FROM users")
                        count = cursor.fetchone()[0]
                        print(f"👥 现有用户数量: {count}")

                        if count > 0:
                            cursor.execute(
                                "SELECT username, qq_email, created_at FROM users ORDER BY created_at DESC LIMIT 5"
                            )
                            recent_users = cursor.fetchall()
                            print("📝 最近注册的用户：")
                            for user in recent_users:
                                print(f"  - {user['username']} ({user['qq_email']}) - {user['created_at']}")
                else:
                    print("❌ users表不存在！")
                    print("请确保已运行应用以自动创建表，或手动创建：")
                    print(
                        "CREATE TABLE users (\n"
                        "  id INTEGER PRIMARY KEY AUTOINCREMENT,\n"
                        "  username VARCHAR(30) UNIQUE NOT NULL,\n"
                        "  qq_email VARCHAR(100) UNIQUE NOT NULL,\n"
                        "  password VARCHAR(255) NOT NULL,\n"
                        "  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP\n"
                        ");"
                    )

            connection.close()
            return True

        except Exception as e:
            print(f"❌ 发生错误: {e}")
            return False

    @staticmethod
    def create_user_directly(username, email, password):
        """直接通过SQL创建用户（SQLite）"""
        try:
            db_path = DatabaseManager._get_db_path()
            connection = sqlite3.connect(db_path)
            with connection:
                cursor = connection.cursor()
                from werkzeug.security import generate_password_hash
                password_hash = generate_password_hash(password)
                cursor.execute(
                    "INSERT INTO users (username, qq_email, password) VALUES (?, ?, ?)",
                    (username, email, password_hash)
                )
            print(f"✅ 用户 {username} 创建成功！")
            return True
        except sqlite3.IntegrityError as e:
            if 'username' in str(e):
                print(f"❌ 用户名 '{username}' 已存在")
            elif 'qq_email' in str(e):
                print(f"❌ 邮箱 '{email}' 已注册")
            else:
                print(f"❌ 数据库错误: {e}")
            return False
        except Exception as e:
            print(f"❌ 发生错误: {e}")
            return False
        finally:
            if 'connection' in locals():
                connection.close()


if __name__ == '__main__':
    print("🔍 测试数据库连接...")
    DatabaseManager.test_connection()