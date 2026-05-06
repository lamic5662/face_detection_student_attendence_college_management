import csv
import io
import re

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for, jsonify, Response
from flask_login import current_user, login_required

from extensions import db
from models.college import College
from models.department import Department
from models.platform_audit import PlatformAuditLog
from models.setting import CollegeSetting
from models.student import Student
from models.subject import Subject
from models.teacher import Teacher
from models.user import User
from utils.decorators import super_admin_required
from utils.feature_access import (
    FEATURE_CATALOG,
    FEATURE_GROUPS,
    FEATURE_PRESETS,
    college_enabled_feature_count,
    college_feature_matrix,
    feature_count,
    normalize_feature_keys,
    preset_feature_keys,
    save_college_feature_access,
)
from utils.platform_audit import log_platform_action
from utils.platform_notifications import (
    dismiss_read_platform_notifications,
    mark_all_platform_notifications_read,
    platform_notification_payload,
)
from utils.system_setup import evaluate_production_setup

super_admin_bp = Blueprint('super_admin', __name__)
_STRONG_PASSWORD_RE = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^a-zA-Z0-9]).{8,}$'
)


def _college_status_rows():
    rows = []
    colleges = College.query.order_by(College.created_at.desc(), College.name.asc()).all()
    for college in colleges:
        report = evaluate_production_setup(current_app, college)
        rows.append({
            'college': college,
            'report': report,
            'students': Student.query.filter_by(college_id=college.id).count(),
            'teachers': Teacher.query.filter_by(college_id=college.id).count(),
            'subjects': Subject.query.filter_by(college_id=college.id).count(),
            'departments': Department.query.filter_by(college_id=college.id).count(),
            'admins': User.query.filter_by(college_id=college.id, role='admin').count(),
            'feature_matrix': college_feature_matrix(college.id),
            'enabled_features': college_enabled_feature_count(college.id),
        })
    return rows


def _get_college_or_404(college_id: int) -> College:
    college = db.session.get(College, college_id)
    if college is None:
        abort(404)
    return college


def _has_platform_admins(college_id: int) -> bool:
    return User.query.filter_by(college_id=college_id, role='super_admin', is_active=True).count() > 0


def _get_college_admin_or_404(college: College, admin_id: int) -> User:
    user = db.session.get(User, admin_id)
    if user is None or user.college_id != college.id or user.role != 'admin':
        abort(404)
    return user


def _active_admin_count(college_id: int) -> int:
    return User.query.filter_by(college_id=college_id, role='admin', is_active=True).count()


def _role_account_summary(college_id: int) -> list[dict]:
    roles = [
        ('admin', 'College Admins', 'bi-person-badge-fill'),
        ('teacher', 'Teachers', 'bi-person-workspace'),
        ('student', 'Students', 'bi-people-fill'),
        ('parent', 'Parents', 'bi-house-heart-fill'),
    ]
    summary = []
    for role, label, icon in roles:
        total = User.query.filter_by(college_id=college_id, role=role).count()
        active = User.query.filter_by(college_id=college_id, role=role, is_active=True).count()
        summary.append({
            'role': role,
            'label': label,
            'icon': icon,
            'total': total,
            'active': active,
            'inactive': total - active,
        })
    return summary


def _recent_platform_logs(limit: int = 8, college_id: int | None = None):
    query = PlatformAuditLog.query
    if college_id is not None:
        query = query.filter_by(college_id=college_id)
    return query.order_by(PlatformAuditLog.created_at.desc()).limit(limit).all()


def _audit_log_filters():
    college_id = request.values.get('college_id', type=int)
    action = (request.values.get('action') or '').strip()
    return college_id, action


def _filtered_audit_log_query(college_id: int | None, action: str):
    query = PlatformAuditLog.query
    if college_id:
        query = query.filter_by(college_id=college_id)
    if action:
        query = query.filter_by(action_key=action)
    return query


