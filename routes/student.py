import os
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, jsonify, current_app, send_file, abort)
from flask_login import login_required, current_user
from extensions import db, csrf, limiter, mail
from flask_mail import Message
import threading
from math import radians, cos, sin, asin, sqrt
from models.attendance import AttendanceSession, AttendanceRecord
from models.subject import Subject
from models.notice import Notice
from models.exam import Exam, Mark
from models.fee import FeeStructure, FeePayment
from models.location import StudentLocation
from models.parent import TeacherStatus
from models.content import TeacherContent, content_extension, is_allowed_content_upload
from models.assignment import AssignmentSubmission
from models.timetable import TimetableSlot
from utils.decorators import student_required
from services.face_service import (decode_base64_image, extract_face_encoding,
                                    average_encodings, save_face_image)
from services.report_service import (generate_student_report, dataframe_to_excel_bytes,
                                      dataframe_to_csv_bytes)
from datetime import date, datetime, timedelta
import io
from werkzeug.utils import secure_filename
from utils.content_storage import resolve_content_path
from utils.assignment_storage import build_submission_relpath, resolve_submission_path
from utils.dashboard import build_dashboard_preferences
from utils.time import utc_now_naive

student_bp = Blueprint('student', __name__)


def _current_student():
    return current_user.student_profile


def _content_for_student(cid: int, student):
    return TeacherContent.query.filter_by(
        id=cid,
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
        is_published=True,
    ).first_or_404()


def _assignment_for_student(cid: int, student):
    return TeacherContent.query.filter_by(
        id=cid,
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
        is_published=True,
        content_type='assignment',
    ).first_or_404()


def _submission_upload(student_id: int):
    submission_file = request.files.get('submission_file')
    if not submission_file or not submission_file.filename:
        return None
    if not is_allowed_content_upload(submission_file.filename):
        flash(
            'Unsupported submission type. Allowed: PDF, Office docs, spreadsheets, text, and safe images.',
            'danger',
        )
        return False

    upload_dir = current_app.config['ASSIGNMENT_UPLOAD_FOLDER']
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(secure_filename(submission_file.filename))[1].lower()
    fname = f'{student_id}_{utc_now_naive().strftime("%Y%m%d%H%M%S%f")}{ext}'
    submission_file.save(os.path.join(upload_dir, fname))
    return build_submission_relpath(fname)


