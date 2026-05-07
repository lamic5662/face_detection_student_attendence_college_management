from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from services.ai_service import chat, generate_notice
from utils.tenancy import get_current_college

ai_bp = Blueprint('ai', __name__, url_prefix='/ai')


@ai_bp.route('/chat', methods=['POST'])
@login_required
def ai_chat():
    data = request.get_json(silent=True) or {}
    messages = data.get('messages', [])
    if not messages:
        return jsonify(error='No messages provided.'), 400

    # keep only last 10 turns to stay within token limits
    messages = messages[-10:]

    last_query = messages[-1].get('content', '') if messages else ''

    college = get_current_college(optional=True)
    college_id = college.id if college else None

    context = ''
    if college_id:
        try:
            from services.ai_context import build_context
            context = build_context(current_user, college_id, last_query)
        except Exception as exc:
            current_app_log(f'ai_context error: {exc}')

    try:
        reply = chat(messages, user_role=current_user.role, context=context)
        return jsonify(reply=reply)
    except RuntimeError as e:
        return jsonify(error=str(e)), 503
    except Exception as e:
        current_app_log(str(e))
        return jsonify(error='AI service error. Please try again.'), 500


@ai_bp.route('/generate-notice', methods=['POST'])
@login_required
def ai_generate_notice():
    if current_user.role not in ('admin', 'teacher', 'super_admin'):
        return jsonify(error='Not authorized.'), 403

    data = request.get_json(silent=True) or {}
    topic = (data.get('topic') or '').strip()
    if not topic:
        return jsonify(error='Topic is required.'), 400

    college = get_current_college(optional=True)
    college_name = college.name if college else 'the college'

    try:
        content = generate_notice(topic, college_name)
        return jsonify(content=content)
    except RuntimeError as e:
        return jsonify(error=str(e)), 503
    except Exception:
        return jsonify(error='AI service error. Please try again.'), 500


def current_app_log(msg: str) -> None:
    try:
        from flask import current_app
        current_app.logger.error(msg)
    except Exception:
        pass