@super_admin_bp.route('/dashboard')
@login_required
@super_admin_required
def dashboard():
    setup_report = evaluate_production_setup(current_app)
    college_rows = _college_status_rows()

    stats = {
        'colleges': College.query.count(),
        'active_colleges': College.query.filter_by(is_active=True).count(),
        'college_admins': User.query.filter_by(role='admin').count(),
        'students': Student.query.count(),
        'teachers': Teacher.query.count(),
        'subjects': Subject.query.count(),
    }

    return render_template(
        'super_admin/dashboard.html',
        stats=stats,
        setup_report=setup_report,
        college_rows=college_rows[:8],
        recent_logs=_recent_platform_logs(),
    )


@super_admin_bp.route('/system-setup')
@login_required
@super_admin_required
def system_setup():
    setup_report = evaluate_production_setup(current_app)
    college_rows = _college_status_rows()
    return render_template(
        'super_admin/system_setup.html',
        setup_report=setup_report,
        college_rows=college_rows,
    )


@super_admin_bp.route('/colleges')
@login_required
@super_admin_required
def colleges():
    college_rows = _college_status_rows()
    return render_template(
        'super_admin/colleges.html',
        college_rows=college_rows,
        feature_catalog=FEATURE_CATALOG,
        feature_groups=FEATURE_GROUPS,
        feature_presets=FEATURE_PRESETS,
        feature_count=feature_count(),
    )


@super_admin_bp.route('/audit-logs')
@login_required
@super_admin_required
def audit_logs():
    college_id, action = _audit_log_filters()
    query = _filtered_audit_log_query(college_id, action)
    logs = query.order_by(PlatformAuditLog.created_at.desc()).limit(150).all()
    colleges = College.query.order_by(College.name.asc()).all()
    actions = [
        row[0]
        for row in db.session.query(PlatformAuditLog.action_key)
        .distinct()
        .order_by(PlatformAuditLog.action_key.asc())
        .all()
    ]
    return render_template(
        'super_admin/audit_logs.html',
        logs=logs,
        colleges=colleges,
        actions=actions,
        selected_college_id=college_id,
        selected_action=action,
    )


@super_admin_bp.route('/audit-logs/export')
@login_required
@super_admin_required
def export_audit_logs():
    college_id, action = _audit_log_filters()
    logs = (
        _filtered_audit_log_query(college_id, action)
        .order_by(PlatformAuditLog.created_at.desc())
        .limit(5000)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'id',
        'created_at',
        'actor_name',
        'actor_email',
        'college_name',
        'college_code',
        'action_key',
        'summary',
        'target_type',
        'target_id',
        'details',
    ])
    for log in logs:
        writer.writerow([
            log.id,
            log.created_at.isoformat() if log.created_at else '',
            log.actor.name if log.actor else 'System',
            log.actor.email if log.actor else '',
            log.college.name if log.college else 'Platform',
            log.college.code if log.college else '',
            log.action_key,
            log.summary,
            log.target_type or '',
            log.target_id or '',
            log.detail_json or '',
        ])

    filename_parts = ['platform-audit-logs']
    if college_id:
        filename_parts.append(f'college-{college_id}')
    if action:
        filename_parts.append(action.replace('.', '-'))
    filename = '-'.join(filename_parts) + '.csv'

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@super_admin_bp.route('/audit-logs/delete-filtered', methods=['POST'])
@login_required
@super_admin_required
def delete_filtered_audit_logs():
    college_id, action = _audit_log_filters()
    if not college_id and not action:
        flash('Apply at least one filter before deleting audit logs in bulk.', 'warning')
        return redirect(url_for('super_admin.audit_logs'))

    query = _filtered_audit_log_query(college_id, action)
    deleted_count = query.count()
    if deleted_count == 0:
        flash('No audit logs matched the selected filters.', 'warning')
        return redirect(url_for('super_admin.audit_logs', college_id=college_id, action=action))

    query.delete(synchronize_session=False)
    db.session.commit()
    flash(f'Deleted {deleted_count} filtered audit log entries.', 'success')
    return redirect(url_for('super_admin.audit_logs', college_id=college_id, action=action))