@student_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    dashboard_prefs = build_dashboard_preferences(current_user)
    student = _current_student()
    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester
    ).all()

    subject_attendance = []
    for sub in subjects:
        pct = student.get_attendance_percentage(subject_id=sub.id)
        total_sessions = AttendanceSession.query.filter_by(
            college_id=student.college_id,
            subject_id=sub.id, status='completed'
        ).count()
        present_count = AttendanceRecord.query.join(AttendanceSession).filter(
            AttendanceRecord.college_id == student.college_id,
            AttendanceRecord.student_id == student.id,
            AttendanceSession.college_id == student.college_id,
            AttendanceSession.subject_id == sub.id,
            AttendanceSession.status == 'completed',
            AttendanceRecord.status == 'present'
        ).count()
        threshold = current_app.config['LOW_ATTENDANCE_THRESHOLD']
        subject_attendance.append({
            'subject': sub,
            'percentage': pct,
            'total': total_sessions,
            'present': present_count,
            'absent': total_sessions - present_count,
            'low': pct < threshold,
        })

    overall_pct = student.get_attendance_percentage()
    recent_records = AttendanceRecord.query.join(AttendanceSession).filter(
        AttendanceRecord.college_id == student.college_id,
        AttendanceRecord.student_id == student.id
    ).order_by(AttendanceSession.date.desc()).limit(10).all()

    today = date.today()

    # Upcoming exams (next 7 days) for student's dept+semester
    subject_ids = [s['subject'].id for s in subject_attendance]
    upcoming_exams = Exam.query.filter(
        Exam.college_id == student.college_id,
        Exam.subject_id.in_(subject_ids),
        Exam.exam_date >= today,
        Exam.exam_date <= today + timedelta(days=7)
    ).order_by(Exam.exam_date).all() if subject_ids else []

    # Fee summary
    structures = FeeStructure.query.filter(
        FeeStructure.college_id == student.college_id,
        db.or_(FeeStructure.department_id == student.department_id,
               FeeStructure.department_id == None),
        db.or_(FeeStructure.semester == student.semester,
               FeeStructure.semester == None),
        FeeStructure.is_active == True
    ).all()
    paid_map = {p.fee_structure_id: p for p in
                FeePayment.query.filter_by(college_id=student.college_id, student_id=student.id).all()}
    total_due = sum(
        max(fs.amount - (paid_map[fs.id].amount_paid if fs.id in paid_map else 0), 0)
        for fs in structures
    )

    # Recent notices
    notices = Notice.query.filter(
        Notice.college_id == student.college_id,
        Notice.target_role.in_(['all', 'student']),
        db.or_(Notice.expires_at == None, Notice.expires_at > utc_now_naive())
    ).order_by(Notice.is_pinned.desc(), Notice.created_at.desc()).limit(3).all()

    today_slots = TimetableSlot.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
        day_of_week=today.weekday(),
    ).order_by(TimetableSlot.period_no).all()
    slot_statuses = []
    for slot in today_slots:
        teacher_status = None
        if slot.subject and slot.subject.teacher:
            teacher_status = TeacherStatus.query.filter_by(
                college_id=student.college_id,
                teacher_id=slot.subject.teacher.id,
            ).first()
        session_started = None
        if slot.subject:
            session_started = AttendanceSession.query.filter(
                AttendanceSession.college_id == student.college_id,
                AttendanceSession.subject_id == slot.subject_id,
                AttendanceSession.date == today,
                AttendanceSession.status.in_(['active', 'completed']),
            ).first()
        slot_statuses.append({
            'slot': slot,
            'teacher_status': teacher_status,
            'session_started': session_started,
        })

    location = StudentLocation.query.filter_by(college_id=student.college_id, student_id=student.id).first()

    return render_template('student/dashboard.html',
                           dashboard_prefs=dashboard_prefs,
                           student=student,
                           subject_attendance=subject_attendance,
                           overall_pct=overall_pct,
                           recent_records=recent_records,
                           threshold=current_app.config['LOW_ATTENDANCE_THRESHOLD'],
                           upcoming_exams=upcoming_exams,
                           total_fee_due=total_due,
                           notices=notices,
                           slot_statuses=slot_statuses,
                           location=location,
                           today=today)


@student_bp.route('/attendance')
@login_required
@student_required
def my_attendance():
    student = _current_student()
    subject_id = request.args.get('subject_id', type=int)
    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester
    ).all()

    records = []
    if subject_id:
        records = AttendanceRecord.query.join(AttendanceSession).filter(
            AttendanceRecord.college_id == student.college_id,
            AttendanceRecord.student_id == student.id,
            AttendanceSession.college_id == student.college_id,
            AttendanceSession.subject_id == subject_id,
            AttendanceSession.status == 'completed'
        ).order_by(AttendanceSession.date.desc()).all()

    return render_template('student/my_attendance.html',
                           student=student, subjects=subjects,
                           records=records,
                           selected_subject_id=subject_id)


# ─── Profile ────────────────────────────────────────────────────────────────

@student_bp.route('/profile')
@login_required
@student_required
def profile():
    student = _current_student()
    subjects = Subject.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester
    ).all()
    chart_data = []
    for sub in subjects:
        total = AttendanceSession.query.filter_by(
            college_id=student.college_id,
            subject_id=sub.id, status='completed'
        ).count()
        present = AttendanceRecord.query.join(AttendanceSession).filter(
            AttendanceRecord.college_id == student.college_id,
            AttendanceRecord.student_id == student.id,
            AttendanceSession.college_id == student.college_id,
            AttendanceSession.subject_id == sub.id,
            AttendanceSession.status == 'completed',
            AttendanceRecord.status == 'present'
        ).count()
        chart_data.append({
            'subject': sub.name,
            'code': sub.code,
            'present': present,
            'absent': total - present,
            'total': total,
            'percentage': round(present / total * 100, 1) if total > 0 else 0,
        })
    return render_template('student/profile.html',
                           student=student, chart_data=chart_data,
                           threshold=current_app.config['LOW_ATTENDANCE_THRESHOLD'])


# ─── Face Enrollment ─────────────────────────────────────────────────────────

