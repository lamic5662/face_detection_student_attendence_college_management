from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

help_bp = Blueprint('help', __name__)

ROLES_META = {
    'super_admin': {'color': 'dark', 'icon': 'bi-shield-lock-fill', 'label': 'Super Admin'},
    'admin':   {'color': 'primary',  'icon': 'bi-shield-fill-check', 'label': 'Administrator'},
    'teacher': {'color': 'success',  'icon': 'bi-person-badge-fill', 'label': 'Teacher'},
    'student': {'color': 'info',     'icon': 'bi-mortarboard-fill',  'label': 'Student'},
    'parent':  {'color': 'warning',  'icon': 'bi-house-heart-fill',  'label': 'Parent'},
}


@help_bp.route('/help')
@login_required
def guide():
    role = current_user.role
    active_role = role
    if role == 'super_admin':
        active_role = 'admin'
    if role in ('admin', 'super_admin'):
        roles = ['admin', 'teacher', 'student', 'parent']
    else:
        roles = [role]
    return render_template('help/guide.html',
                           roles=roles,
                           active_role=active_role,
                           meta=ROLES_META)


@help_bp.route('/help/<string:role_name>')
@login_required
def guide_role(role_name):
    if role_name not in ROLES_META:
        abort(404)
    if current_user.role not in ('admin', 'super_admin') and current_user.role != role_name:
        abort(403)
    roles = [role_name]
    if current_user.role in ('admin', 'super_admin'):
        roles = ['admin', 'teacher', 'student', 'parent']
    return render_template('help/guide.html',
                           roles=roles,
                           active_role=role_name,
                           meta=ROLES_META)