@super_admin_bp.route('/audit-logs/<int:log_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_audit_log(log_id: int):
    log = db.session.get(PlatformAuditLog, log_id)
    if log is None:
        abort(404)

    db.session.delete(log)
    db.session.commit()
    flash('Audit log entry deleted.', 'success')
    return redirect(url_for('super_admin.audit_logs'))


@super_admin_bp.route('/notifications/feed')
@login_required
@super_admin_required
def notifications_feed():
    return jsonify(platform_notification_payload(current_user))


@super_admin_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
@super_admin_required
def notifications_mark_all_read():
    marked_count = mark_all_platform_notifications_read(current_user)
    payload = platform_notification_payload(current_user)
    payload['marked_count'] = marked_count
    return jsonify(payload)


@super_admin_bp.route('/notifications/delete-read', methods=['POST'])
@login_required
@super_admin_required
def notifications_delete_read():
    deleted_count = dismiss_read_platform_notifications(current_user)
    payload = platform_notification_payload(current_user)
    payload['deleted_count'] = deleted_count
    return jsonify(payload)


@super_admin_bp.route('/colleges/<int:college_id>')
@login_required
@super_admin_required
def college_detail(college_id: int):
    college = _get_college_or_404(college_id)
    setup_report = evaluate_production_setup(current_app, college)
    role_summary = _role_account_summary(college.id)
    feature_matrix = college_feature_matrix(college.id)
    enabled_feature_keys = [key for key, enabled in feature_matrix.items() if enabled]
    disabled_feature_keys = [key for key, enabled in feature_matrix.items() if not enabled]
    college_admins = (
        User.query
        .filter_by(college_id=college.id, role='admin')
        .order_by(User.is_active.desc(), User.created_at.desc())
        .all()
    )

    stats = {
        'departments': Department.query.filter_by(college_id=college.id).count(),
        'subjects': Subject.query.filter_by(college_id=college.id).count(),
        'teachers': Teacher.query.filter_by(college_id=college.id).count(),
        'students': Student.query.filter_by(college_id=college.id).count(),
        'parents': User.query.filter_by(college_id=college.id, role='parent').count(),
        'enabled_features': len(enabled_feature_keys),
        'total_features': feature_count(),
        'active_users': User.query.filter_by(college_id=college.id, is_active=True).count(),
        'inactive_users': User.query.filter_by(college_id=college.id, is_active=False).count(),
        'total_users': User.query.filter_by(college_id=college.id).count(),
    }

    return render_template(
        'super_admin/college_detail.html',
        college=college,
        setup_report=setup_report,
        role_summary=role_summary,
        stats=stats,
        college_admins=college_admins,
        enabled_feature_keys=enabled_feature_keys,
        disabled_feature_keys=disabled_feature_keys,
        feature_catalog=FEATURE_CATALOG,
        recent_logs=_recent_platform_logs(limit=10, college_id=college.id),
    )


@super_admin_bp.route('/colleges/create', methods=['POST'])
@login_required
@super_admin_required
def create_college():
    name = (request.form.get('name') or '').strip()
    code = (request.form.get('code') or '').strip().upper()
    subdomain = (request.form.get('subdomain') or '').strip().lower() or None

    if not name or not code:
        flash('College name and code are required.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    if College.query.filter_by(code=code).first():
        flash(f'College code {code} already exists.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    if subdomain and College.query.filter_by(subdomain=subdomain).first():
        flash(f'Subdomain {subdomain} already exists.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    college = College(name=name, code=code, subdomain=subdomain, is_active=True)
    db.session.add(college)
    db.session.flush()
    db.session.add(CollegeSetting(college_id=college.id, college_name=name))
    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college.created',
        summary=f'Created college {name} [{code}]',
        college=college,
        target_type='college',
        target_id=college.id,
        details={'name': name, 'code': code, 'subdomain': subdomain},
    ))
    db.session.commit()

    flash(f'College {name} [{code}] created successfully.', 'success')
    return redirect(url_for('super_admin.colleges'))


@super_admin_bp.route('/colleges/<int:college_id>/edit', methods=['POST'])
@login_required
@super_admin_required
def edit_college(college_id: int):
    college = _get_college_or_404(college_id)
    previous_name = college.name
    name = (request.form.get('name') or '').strip()
    code = (request.form.get('code') or '').strip().upper()
    subdomain = (request.form.get('subdomain') or '').strip().lower() or None

    if not name or not code:
        flash('College name and code are required.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    existing_code = College.query.filter(College.code == code, College.id != college.id).first()
    if existing_code:
        flash(f'College code {code} already exists.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    existing_subdomain = (
        College.query
        .filter(College.subdomain == subdomain, College.id != college.id)
        .first()
        if subdomain else None
    )
    if existing_subdomain:
        flash(f'Subdomain {subdomain} already exists.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    if _has_platform_admins(college.id) and college.code != code:
        flash('You cannot change the code of a college that hosts active super admin accounts.', 'warning')
        return redirect(url_for('super_admin.colleges'))

    college.name = name
    college.code = code
    college.subdomain = subdomain

    setting = CollegeSetting.get(college)
    if not setting.college_name or setting.college_name == previous_name:
        setting.college_name = name

    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college.updated',
        summary=f'Updated college {college.name} [{college.code}]',
        college=college,
        target_type='college',
        target_id=college.id,
        details={
            'previous_name': previous_name,
            'name': name,
            'code': code,
            'subdomain': subdomain,
        },
    ))
    db.session.commit()
    flash(f'College {name} updated successfully.', 'success')
    return redirect(url_for('super_admin.colleges'))


@super_admin_bp.route('/colleges/<int:college_id>/toggle', methods=['POST'])
@login_required
@super_admin_required
def toggle_college(college_id: int):
    college = _get_college_or_404(college_id)

    if college.is_active and _has_platform_admins(college.id):
        flash('You cannot deactivate a college that contains active super admin accounts.', 'warning')
        return redirect(url_for('super_admin.colleges'))

    college.is_active = not college.is_active
    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college.toggled',
        summary=f"{'Activated' if college.is_active else 'Deactivated'} college {college.name} [{college.code}]",
        college=college,
        target_type='college',
        target_id=college.id,
        details={'is_active': college.is_active},
    ))
    db.session.commit()
    flash(
        f"College {college.name} is now {'active' if college.is_active else 'inactive'}.",
        'success',
    )
    return redirect(url_for('super_admin.colleges'))