@student_bp.route('/attendance/download')
@login_required
@student_required
def download_attendance():
    student = _current_student()
    subject_id = request.args.get('subject_id', type=int)
    fmt = request.args.get('fmt', 'excel')
    df = generate_student_report(student.id, subject_id)
    filename = f"attendance_{student.roll_number}"
    if subject_id:
        sub = db.session.get(Subject, subject_id)
        if sub:
            if sub.college_id != student.college_id:
                abort(404)
            filename += f"_{sub.code}"
    if fmt == 'csv':
        return send_file(
            io.BytesIO(dataframe_to_csv_bytes(df)),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"{filename}.csv"
        )
    return send_file(
        io.BytesIO(dataframe_to_excel_bytes(df, 'My Attendance')),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f"{filename}.xlsx"
    )


@student_bp.route('/enroll')
@login_required
@student_required
def enroll():
    student = _current_student()
    return render_template('student/enroll.html', student=student)


@student_bp.route('/enroll/capture', methods=['POST'])
@csrf.exempt
@limiter.limit('20 per minute', methods=['POST'])
@login_required
@student_required
def capture_face():
    """Accept up to 5 base64 frames, extract encodings, average and store."""
    student = _current_student()
    data = request.get_json(silent=True) or {}
    frames_b64 = data.get('frames', [])

    if not frames_b64:
        return jsonify({'success': False, 'message': 'No frames received'}), 400
    if not isinstance(frames_b64, list):
        return jsonify({'success': False, 'message': 'Invalid frame payload'}), 400
    if len(frames_b64) > 5:
        return jsonify({'success': False, 'message': 'Too many frames submitted'}), 400

    encodings = []
    for b64 in frames_b64:
        frame = decode_base64_image(b64)
        if frame is None:
            continue
        enc = extract_face_encoding(frame)
        if enc is not None:
            encodings.append(enc)

    if not encodings:
        return jsonify({'success': False, 'message': 'No face detected in captured images. Ensure good lighting and face the camera directly.'}), 400

    avg_encoding = average_encodings(encodings)
    student.set_face_encoding(avg_encoding)

    # Save best frame as profile image
    first_frame = decode_base64_image(frames_b64[0])
    if first_frame is not None:
        upload_folder = current_app.config['UPLOAD_FOLDER']
        image_path = save_face_image(first_frame, student.roll_number, upload_folder)
        student.face_image_path = image_path

    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Face enrolled successfully from {len(encodings)} sample(s).',
        'samples': len(encodings),
    })


@student_bp.route('/enroll/delete', methods=['POST'])
@csrf.exempt
@login_required
@student_required
def delete_face():
    student = _current_student()
    student.face_encoding = None
    student.face_image_path = None
    db.session.commit()
    flash('Face data removed. You can re-enroll anytime.', 'info')
    return redirect(url_for('student.enroll'))


# ─── Location Sharing ─────────────────────────────────────────────────────────

@student_bp.route('/location/toggle', methods=['POST'])
@login_required
@student_required
def location_toggle():
    student = _current_student()
    loc = StudentLocation.query.filter_by(college_id=student.college_id, student_id=student.id).first()
    if not loc:
        loc = StudentLocation(college_id=student.college_id, student_id=student.id, is_sharing=False)
        db.session.add(loc)
    loc.is_sharing = not loc.is_sharing
    if not loc.is_sharing:
        loc.latitude = None
        loc.longitude = None
        loc.accuracy = None
    db.session.commit()
    status = 'enabled' if loc.is_sharing else 'disabled'
    flash(f'Location sharing {status}.', 'success')
    return redirect(url_for('student.dashboard'))


def _haversine_m(lat1, lon1, lat2, lon2):
    """Return distance in metres between two GPS coordinates."""
    R = 6_371_000
    p1, p2 = radians(lat1), radians(lat2)
    dp = radians(lat2 - lat1)
    dl = radians(lon2 - lon1)
    a = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return R * 2 * asin(sqrt(a))


