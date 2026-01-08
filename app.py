# app.py
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from services.voice_service import get_voice_service
from services.speech_service import get_speech_service
from flask_sqlalchemy import SQLAlchemy
from config import config
from models import db, User, TranslationHistory  # 重新导入 TranslationHistory
import logging
import json
from datetime import datetime
from pathlib import Path
import os
import sys

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app():
    """创建Flask应用，兼容 PyInstaller (_MEIPASS) 的资源路径"""
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    app = Flask(
        __name__,
        static_folder=str(base_path / "static"),
        template_folder=str(base_path / "templates"),
    )

    # 加载配置
    app.config.from_object(config)

    # 初始化数据库
    db.init_app(app)

    # 创建数据库表（如果不存在）
    with app.app_context():
        try:
            db.create_all()
            logger.info("✅ 数据库表初始化完成")
        except Exception as e:
            logger.error(f"❌ 数据库表初始化失败: {e}")

    # ==================== 辅助函数 ====================

    def allowed_file(filename):
        """检查文件类型是否允许"""
        allowed_extensions = {'png', 'jpg', 'jpeg', 'bmp', 'pdf'}
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in allowed_extensions

    def save_uploaded_file(file):
        """保存上传的文件"""
        from werkzeug.utils import secure_filename

        # 创建上传目录
        upload_folder = 'static/uploads'
        os.makedirs(upload_folder, exist_ok=True)

        # 生成安全的唯一文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        original_name = secure_filename(file.filename)
        base_name, ext = os.path.splitext(original_name)
        unique_filename = f"{timestamp}_{base_name}{ext}"

        # 保存文件路径
        filepath = os.path.join(upload_folder, unique_filename)

        # 保存文件
        file.save(filepath)

        return {
            'filename': unique_filename,
            'filepath': filepath,
            'url': f'/static/uploads/{unique_filename}'
        }

    def get_ocr_service():
        """获取OCR服务实例"""
        try:
            from services.ocr_service import get_ocr_service as get_service
            return get_service()
        except ImportError:
            logger.error("OCR服务模块未找到，请创建 services/ocr_service.py")
            raise

    def get_translation_service():
        """获取翻译服务实例"""
        try:
            from services.translation_service import get_translation_service as get_service
            return get_service()
        except ImportError:
            logger.error("翻译服务模块未找到，请创建 services/translation_service.py")
            raise

    def get_speech_recognition_service():
        """获取语音识别服务实例"""
        try:
            return get_speech_service()
        except ImportError:
            logger.error("语音识别服务模块未找到，请创建 services/speech_service.py")
            raise

    def get_time_ago(timestamp):
        """获取相对时间描述"""
        if not timestamp:
            return "未知时间"

        now = datetime.now()
        diff = now - timestamp

        if diff.days > 365:
            return f"{diff.days // 365}年前"
        elif diff.days > 30:
            return f"{diff.days // 30}个月前"
        elif diff.days > 0:
            return f"{diff.days}天前"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600}小时前"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60}分钟前"
        else:
            return "刚刚"

    # ==================== 路由定义 ====================

    @app.route('/')
    def index():
        """首页重定向到登录页面"""
        return redirect(url_for('login_page'))

    @app.route('/register')
    def register_page():
        """注册页面"""
        return render_template('register.html')

    @app.route('/api/check/username/<username>')
    def check_username(username):
        """检查用户名是否可用"""
        try:
            user = User.query.filter_by(username=username).first()
            return jsonify({
                'available': user is None,
                'message': '用户名已存在' if user else '用户名可用'
            })
        except Exception as e:
            logger.error(f"检查用户名失败: {e}")
            return jsonify({
                'available': False,
                'message': '检查失败'
            }), 500

    @app.route('/api/check/email/<email>')
    def check_email(email):
        """检查邮箱是否可用"""
        try:
            user = User.query.filter_by(qq_email=email).first()
            return jsonify({
                'available': user is None,
                'message': '邮箱已注册' if user else '邮箱可用'
            })
        except Exception as e:
            logger.error(f"检查邮箱失败: {e}")
            return jsonify({
                'available': False,
                'message': '检查失败'
            }), 500

    @app.route('/api/register', methods=['POST'])
    def api_register():
        """注册API接口"""
        try:
            # 获取JSON数据
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form

            username = data.get('username', '').strip()
            qq_email = data.get('qq_email', '').strip()
            password = data.get('password', '')
            confirm_password = data.get('confirm_password', '')

            logger.info(f"注册请求: username={username}, email={qq_email}")

            # 验证必填字段
            if not all([username, qq_email, password, confirm_password]):
                return jsonify({
                    'success': False,
                    'message': '所有字段都必须填写'
                }), 400

            # 验证密码一致性
            if password != confirm_password:
                return jsonify({
                    'success': False,
                    'message': '两次输入的密码不一致'
                }), 400

            # 验证用户名格式
            is_valid, username_msg = User.validate_username(username)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': username_msg
                }), 400

            # 验证QQ邮箱格式
            is_valid, email_msg = User.validate_qq_email(qq_email)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': email_msg
                }), 400

            # 验证密码强度
            is_valid, password_msg = User.validate_password(password)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': password_msg
                }), 400

            # 检查用户名是否已存在
            existing_user = User.query.filter_by(username=username).first()
            if existing_user:
                return jsonify({
                    'success': False,
                    'message': '用户名已存在'
                }), 409

            # 检查邮箱是否已存在
            existing_email = User.query.filter_by(qq_email=qq_email).first()
            if existing_email:
                return jsonify({
                    'success': False,
                    'message': '该QQ邮箱已被注册'
                }), 409

            # 创建新用户
            new_user = User(username=username, qq_email=qq_email, password=password)

            # 保存到数据库
            db.session.add(new_user)
            db.session.commit()

            # 记录注册日志
            log_data = {
                'timestamp': datetime.now().isoformat(),
                'user_id': new_user.id,
                'username': new_user.username,
                'email': new_user.qq_email,
                'ip': request.remote_addr,
                'user_agent': request.user_agent.string
            }
            logger.info(f"用户注册成功: {json.dumps(log_data)}")

            # 设置session
            session['user_id'] = new_user.id
            session['username'] = new_user.username

            return jsonify({
                'success': True,
                'message': '注册成功！',
                'user': new_user.to_dict(),
                'redirect': '/login'
            }), 201

        except Exception as e:
            db.session.rollback()
            logger.error(f"注册失败: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': '系统错误，请稍后重试'
            }), 500

    @app.route('/api/users')
    def get_users():
        """获取所有用户（仅用于测试）"""
        try:
            users = User.query.all()
            return jsonify({
                'success': True,
                'count': len(users),
                'users': [user.to_dict() for user in users]
            })
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            return jsonify({
                'success': False,
                'message': '获取用户列表失败'
            }), 500

    @app.route('/login')
    def login_page():
        """登录页面"""
        return render_template('login.html')

    @app.route('/api/login', methods=['POST'])
    def api_login():
        """登录API接口"""
        try:
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form

            username = data.get('username', '').strip()
            password = data.get('password', '')

            # 查找用户（支持用户名或邮箱登录）
            user = User.query.filter(
                (User.username == username) | (User.qq_email == username)
            ).first()

            if user and user.check_password(password):
                # 设置session
                session['user_id'] = user.id
                session['username'] = user.username

                logger.info(f"用户登录成功: {user.username}")

                return jsonify({
                    'success': True,
                    'message': '登录成功',
                    'user': user.to_dict(),
                    'redirect': '/main'
                })
            else:
                logger.warning(f"登录失败: username={username}")
                return jsonify({
                    'success': False,
                    'message': '用户名或密码错误'
                }), 401

        except Exception as e:
            logger.error(f"登录失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': '系统错误，请稍后重试'
            }), 500

    @app.route('/api/logout')
    def api_logout():
        """登出"""
        session.clear()
        return jsonify({
            'success': True,
            'message': '已退出登录'
        })

    @app.route('/test-db')
    def test_db():
        """测试数据库连接页面"""
        from database import DatabaseManager
        success = DatabaseManager.test_connection()
        return f"数据库连接测试: {'成功' if success else '失败'}"

    # ==================== OCR 功能路由 ====================

    @app.route('/api/ocr/recognize', methods=['POST'])
    def ocr_recognize():
        """OCR文字识别接口"""
        try:
            # 检查用户是否登录
            if 'user_id' not in session:
                return jsonify({
                    'success': False,
                    'message': '请先登录',
                    'code': 401
                }), 401

            # 检查是否有文件上传
            if 'image' not in request.files:
                return jsonify({
                    'success': False,
                    'message': '请选择要识别的图片',
                    'code': 400
                }), 400

            file = request.files['image']

            # 检查文件是否选择
            if file.filename == '':
                return jsonify({
                    'success': False,
                    'message': '请选择有效的图片文件',
                    'code': 400
                }), 400

            # 检查文件类型
            if not allowed_file(file.filename):
                return jsonify({
                    'success': False,
                    'message': '不支持的文件类型，仅支持 PNG, JPG, JPEG, BMP, PDF',
                    'code': 400
                }), 400

            user_id = session['user_id']
            username = session.get('username', '用户')

            # 保存上传的图片
            upload_result = save_uploaded_file(file)

            # 从保存的文件路径识别
            ocr_service = get_ocr_service()
            ocr_result = ocr_service.recognize_from_path(upload_result['filepath'])

            if ocr_result['success']:
                # 将识别结果保存到session（不再保存到数据库）
                session['last_ocr_text'] = ocr_result['text']
                session['last_ocr_image'] = upload_result['filename']

                logger.info(f"OCR识别成功: 用户={username}, 字符数={len(ocr_result['text'])}")

                return jsonify({
                    'success': True,
                    'message': ocr_result['message'],
                    'text': ocr_result['text'],
                    'detections': ocr_result.get('detections', []),
                    'confidence': ocr_result.get('confidence', 0),
                    'image_info': {
                        'filename': upload_result['filename'],
                        'url': upload_result['url']
                    },
                    'user_info': {
                        'username': username,
                        'user_id': user_id
                    },
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            else:
                # 如果识别失败，删除已上传的图片
                if os.path.exists(upload_result['filepath']):
                    os.remove(upload_result['filepath'])

                logger.warning(f"OCR识别失败: {ocr_result['message']}")

                return jsonify({
                    'success': False,
                    'message': ocr_result['message'],
                    'code': 500
                }), 500

        except Exception as e:
            logger.error(f"OCR处理异常: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'处理失败: {str(e)}',
                'code': 500
            }), 500

    @app.route('/api/ocr/recognize/batch', methods=['POST'])
    def ocr_recognize_batch():
        """批量OCR识别，多文件上传返回列表结果"""
        try:
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': '请先登录', 'code': 401}), 401
            files = request.files.getlist('images')
            if not files:
                return jsonify({'success': False, 'message': '请上传图片文件', 'code': 400}), 400
            results = []
            ocr_service = get_ocr_service()
            for file in files:
                if not allowed_file(file.filename):
                    results.append({'filename': file.filename, 'success': False, 'message': '不支持的文件类型'})
                    continue
                upload = save_uploaded_file(file)
                ocr_result = ocr_service.recognize_from_path(upload['filepath'])
                if ocr_result['success']:
                    history = TranslationHistory(
                        user_id=session['user_id'],
                        original_text=ocr_result['text'],
                        translated_text=ocr_result['text'],
                        source_lang='auto',
                        target_lang='auto',
                        operation_type='ocr',
                        image_path=upload['filepath'],
                        confidence=ocr_result.get('confidence'),
                    )
                    db.session.add(history)
                    db.session.commit()
                results.append({
                    'filename': file.filename,
                    'success': ocr_result.get('success', False),
                    'text': ocr_result.get('text', ''),
                    'message': ocr_result.get('message', ''),
                    'image_url': upload['url'],
                })
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            logger.error(f"批量OCR处理异常: {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'处理失败: {e}', 'code': 500}), 500

    @app.route('/api/ocr/test', methods=['GET'])
    def ocr_test():
        """测试OCR服务是否正常"""
        try:
            ocr_service = get_ocr_service()

            # 简单测试
            return jsonify({
                'success': True,
                'service': 'OCR文字识别',
                'status': '服务正常',
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'service': 'OCR文字识别',
                'status': '服务异常',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }), 500

    @app.route('/main')
    def main_page():
        """主页面 - 检查登录状态"""
        if 'user_id' not in session:
            return redirect(url_for('login_page'))

        user_info = {
            'user_id': session.get('user_id'),
            'username': session.get('username')
        }

        return render_template('main.html', user_info=user_info)

    # ==================== 翻译功能路由 ====================

    @app.route('/api/translate', methods=['POST'])
    def translate_text():
        """文本翻译接口"""
        try:
            # 检查用户是否登录
            if 'user_id' not in session:
                return jsonify({
                    'success': False,
                    'message': '请先登录',
                    'code': 401
                }), 401

            # 获取请求数据
            if request.is_json:
                data = request.get_json()
            else:
                data = request.form

            text = data.get('text', '').strip()
            source_lang = data.get('source_lang', 'zh')
            target_lang = data.get('target_lang', 'en')

            if not text:
                return jsonify({
                    'success': False,
                    'message': '请输入要翻译的文本',
                    'code': 400
                }), 400

            user_id = session['user_id']
            username = session.get('username', '用户')

            # 调用翻译服务
            translation_service = get_translation_service()
            translation_result = translation_service.translate(text, source_lang, target_lang)

            if translation_result['success']:
                # 保存到翻译历史记录
                history = TranslationHistory(
                    user_id=user_id,
                    original_text=text,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    translated_text=translation_result['translated'],
                    operation_type='translate'
                )
                db.session.add(history)
                db.session.commit()

                # 将翻译结果保存到session
                session['last_translation'] = {
                    'original': text,
                    'translated': translation_result['translated'],
                    'source_lang': source_lang,
                    'target_lang': target_lang,
                    'timestamp': datetime.now().isoformat(),
                    'history_id': history.id
                }

                logger.info(f"翻译成功: 用户={username}, {source_lang}→{target_lang}, 字符数={len(text)}")

                return jsonify({
                    'success': True,
                    'message': translation_result['message'],
                    'original': text,
                    'translated': translation_result['translated'],
                    'source_lang': source_lang,
                    'target_lang': target_lang,
                    'history_id': history.id,
                    'user_info': {
                        'username': username,
                        'user_id': user_id
                    },
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            else:
                logger.warning(f"翻译失败: {translation_result['message']}")

                return jsonify({
                    'success': False,
                    'message': translation_result['message'],
                    'code': 500
                }), 500

        except Exception as e:
            db.session.rollback()
            logger.error(f"翻译处理异常: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'翻译失败: {str(e)}',
                'code': 500
            }), 500

    @app.route('/api/translate/history', methods=['GET'])
    def get_translation_history():
        """获取翻译历史记录"""
        try:
            # 检查用户是否登录
            if 'user_id' not in session:
                return jsonify({
                    'success': False,
                    'message': '请先登录',
                    'code': 401
                }), 401

            user_id = session['user_id']

            # 获取请求参数
            limit = request.args.get('limit', 20, type=int)
            page = request.args.get('page', 1, type=int)
            operation_type = request.args.get('type', 'translate')

            # 查询用户的翻译历史记录
            histories = TranslationHistory.query.filter_by(
                user_id=user_id,
                operation_type=operation_type
            ).order_by(TranslationHistory.created_at.desc()) \
                .paginate(page=page, per_page=limit, error_out=False)

            result = []
            for history in histories.items:
                # 获取预览文本
                original_preview = history.original_text
                if len(original_preview) > 100:
                    original_preview = original_preview[:100] + '...'

                translated_preview = history.translated_text or ''
                if len(translated_preview) > 100:
                    translated_preview = translated_preview[:100] + '...'

                result.append({
                    'id': history.id,
                    'original_text': history.original_text,
                    'translated_text': history.translated_text,
                    'original_preview': original_preview,
                    'translated_preview': translated_preview,
                    'source_lang': history.source_lang,
                    'target_lang': history.target_lang,
                    'operation_type': history.operation_type,
                    'created_at': history.created_at.strftime('%Y-%m-%d %H:%M:%S') if history.created_at else None,
                    'time_ago': get_time_ago(history.created_at) if history.created_at else None
                })

            return jsonify({
                'success': True,
                'count': len(result),
                'total': histories.total,
                'page': histories.page,
                'pages': histories.pages,
                'has_next': histories.has_next,
                'has_prev': histories.has_prev,
                'histories': result,
                'message': f'找到{histories.total}条翻译历史记录'
            })

        except Exception as e:
            logger.error(f"获取翻译历史失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'获取历史记录失败: {str(e)}',
                'code': 500
            }), 500

    @app.route('/api/translate/history/<int:history_id>', methods=['GET'])
    def get_translation_history_detail(history_id):
        """获取单条翻译历史记录详情"""
        try:
            # 检查用户是否登录
            if 'user_id' not in session:
                return jsonify({
                    'success': False,
                    'message': '请先登录',
                    'code': 401
                }), 401

            user_id = session['user_id']

            # 查找记录
            history = TranslationHistory.query.filter_by(
                id=history_id,
                user_id=user_id,
                operation_type='translate'
            ).first()

            if not history:
                return jsonify({
                    'success': False,
                    'message': '记录不存在或无权访问',
                    'code': 404
                }), 404

            return jsonify({
                'success': True,
                'history': history.to_dict(),
                'message': '获取记录详情成功'
            })

        except Exception as e:
            logger.error(f"获取翻译历史详情失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'获取记录详情失败: {str(e)}',
                'code': 500
            }), 500

    @app.route('/api/translate/history/<int:history_id>', methods=['DELETE'])
    def delete_translation_history(history_id):
        """删除翻译历史记录"""
        try:
            # 检查用户是否登录
            if 'user_id' not in session:
                return jsonify({
                    'success': False,
                    'message': '请先登录',
                    'code': 401
                }), 401

            user_id = session['user_id']

            # 查找记录
            history = TranslationHistory.query.filter_by(
                id=history_id,
                user_id=user_id,
                operation_type='translate'
            ).first()

            if not history:
                return jsonify({
                    'success': False,
                    'message': '记录不存在或无权删除',
                    'code': 404
                }), 404

            # 删除数据库记录
            db.session.delete(history)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': '删除成功',
                'deleted_id': history_id
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"删除翻译历史失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'删除失败: {str(e)}',
                'code': 500
            }), 500

    @app.route('/api/translate/history/clear', methods=['DELETE'])
    def clear_translation_history():
        """清空翻译历史记录"""
        try:
            # 检查用户是否登录
            if 'user_id' not in session:
                return jsonify({
                    'success': False,
                    'message': '请先登录',
                    'code': 401
                }), 401

            user_id = session['user_id']

            # 删除用户的所有翻译历史记录
            deleted_count = TranslationHistory.query.filter_by(
                user_id=user_id,
                operation_type='translate'
            ).delete()

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'已清空{deleted_count}条翻译历史记录',
                'deleted_count': deleted_count
            })

        except Exception as e:
            db.session.rollback()
            logger.error(f"清空翻译历史失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': f'清空失败: {str(e)}',
                'code': 500
            }), 500

    # ==================== 错误处理 ====================

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            'success': False,
            'message': '请求的资源不存在'
        }), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"服务器内部错误: {error}")
        return jsonify({
            'success': False,
            'message': '服务器内部错误'
        }), 500

    # ==================== 语音合成API路由 ====================

    @app.route('/api/voice/synthesize', methods=['POST'])
    def voice_synthesize():
        """语音合成API接口"""
        try:
            # 检查用户是否登录
            if 'user_id' not in session:
                return jsonify({
                    'success': False,
                    'message': '请先登录',
                    'code': 401
                }), 401

            # 获取请求数据
            data = request.get_json()

            text = data.get('text', '').strip()
            lang = data.get('lang', 'zh')
            gender = data.get('gender', 'female')
            speed = float(data.get('speed', 1.0))

            if not text:
                return jsonify({
                    'success': False,
                    'message': '请输入要合成的文本',
                    'code': 400
                }), 400

            # 限制文本长度
            if len(text) > 1500:
                return jsonify({
                    'success': False,
                    'message': '文本过长，请限制在1500字符以内',
                    'code': 400
                }), 400

            # 获取语音服务
            voice_service = get_voice_service()

            if not voice_service.is_available():
                return jsonify({
                    'success': False,
                    'message': '语音合成服务不可用，请检查腾讯云配置',
                    'code': 503
                }), 503

            # 调用语音合成服务
            result = voice_service.text_to_speech(text, lang, gender, speed)

            if result['success']:
                # 记录使用日志
                logger.info(f"语音合成: 用户={session.get('username')}, 语言={lang}, 字符数={len(text)}")

                return jsonify({
                    'success': True,
                    'message': result['message'],
                    'audio_url': result['audio_url'],
                    'duration': result['duration'],
                    'format': result.get('format', 'mp3'),
                    'language': lang,
                    'gender': gender,
                    'speed': speed,
                    'user_info': {
                        'username': session.get('username'),
                        'user_id': session['user_id']
                    },
                    'timestamp': result.get('timestamp', datetime.now().isoformat())
                })
            else:
                return jsonify({
                    'success': False,
                    'message': result['message'],
                    'code': 500
                }), 500

        except Exception as e:
            logger.error(f"语音合成API异常: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'语音合成失败: {str(e)}',
                'code': 500
            }), 500

    @app.route('/api/voice/languages', methods=['GET'])
    def get_voice_languages():
        """获取支持的语音语言列表"""
        try:
            voice_service = get_voice_service()
            languages = voice_service.get_supported_languages()

            # 转换为前端需要的格式
            formatted_languages = {}
            for code, info in languages.items():
                formatted_languages[code] = info['name']

            return jsonify({
                'success': True,
                'languages': formatted_languages,
                'service_available': voice_service.is_available()
            })
        except Exception as e:
            logger.error(f"获取语音语言列表失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': str(e),
                'service_available': False
            }), 500

    @app.route('/api/voice/voices', methods=['GET'])
    def get_voice_voices():
        """获取支持的音色列表"""
        try:
            voices = {
                'female': {'name': '女声', 'description': '柔和女声'},
                'male': {'name': '男声', 'description': '沉稳男声'},
                'child': {'name': '童声', 'description': '清脆童声'},
                'robot': {'name': '机器人', 'description': '电子音色'}
            }

            voice_service = get_voice_service()

            return jsonify({
                'success': True,
                'voices': voices,
                'service_available': voice_service.is_available()
            })
        except Exception as e:
            logger.error(f"获取音色列表失败: {str(e)}")
            return jsonify({
                'success': False,
                'message': str(e),
                'service_available': False
            }), 500

    @app.route('/api/voice/test', methods=['GET'])
    def test_voice_service():
        """测试语音合成服务状态"""
        try:
            voice_service = get_voice_service()

            if not voice_service.is_available():
                return jsonify({
                    'success': False,
                    'service': '腾讯云TTS',
                    'status': '服务不可用',
                    'message': '请配置TENCENTCLOUD_SECRET_ID和TENCENTCLOUD_SECRET_KEY环境变量',
                    'timestamp': datetime.now().isoformat()
                }), 503

            # 尝试合成一个测试文本
            test_text = "这是一个语音合成测试。"
            test_result = voice_service.text_to_speech(test_text, lang='zh', gender='female', speed=1.0)

            if test_result['success']:
                # 删除测试文件
                if os.path.exists(test_result['filepath']):
                    os.remove(test_result['filepath'])

                return jsonify({
                    'success': True,
                    'service': '腾讯云TTS',
                    'status': '服务正常',
                    'message': '语音合成测试成功',
                    'timestamp': datetime.now().isoformat()
                })
            else:
                return jsonify({
                    'success': False,
                    'service': '腾讯云TTS',
                    'status': '服务异常',
                    'message': test_result['message'],
                    'timestamp': datetime.now().isoformat()
                }), 500

        except Exception as e:
            logger.error(f"语音服务测试失败: {str(e)}")
            return jsonify({
                'success': False,
                'service': '腾讯云TTS',
                'status': '服务异常',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }), 500

    @app.route('/api/speech-to-text', methods=['POST'])
    def speech_to_text():
        """语音转文本接口"""
        try:
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': '请先登录', 'code': 401}), 401

            if 'audio' not in request.files:
                return jsonify({'success': False, 'message': '请上传音频文件'}), 400

            audio_file = request.files['audio']
            if audio_file.filename == '':
                return jsonify({'success': False, 'message': '请选择有效的音频文件'}), 400

            # 保存上传文件
            upload_folder = 'static/uploads/audio'
            os.makedirs(upload_folder, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"stt_{timestamp}_{audio_file.filename}"
            filepath = os.path.join(upload_folder, filename)
            audio_file.save(filepath)

            # 调用语音识别
            speech_service = get_speech_recognition_service()
            result = speech_service.transcribe(filepath)

            # 清理原始文件
            try:
                os.remove(filepath)
            except OSError:
                pass

            status_code = 200 if result.get('success') else 500
            return jsonify(result), status_code
        except Exception as e:
            logger.error(f"语音转文本失败: {e}", exc_info=True)
            return jsonify({'success': False, 'message': '语音转文本失败'}), 500

    @app.route('/api/speech-to-text/batch', methods=['POST'])
    def speech_to_text_batch():
        """批量语音转文本，支持多文件"""
        try:
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': '请先登录', 'code': 401}), 401
            files = request.files.getlist('audios')
            if not files:
                return jsonify({'success': False, 'message': '请上传音频文件'}), 400
            results = []
            speech_service = get_speech_recognition_service()
            upload_folder = 'static/uploads/audio'
            os.makedirs(upload_folder, exist_ok=True)
            for file in files:
                if not file.filename:
                    results.append({'filename': '', 'success': False, 'message': '文件名无效'})
                    continue
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filepath = os.path.join(upload_folder, f"stt_{timestamp}_{file.filename}")
                file.save(filepath)
                result = speech_service.transcribe(filepath)
                try:
                    os.remove(filepath)
                except OSError:
                    pass
                results.append({'filename': file.filename, **result})
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            logger.error(f"批量语音转文本失败: {e}", exc_info=True)
            return jsonify({'success': False, 'message': '批量语音转文本失败'}), 500

    # ==================== 翻译历史记录批量删除路由 ====================

    @app.route('/api/translate/history/batch-delete', methods=['DELETE'])
    def batch_delete_translation_history():
        """批量删除翻译历史，传递ids数组"""
        try:
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': '请先登录', 'code': 401}), 401
            data = request.get_json(silent=True) or {}
            ids = data.get('ids', [])
            if not isinstance(ids, list) or not ids:
                return jsonify({'success': False, 'message': '请提供要删除的ID列表', 'code': 400}), 400
            deleted = TranslationHistory.query.filter(
                TranslationHistory.user_id == session['user_id'],
                TranslationHistory.id.in_(ids)
            ).delete(synchronize_session=False)
            db.session.commit()
            return jsonify({'success': True, 'deleted_count': deleted})
        except Exception as e:
            db.session.rollback()
            logger.error(f"批量删除历史失败: {e}", exc_info=True)
            return jsonify({'success': False, 'message': f'删除失败: {e}', 'code': 500}), 500

    return app




if __name__ == '__main__':
    app = create_app()

    # 测试数据库连接
    from database import DatabaseManager

    print("=" * 60)
    print("🤖 智能文字翻译助手 - OCR功能")
    print("=" * 60)
    print("🔍 启动前数据库连接测试...")
    DatabaseManager.test_connection()

    print("\n📡 可用API端点:")
    print("  🔐 认证相关:")
    print("    POST /api/register     - 用户注册")
    print("    POST /api/login        - 用户登录")
    print("    GET  /api/logout       - 用户登出")
    print("    GET  /api/users        - 获取用户列表(测试)")
    print("  📷 OCR相关:")
    print("    POST /api/ocr/recognize - 图片文字识别")
    print("    POST /api/ocr/recognize/batch - 批量图片文字识别")
    print("    GET  /api/ocr/test      - OCR服务测试")
    print("  🌐 翻译相关:")
    print("    POST /api/translate      - 文本翻译")
    print("    GET  /api/translate/history - 翻译历史")
    print("    GET  /api/translate/history/<id> - 历史详情")
    print("    DELETE /api/translate/history/<id> - 删除历史")
    print("    DELETE /api/translate/history/clear - 清空历史")
    print("    DELETE /api/translate/history/batch-delete - 批量删除历史")
    print("  🔊 语音合成相关:")
    print("    POST /api/voice/synthesize - 文本转语音")
    print("    GET  /api/voice/languages  - 支持的语言")
    print("    GET  /api/voice/voices     - 支持的音色")
    print("    GET  /api/voice/test       - 测试服务状态")
    print("  🎤 语音识别相关:")
    print("    POST /api/speech-to-text   - 语音转文本")
    print("    POST /api/speech-to-text/batch - 批量语音转文本")
    print("  🌐 页面路由:")
    print("    GET  /                 - 首页(重定向到登录)")
    print("    GET  /register         - 注册页面")
    print("    GET  /login            - 登录页面")
    print("    GET  /main             - 主页面(需登录)")
    print("=" * 60)

    # 检查必要的服务和目录
    upload_dir = 'static/uploads'
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
        print(f"📁 创建上传目录: {upload_dir}")

    audio_dir = 'static/audio'
    if not os.path.exists(audio_dir):
        os.makedirs(audio_dir)
        print(f"🎵 创建音频目录: {audio_dir}")

    # 检查OCR服务
    try:
        from services.ocr_service import get_ocr_service

        ocr_service = get_ocr_service()
        print(f"✅ OCR服务初始化成功")
    except Exception as e:
        print(f"❌ OCR服务初始化失败: {e}")
        print("   请创建 services/ocr_service.py 文件")

    # 检查翻译服务
    try:
        from services.translation_service import get_translation_service

        translation_service = get_translation_service()
        print(f"✅ 翻译服务初始化成功")
    except Exception as e:
        print(f"❌ 翻译服务初始化失败: {e}")
        print("   请创建 services/translation_service.py 文件")

    # 检查语音合成服务
    try:
        from services.voice_service import get_voice_service
        voice_service = get_voice_service()
        if voice_service.is_available():
            print(f"✅ 语音合成服务初始化成功 (腾讯云TTS)")
        else:
            print(f"⚠️  语音合成服务未配置")
            print("   请设置TENCENTCLOUD_SECRET_ID和TENCENTCLOUD_SECRET_KEY环境变量")
    except Exception as e:
        print(f"❌ 语音合成服务初始化失败: {e}")

    print(f"🚀 启动Flask应用: http://{config.HOST}:{config.PORT}")
    print("=" * 60)

    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)