@super_admin_bp.route('/colleges/<int:college_id>/admins/create', methods=['POST'])
@login_required
@super_admin_required
def create_college_admin(college_id: int):
    college = _get_college_or_404(college_id)
    name = (request.form.get('name') or '').strip()
    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''

    if not name or not email or not password:
        flash('Admin name, email, and password are required.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    if User.query.filter_by(college_id=college.id, email=email).first():
        flash(f'An account with {email} already exists in {college.name}.', 'danger')
        return redirect(url_for('super_admin.colleges'))

    user = User(
        college_id=college.id,
        name=name,
        email=email,
        role='admin',
        is_active=True,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college_admin.created',
        summary=f'Created college admin {email} for {college.name}',
        college=college,
        target_type='user',
        target_id=user.id,
        details={'email': email, 'name': name},
    ))
    db.session.commit()

    flash(f'College admin {email} created for {college.name}.', 'success')
    return redirect(url_for('super_admin.colleges'))


@super_admin_bp.route('/colleges/<int:college_id>/features', methods=['POST'])
@login_required
@super_admin_required
def update_college_features(college_id: int):
    college = _get_college_or_404(college_id)
    preset = (request.form.get('preset') or '').strip()

    if preset:
        enabled_keys = preset_feature_keys(preset)
        preset_label = FEATURE_PRESETS.get(preset, {}).get('label', 'preset')
    else:
        enabled_keys = normalize_feature_keys(request.form.getlist('enabled_features'))
        preset_label = None

    save_college_feature_access(college.id, enabled_keys)
    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college.features_updated',
        summary=f'Updated feature access for {college.name}',
        college=college,
        target_type='college',
        target_id=college.id,
        details={
            'preset': preset or None,
            'enabled_features': enabled_keys,
        },
    ))
    db.session.commit()

    if preset_label:
        flash(f'{preset_label} applied to {college.name}.', 'success')
    else:
        flash(f'Feature access updated for {college.name}.', 'success')
    return redirect(url_for('super_admin.colleges'))