def _send_arrival_email(app, student_name, student_roll, college_name, arrival_time, parent_emails):
    """Send arrival notification emails in a background thread."""
    with app.app_context():
        subject = f"✅ {student_name} has arrived at {college_name}"
        html = f"""
<div style="font-family:Inter,Arial,sans-serif;max-width:520px;margin:0 auto;background:#f8f9fa;padding:24px;border-radius:12px">
  <div style="background:linear-gradient(135deg,#0d6efd,#6610f2);padding:28px 24px;border-radius:10px 10px 0 0;text-align:center">
    <div style="font-size:40px;margin-bottom:8px">🏫</div>
    <h1 style="color:#fff;margin:0;font-size:22px;font-weight:700">Arrived at College</h1>
  </div>
  <div style="background:#fff;padding:24px 28px;border-radius:0 0 10px 10px;border:1px solid #dee2e6;border-top:none">
    <p style="margin:0 0 16px;color:#212529;font-size:15px">
      Your ward <strong>{student_name}</strong> ({student_roll}) has <strong>arrived at {college_name}</strong>.
    </p>
    <div style="background:#f0fff4;border:1px solid #b7ebc8;border-radius:8px;padding:16px;text-align:center;margin:20px 0">
      <div style="font-size:28px;font-weight:700;color:#198754">{arrival_time}</div>
      <div style="color:#6c757d;font-size:13px;margin-top:4px">Arrival Time</div>
    </div>
    <p style="color:#6c757d;font-size:12px;margin:0;border-top:1px solid #f0f0f0;padding-top:14px">
      This is an automated notification from <strong>SmartAttend</strong>. One email is sent per day when your child enters the college campus.
    </p>
  </div>
</div>"""
        for email_addr, parent_name in parent_emails:
            try:
                msg = Message(subject=subject, recipients=[email_addr], html=html)
                mail.send(msg)
                app.logger.info('Arrival email sent to %s for student %s', email_addr, student_name)
            except Exception as exc:
                app.logger.error('Arrival email failed for %s: %s', email_addr, exc)


ARRIVAL_RADIUS_M = 300  # metres — student considered "at college" within this distance


@student_bp.route('/location/update', methods=['POST'])
@csrf.exempt
@limiter.exempt
@login_required
@student_required
def location_update():
    from datetime import datetime, date
    from models.parent import ParentStudent
    from models.user import User
    from models.setting import CollegeSetting

    student = _current_student()
    data = request.get_json(silent=True) or {}
    lat = data.get('lat')
    lng = data.get('lng')
    acc = data.get('accuracy')

    if lat is None or lng is None:
        return jsonify(ok=False, error='Missing coordinates'), 400

    try:
        lat, lng = float(lat), float(lng)
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError
    except (ValueError, TypeError):
        return jsonify(ok=False, error='Invalid coordinates'), 400

    loc = StudentLocation.query.filter_by(college_id=student.college_id, student_id=student.id).first()
    if not loc:
        loc = StudentLocation(college_id=student.college_id, student_id=student.id, is_sharing=True)
        db.session.add(loc)

    if not loc.is_sharing:
        return jsonify(ok=False, error='Sharing is disabled'), 403

    loc.latitude = lat
    loc.longitude = lng
    loc.accuracy = float(acc) if acc is not None else None
    loc.updated_at = utc_now_naive()

    # ── Arrival detection ────────────────────────────────────────────────────
    today = date.today()
    cs = CollegeSetting.get()
    college_lat = cs.latitude or current_app.config['COLLEGE_LAT']
    college_lng = cs.longitude or current_app.config['COLLEGE_LNG']
    college_name = cs.college_name or current_app.config.get('COLLEGE_NAME', 'College')

    dist = _haversine_m(lat, lng, college_lat, college_lng)
    should_notify = (dist <= ARRIVAL_RADIUS_M) and (loc.last_arrival_date != today)

    if should_notify:
        loc.last_arrival_date = today
        db.session.commit()  # commit before spawning thread to avoid duplicate sends

        # Gather parent emails
        links = ParentStudent.query.filter_by(student_id=student.id).all()
        parent_emails = []
        for link in links:
            parent_user = db.session.get(User, link.parent_id)
            if parent_user and parent_user.email:
                parent_emails.append((parent_user.email, parent_user.name))

        if parent_emails:
            arrival_time = datetime.now().strftime('%I:%M %p')
            app = current_app._get_current_object()
            t = threading.Thread(
                target=_send_arrival_email,
                args=(app, student.user.name, student.roll_number,
                      college_name, arrival_time, parent_emails),
                daemon=True
            )
            t.start()
    else:
        db.session.commit()

    return jsonify(ok=True, distance_m=round(dist), at_college=dist <= ARRIVAL_RADIUS_M)


# ─── Digital ID Card ──────────────────────────────────────────────────────────

@student_bp.route('/id-card', methods=['GET', 'POST'])
@login_required
@student_required
def id_card():
    from models.id_card import IDCardTemplate, StudentIDCard
    from models.setting import CollegeSetting
    from werkzeug.utils import secure_filename
    import os

    student = _current_student()
    tpl     = IDCardTemplate.get(student.college)
    cs      = CollegeSetting.get()
    card    = student.id_card  # may be None

    if request.method == 'POST':
        action = request.form.get('action', 'submit')

        if action == 'submit':
            # Update missing profile fields while we're here
            if request.form.get('dob'):
                try:
                    student.dob = datetime.strptime(request.form['dob'], '%Y-%m-%d').date()
                except ValueError:
                    pass
            if request.form.get('blood_group'):
                student.blood_group = request.form['blood_group'].strip()
            if request.form.get('phone'):
                student.phone = request.form['phone'].strip()
            if request.form.get('address'):
                student.address = request.form['address'].strip()
            if request.form.get('parent_name'):
                student.parent_name = request.form['parent_name'].strip()
            if request.form.get('parent_phone'):
                student.parent_phone = request.form['parent_phone'].strip()

            photo = request.files.get('id_photo')
            photo_path = card.photo_path if card else None
            if photo and photo.filename:
                college_slug = secure_filename((student.college.code or f'college-{student.college_id}').lower()) or f'college-{student.college_id}'
                rel_dir = os.path.join('uploads', 'id_photos', college_slug)
                upload_dir = os.path.join(current_app.root_path, 'static', rel_dir)
                os.makedirs(upload_dir, exist_ok=True)
                fname = secure_filename(f"{student.roll_number}_id.jpg")
                photo.save(os.path.join(upload_dir, fname))
                photo_path = f'{rel_dir}/{fname}'

            if card:
                card.photo_path   = photo_path
                card.status       = 'pending'
                card.rejection_note = None
                card.submitted_at = utc_now_naive()
            else:
                card = StudentIDCard(
                    college_id=student.college_id,
                    student_id=student.id,
                    photo_path=photo_path,
                    status='pending',
                )
                db.session.add(card)

            db.session.commit()
            flash('Your ID card request has been submitted for admin review.', 'success')
            return redirect(url_for('student.id_card'))

    from utils.qr_utils import make_id_card_qr, get_map_tile_b64
    qr_img  = make_id_card_qr(student, card) if card else None
    map_url = (get_map_tile_b64(tpl.map_lat, tpl.map_lng)
               if tpl.map_lat is not None and tpl.map_lng is not None else None)
    return render_template('student/id_card.html',
                           student=student, tpl=tpl, cs=cs, card=card,
                           qr_img=qr_img, map_url=map_url)


@student_bp.route('/content')
@login_required
@student_required
def student_content():
    from models.subject import Subject as Subj
    student     = _current_student()
    type_filter = request.args.get('type', '')
    subj_filter = request.args.get('subject', 0, type=int)
    q           = request.args.get('q', '').strip()
    page        = request.args.get('page', 1, type=int)

    base = TeacherContent.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester,
        is_published=True
    )
    query = base
    if type_filter in ('note', 'assignment', 'lab', 'question'):
        query = query.filter_by(content_type=type_filter)
    if subj_filter:
        query = query.filter_by(subject_id=subj_filter)
    if q:
        query = query.filter(TeacherContent.title.ilike(f'%{q}%'))

    pagination = query.order_by(TeacherContent.created_at.desc()).paginate(
        page=page, per_page=12, error_out=False)

    subjects = Subj.query.filter_by(
        college_id=student.college_id,
        department_id=student.department_id,
        semester=student.semester
    ).order_by(Subj.name).all()

    counts = {
        'all':        base.count(),
        'note':       base.filter_by(content_type='note').count(),
        'assignment': base.filter_by(content_type='assignment').count(),
        'lab':        base.filter_by(content_type='lab').count(),
        'question':   base.filter_by(content_type='question').count(),
    }
    assignment_ids = [item.id for item in pagination.items if item.content_type == 'assignment']
    submission_map = {}
    if assignment_ids:
        submission_map = {
            submission.content_id: submission
            for submission in AssignmentSubmission.query.filter(
                AssignmentSubmission.college_id == student.college_id,
                AssignmentSubmission.student_id == student.id,
                AssignmentSubmission.content_id.in_(assignment_ids),
            ).all()
        }
    return render_template('student/content.html',
                           pagination=pagination, items=pagination.items,
                           subjects=subjects, counts=counts,
                           type_filter=type_filter, subj_filter=subj_filter, q=q,
                           submission_map=submission_map)