@super_admin_bp.route('/colleges/<int:college_id>/admins/<int:admin_id>/toggle', methods=['POST'])
@login_required
@super_admin_required
def toggle_college_admin(college_id: int, admin_id: int):
    college = _get_college_or_404(college_id)
    admin = _get_college_admin_or_404(college, admin_id)

    if admin.is_active and college.is_active and _active_admin_count(college.id) <= 1:
        flash('You cannot deactivate the last active college admin for an active college.', 'warning')
        return redirect(url_for('super_admin.college_detail', college_id=college.id))

    admin.is_active = not admin.is_active
    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college_admin.toggled',
        summary=f"{'Activated' if admin.is_active else 'Deactivated'} college admin {admin.email}",
        college=college,
        target_type='user',
        target_id=admin.id,
        details={'email': admin.email, 'is_active': admin.is_active},
    ))
    db.session.commit()
    flash(
        f"College admin {'activated' if admin.is_active else 'deactivated'}: {admin.email}",
        'success',
    )
    return redirect(url_for('super_admin.college_detail', college_id=college.id))


@super_admin_bp.route('/colleges/<int:college_id>/admins/<int:admin_id>/reset-password', methods=['POST'])
@login_required
@super_admin_required
def reset_college_admin_password(college_id: int, admin_id: int):
    college = _get_college_or_404(college_id)
    admin = _get_college_admin_or_404(college, admin_id)
    new_password = (request.form.get('new_password') or '').strip()

    if not _STRONG_PASSWORD_RE.match(new_password):
        flash(
            'Password must be at least 8 characters and include uppercase, lowercase, a digit, and a special character.',
            'danger',
        )
        return redirect(url_for('super_admin.college_detail', college_id=college.id))

    admin.set_password(new_password)
    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college_admin.password_reset',
        summary=f'Reset password for college admin {admin.email}',
        college=college,
        target_type='user',
        target_id=admin.id,
        details={'email': admin.email},
    ))
    db.session.commit()
    flash(f'Password reset for {admin.email}.', 'success')
    return redirect(url_for('super_admin.college_detail', college_id=college.id))


@super_admin_bp.route('/colleges/<int:college_id>/admins/<int:admin_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_college_admin(college_id: int, admin_id: int):
    college = _get_college_or_404(college_id)
    admin = _get_college_admin_or_404(college, admin_id)

    if college.is_active and _active_admin_count(college.id) <= 1 and admin.is_active:
        flash('You cannot remove the last active college admin while the college is active.', 'warning')
        return redirect(url_for('super_admin.college_detail', college_id=college.id))

    email = admin.email
    db.session.add(log_platform_action(
        actor=current_user,
        action_key='college_admin.deleted',
        summary=f'Removed college admin {email}',
        college=college,
        target_type='user',
        target_id=admin.id,
        details={'email': email},
    ))
    db.session.delete(admin)
    db.session.commit()
    flash(f'College admin removed: {email}', 'success')
    return redirect(url_for('super_admin.college_detail', college_id=college.id))