@student_bp.route('/content/<int:cid>/file')
@login_required
@student_required
def content_file(cid):
    student = _current_student()
    item = _content_for_student(cid, student)
    if not item.file_path:
        abort(404)

    abs_path = resolve_content_path(current_app, item.file_path)
    if not abs_path or not os.path.isfile(abs_path):
        abort(404)

    return send_file(
        abs_path,
        as_attachment=request.args.get('download', '1') != '0',
        download_name=os.path.basename(item.file_path),
        conditional=True,
    )


@student_bp.route('/content/<int:cid>/preview')
@login_required
@student_required
def content_preview(cid):
    import html
    from utils.file_preview import (
        pptx_to_html,
        docx_to_html,
        preview_exception_message,
        infer_preview_type,
    )

    student = _current_student()
    item = _content_for_student(cid, student)

    abs_path = resolve_content_path(current_app, item.file_path) if item.file_path else None
    ext = infer_preview_type(item.file_path, abs_path)
    file_url = url_for('student.content_file', cid=item.id, download=0) if item.file_path else None
    download_url = url_for('student.content_file', cid=item.id) if item.file_path else None

    show_note_body = item.content_type == 'note' and bool(item.body)
    preview_type = ext
    preview_html = None
    error        = None

    if item.file_path:
        if not abs_path or not os.path.isfile(abs_path):
            error = 'Attached file is missing from the server.'
        elif ext == 'pptx':
            try:
                preview_html = pptx_to_html(abs_path)
            except Exception as e:
                error = preview_exception_message(ext, e)
        elif ext in ('docx', 'doc'):
            try:
                preview_html = docx_to_html(abs_path)
            except Exception as e:
                error = preview_exception_message(ext, e)
        elif ext in ('txt', 'csv'):
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='replace') as fh:
                    preview_html = f"<pre class=\"text-file-preview mb-0\">{html.escape(fh.read())}</pre>"
            except Exception as e:
                error = preview_exception_message(ext, e)
    else:
        preview_type = 'content'

    student_submission = None
    if item.content_type == 'assignment':
        student_submission = AssignmentSubmission.query.filter_by(
            college_id=student.college_id,
            content_id=item.id,
            student_id=student.id,
        ).first()

    return render_template('student/content_preview.html',
                           item=item, preview_type=preview_type,
                           file_url=file_url, download_url=download_url,
                           preview_html=preview_html, error=error,
                           show_note_body=show_note_body,
                           student_submission=student_submission)


@student_bp.route('/assignments/<int:cid>/submit', methods=['POST'])
@login_required
@student_required
def submit_assignment(cid):
    student = _current_student()
    item = _assignment_for_student(cid, student)

    submission_text = request.form.get('submission_text', '').strip()
    file_path = _submission_upload(student.id)
    if file_path is False:
        return redirect(url_for('student.content_preview', cid=item.id))

    submission = AssignmentSubmission.query.filter_by(
        college_id=student.college_id,
        content_id=item.id,
        student_id=student.id,
    ).first()

    if submission is None:
        submission = AssignmentSubmission(
            college_id=student.college_id,
            content_id=item.id,
            student_id=student.id,
        )
        db.session.add(submission)

    if not submission_text and not file_path and not submission.file_path:
        flash('Add a note or upload a file before submitting.', 'danger')
        return redirect(url_for('student.content_preview', cid=item.id))

    if file_path:
        submission.file_path = file_path
    submission.submission_text = submission_text or None
    submission.status = 'submitted'
    submission.submitted_at = utc_now_naive()
    submission.updated_at = utc_now_naive()
    submission.graded_at = None
    submission.marks_awarded = None
    submission.feedback = None
    db.session.commit()

    late_note = ' Late submission flagged.' if item.due_date and submission.submitted_at.date() > item.due_date else ''
    flash(f'Assignment submitted successfully.{late_note}', 'success')
    return redirect(url_for('student.content_preview', cid=item.id))


@student_bp.route('/assignments/submissions/<int:sid>/file')
@login_required
@student_required
def submission_file(sid):
    student = _current_student()
    submission = AssignmentSubmission.query.filter_by(
        college_id=student.college_id,
        id=sid,
        student_id=student.id,
    ).first_or_404()
    if not submission.file_path:
        abort(404)

    abs_path = resolve_submission_path(current_app, submission.file_path)
    if not abs_path or not os.path.isfile(abs_path):
        abort(404)

    return send_file(
        abs_path,
        as_attachment=request.args.get('download', '1') != '0',
        download_name=os.path.basename(submission.file_path),
        conditional=True,
    )
