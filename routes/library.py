from __future__ import annotations

import io
import os
import mimetypes
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from pypdf import PdfReader, PdfWriter
from werkzeug.utils import secure_filename

from extensions import db
from models.department import Department
from models.id_card import StudentIDCard
from models.library import (
    LIBRARY_AUDIT_DISCREPANCY_STATUSES,
    LIBRARY_AUDIT_STATUSES,
    LIBRARY_BOOK_TYPES,
    LIBRARY_EBOOK_ACCESS_LEVELS,
    LIBRARY_LOCATION_TYPES,
    LIBRARY_RULE_DEFAULTS,
    LibraryAccessLog,
    LibraryAuditEntry,
    LibraryAuditSession,
    LibraryBook,
    LibraryBookCopy,
    LibraryCategory,
    LibraryCopyEvent,
    LibraryFine,
    LibraryLocation,
    LibraryLoan,
    LibraryReadingProgress,
    LibraryReservation,
    LibraryRule,
)
from models.parent import ParentStudent
from models.student import Student
from models.subject import Subject
from models.teacher import Teacher
from models.user import User
from services.library_notification_service import (
    notify_roles,
    notify_student_and_parents,
    notify_teacher,
)
from utils.decorators import admin_required, parent_required, student_required, teacher_required
from utils.qr_utils import make_library_borrower_qr, make_library_copy_qr
from utils.library_storage import build_library_relpath, resolve_library_path
from utils.time import utc_now_naive


library_bp = Blueprint('library', __name__)

_ALLOWED_EBOOK_EXTENSIONS = {'pdf', 'epub'}


def _college_id() -> int:
    return current_user.college_id


def _is_admin() -> bool:
    return current_user.role in {'admin', 'sub_admin'}


def _is_library_overseer() -> bool:
    return current_user.role in {'admin', 'sub_admin'}


def _is_library_operator() -> bool:
    return current_user.role == 'librarian'


def _can_manage_library() -> bool:
    return _is_library_overseer() or _is_library_operator()


def _can_operate_library() -> bool:
    return _is_library_operator()


def _ensure_library_user():
    if not current_user.is_authenticated or current_user.role == 'super_admin':
        abort(403)


def _scoped_book_or_404(book_id: int) -> LibraryBook:
    book = db.session.get(LibraryBook, book_id)
    if book is None or book.college_id != _college_id():
        abort(404)
    return book


def _scoped_copy_or_404(copy_id: int) -> LibraryBookCopy:
    copy = db.session.get(LibraryBookCopy, copy_id)
    if copy is None or copy.college_id != _college_id():
        abort(404)
    return copy


def _scoped_loan_or_404(loan_id: int) -> LibraryLoan:
    loan = db.session.get(LibraryLoan, loan_id)
    if loan is None or loan.college_id != _college_id():
        abort(404)
    return loan


def _scoped_location_or_404(location_id: int) -> LibraryLocation:
    location = db.session.get(LibraryLocation, location_id)
    if location is None or location.college_id != _college_id():
        abort(404)
    return location


def _student_can_access_book(book: LibraryBook) -> bool:
    if current_user.role != 'student':
        return True
    student = current_user.student_profile
    if student is None:
        return False
    if book.department_id and book.department_id != student.department_id:
        return False
    return book.semester == student.semester


def _library_rule_defaults() -> dict:
    return dict(LIBRARY_RULE_DEFAULTS)


def _library_rule_for_college() -> LibraryRule:
    rule = LibraryRule.query.filter_by(college_id=_college_id()).first()
    if rule is not None:
        return rule
    return LibraryRule(college_id=_college_id(), **_library_rule_defaults())


def _policy_for_borrower(rule: LibraryRule, borrower_role: str) -> dict:
    if borrower_role == 'teacher':
        policy = rule.teacher_policy
    else:
        policy = rule.student_policy
    policy = dict(policy)
    policy['fine_per_day'] = Decimal(str(policy['fine_per_day'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return policy


def _current_borrower_policy() -> dict | None:
    if current_user.role not in {'student', 'teacher'}:
        return None
    borrower_role = 'student' if current_user.role == 'student' else 'teacher'
    return _policy_for_borrower(_library_rule_for_college(), borrower_role)


def _reservation_hold_days(rule: LibraryRule) -> int:
    return max(rule.reservation_hold_days or LIBRARY_RULE_DEFAULTS['reservation_hold_days'], 1)


def _borrower_action_url(*, borrower_role: str) -> str:
    if borrower_role == 'teacher':
        return url_for('library.my_loans')
    return url_for('library.my_loans')


def _parent_library_action_url() -> str:
    return url_for('library.parent_overview')


def _library_staff_action_url(*, session_id: int | None = None) -> str:
    if session_id:
        return url_for('library.stock_audit', session_id=session_id)
    return url_for('library.admin_dashboard')


def _notify_ready_for_pickup(reservation: LibraryReservation) -> None:
    pickup_by = reservation.pickup_expires_at.strftime('%d %b %Y') if reservation.pickup_expires_at else 'the hold deadline'
    title = f'Library pickup ready: {reservation.book.title}'
    content = (
        f'Your reserved copy of "{reservation.book.title}" is ready for pickup. '
        f'Please collect it by {pickup_by}.'
    )
    source_key = f'library_ready_pickup:{reservation.id}'
    if reservation.student is not None:
        notify_student_and_parents(
            reservation.student,
            title=title,
            content=content,
            category='event',
            student_action_url=_borrower_action_url(borrower_role='student'),
            parent_action_url=_parent_library_action_url(),
            source_key=source_key,
            send_email=True,
        )
    elif reservation.teacher is not None:
        notify_teacher(
            reservation.teacher,
            title=title,
            content=content,
            category='event',
            action_url=_borrower_action_url(borrower_role='teacher'),
            source_key=source_key,
            send_email=True,
        )


def _notify_overdue_loan(loan: LibraryLoan) -> None:
    due_label = loan.due_at.strftime('%d %b %Y')
    title = f'Library overdue: {loan.book.title}'
    content = (
        f'"{loan.book.title}" is now overdue. It was due on {due_label}. '
        'Return or renew it from your library page as soon as possible.'
    )
    source_key = f'library_overdue:{loan.id}'
    if loan.student is not None:
        notify_student_and_parents(
            loan.student,
            title=title,
            content=content,
            category='urgent',
            student_action_url=_borrower_action_url(borrower_role='student'),
            parent_action_url=_parent_library_action_url(),
            source_key=source_key,
            send_email=True,
        )
    elif loan.teacher is not None:
        notify_teacher(
            loan.teacher,
            title=title,
            content=content,
            category='urgent',
            action_url=_borrower_action_url(borrower_role='teacher'),
            source_key=source_key,
            send_email=True,
        )


def _notify_fine_assessed(fine: LibraryFine) -> None:
    amount_label = Decimal(str(fine.outstanding_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    book = fine.book or db.session.get(LibraryBook, fine.book_id)
    if book is None:
        return
    title = f'Library fine: {book.title}'
    content = (
        f'A library fine of Rs. {amount_label:.2f} was added for "{book.title}". '
        'Open your library page to review the fine and loan history.'
    )
    source_key = f'library_fine:{fine.id}'
    if fine.student is not None:
        notify_student_and_parents(
            fine.student,
            title=title,
            content=content,
            category='fee',
            student_action_url=_borrower_action_url(borrower_role='student'),
            parent_action_url=_parent_library_action_url(),
            source_key=source_key,
            send_email=True,
        )
    elif fine.teacher is not None:
        notify_teacher(
            fine.teacher,
            title=title,
            content=content,
            category='fee',
            action_url=_borrower_action_url(borrower_role='teacher'),
            source_key=source_key,
            send_email=True,
        )


def _notify_lost_copy_follow_up(copy: LibraryBookCopy, loan: LibraryLoan | None) -> None:
    if loan is None:
        return
    title = f'Library follow-up: copy marked lost for {copy.book.title}'
    content = (
        f'The physical copy {copy.accession_number} of "{copy.book.title}" has been marked as lost. '
        'Please contact the librarian to complete the follow-up process.'
    )
    source_key = f'library_copy_lost:{copy.id}:{loan.id}'
    if loan.student is not None:
        notify_student_and_parents(
            loan.student,
            title=title,
            content=content,
            category='urgent',
            student_action_url=_borrower_action_url(borrower_role='student'),
            parent_action_url=_parent_library_action_url(),
            source_key=source_key,
            send_email=True,
        )
    elif loan.teacher is not None:
        notify_teacher(
            loan.teacher,
            title=title,
            content=content,
            category='urgent',
            action_url=_borrower_action_url(borrower_role='teacher'),
            source_key=source_key,
            send_email=True,
        )


def _notify_audit_follow_up(entry: LibraryAuditEntry) -> None:
    title = f'Library audit follow-up: {entry.copy.accession_number}'
    content = (
        f'Completed audit "{entry.session.title}" flagged {entry.copy.accession_number} '
        f'for follow-up at {entry.copy.location_label}.'
    )
    notify_roles(
        college_id=_college_id(),
        roles={'admin', 'sub_admin', 'librarian'},
        title=title,
        content=content,
        category='urgent',
        action_url=_library_staff_action_url(session_id=entry.session_id),
        source_key=f'library_audit_follow_up:{entry.id}',
        send_email=False,
    )


def _current_borrower_identity() -> dict | None:
    if current_user.role == 'student' and current_user.student_profile:
        return {
            'role': 'student',
            'student_id': current_user.student_profile.id,
            'teacher_id': None,
            'label': current_user.student_profile.user.name,
        }
    if current_user.role == 'teacher' and current_user.teacher_profile:
        return {
            'role': 'teacher',
            'student_id': None,
            'teacher_id': current_user.teacher_profile.id,
            'label': current_user.teacher_profile.user.name,
        }
    return None


def _pending_reservation_for_user(book_id: int) -> LibraryReservation | None:
    identity = _current_borrower_identity()
    if not identity:
        return None
    query = LibraryReservation.query.filter_by(
        college_id=_college_id(),
        book_id=book_id,
    )
    query = query.filter(LibraryReservation.status.in_(['pending', 'ready_for_pickup']))
    if identity['student_id']:
        query = query.filter_by(student_id=identity['student_id'])
    else:
        query = query.filter_by(teacher_id=identity['teacher_id'])
    return query.order_by(LibraryReservation.created_at.asc()).first()


def _pending_reservation_book_ids_for_user() -> set[int]:
    identity = _current_borrower_identity()
    if not identity:
        return set()
    query = LibraryReservation.query.filter_by(
        college_id=_college_id(),
    )
    query = query.filter(LibraryReservation.status.in_(['pending', 'ready_for_pickup']))
    if identity['student_id']:
        query = query.filter_by(student_id=identity['student_id'])
    else:
        query = query.filter_by(teacher_id=identity['teacher_id'])
    return {reservation.book_id for reservation in query.all()}


def _user_reservation_query():
    identity = _current_borrower_identity()
    if not identity:
        return None
    query = LibraryReservation.query.filter_by(college_id=_college_id())
    if identity['student_id']:
        return query.filter_by(student_id=identity['student_id'])
    return query.filter_by(teacher_id=identity['teacher_id'])


def _pending_reservations_for_book(book_id: int):
    return (
        LibraryReservation.query
        .filter(
            LibraryReservation.college_id == _college_id(),
            LibraryReservation.book_id == book_id,
            LibraryReservation.status.in_(['pending', 'ready_for_pickup']),
        )
        .order_by(
            db.case((LibraryReservation.status == 'ready_for_pickup', 0), else_=1),
            LibraryReservation.created_at.asc(),
        )
        .all()
    )


def _release_copy_hold(copy: LibraryBookCopy) -> None:
    if copy.status == 'held':
        copy.status = 'available'


def _active_loan_for_copy(copy: LibraryBookCopy) -> LibraryLoan | None:
    return (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == _college_id(),
            LibraryLoan.copy_id == copy.id,
            LibraryLoan.status.in_(['active', 'overdue']),
        )
        .order_by(LibraryLoan.issued_at.desc())
        .first()
    )


def _requeue_ready_hold_for_copy(copy: LibraryBookCopy) -> LibraryReservation | None:
    reservation = (
        LibraryReservation.query
        .filter_by(college_id=_college_id(), held_copy_id=copy.id, status='ready_for_pickup')
        .first()
    )
    if reservation is None:
        return None
    reservation.status = 'pending'
    reservation.pickup_expires_at = None
    reservation.held_copy_id = None
    _release_copy_hold(copy)
    return reservation


def _append_copy_note(copy: LibraryBookCopy, note: str | None) -> None:
    cleaned = (note or '').strip()
    if not cleaned:
        return
    copy.notes = f'{copy.notes}\n{cleaned}'.strip() if copy.notes else cleaned


def _log_copy_event(
    copy: LibraryBookCopy,
    *,
    action: str,
    previous_status: str | None,
    new_status: str | None,
    previous_condition: str | None,
    new_condition: str | None,
    note: str | None = None,
    loan: LibraryLoan | None = None,
) -> LibraryCopyEvent:
    event = LibraryCopyEvent(
        college_id=_college_id(),
        book_id=copy.book_id,
        copy_id=copy.id,
        loan_id=loan.id if loan else None,
        created_by_user_id=current_user.id,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
        previous_condition=previous_condition,
        new_condition=new_condition,
        notes=(note or '').strip() or None,
    )
    db.session.add(event)
    return event


def _replacement_condition(value: str | None) -> str:
    cleaned = (value or '').strip().lower() or 'good'
    if cleaned not in {'new', 'good', 'fair'}:
        raise ValueError('Choose a valid restored or replacement condition.')
    return cleaned


def _set_reservation_ready_for_pickup(reservation: LibraryReservation, copy: LibraryBookCopy, rule: LibraryRule) -> None:
    now = utc_now_naive()
    reservation.status = 'ready_for_pickup'
    reservation.ready_at = now
    reservation.pickup_expires_at = now + timedelta(days=_reservation_hold_days(rule))
    reservation.held_copy_id = copy.id
    copy.status = 'held'
    _notify_ready_for_pickup(reservation)


def _activate_next_reservation_hold(book_id: int, copy: LibraryBookCopy | None = None) -> LibraryReservation | None:
    copy = copy or (
        LibraryBookCopy.query
        .filter_by(college_id=_college_id(), book_id=book_id, status='available')
        .order_by(LibraryBookCopy.id.asc())
        .first()
    )
    if copy is None:
        return None
    existing_ready = (
        LibraryReservation.query
        .filter_by(college_id=_college_id(), held_copy_id=copy.id, status='ready_for_pickup')
        .first()
    )
    if existing_ready is not None:
        return existing_ready
    next_reservation = (
        LibraryReservation.query
        .filter_by(college_id=_college_id(), book_id=book_id, status='pending')
        .order_by(LibraryReservation.created_at.asc())
        .first()
    )
    if next_reservation is None:
        return None
    _set_reservation_ready_for_pickup(next_reservation, copy, _library_rule_for_college())
    return next_reservation


def _copy_inventory_action_choices(copy: LibraryBookCopy) -> list[tuple[str, str]]:
    if copy.book.book_type == 'digital':
        return []
    if copy.status == 'available':
        return [('mark_damaged', 'Mark Damaged'), ('send_maintenance', 'Send To Maintenance'), ('mark_lost', 'Mark Lost')]
    if copy.status == 'held':
        return [('mark_damaged', 'Mark Damaged'), ('send_maintenance', 'Send To Maintenance'), ('mark_lost', 'Mark Lost')]
    if copy.status == 'issued':
        return [('mark_lost', 'Mark Lost')]
    if copy.status == 'damaged':
        return [('send_maintenance', 'Send To Maintenance'), ('mark_repaired', 'Mark Repaired'), ('write_off', 'Write Off'), ('replacement_received', 'Replacement Received')]
    if copy.status == 'maintenance':
        return [('mark_repaired', 'Mark Repaired'), ('write_off', 'Write Off'), ('replacement_received', 'Replacement Received')]
    if copy.status == 'lost':
        return [('write_off', 'Write Off'), ('replacement_received', 'Replacement Received')]
    if copy.status == 'written_off':
        return [('replacement_received', 'Replacement Received')]
    return []


def _audit_discrepancy_action_choices(entry: LibraryAuditEntry) -> list[tuple[str, str]]:
    if entry.is_present:
        return []
    choices: list[tuple[str, str]] = [('follow_up_required', 'Follow Up Required')]
    copy_actions = {value: label for value, label in _copy_inventory_action_choices(entry.copy)}
    if 'mark_lost' in copy_actions:
        choices.append(('marked_lost', 'Mark Lost'))
    if 'mark_damaged' in copy_actions:
        choices.append(('marked_damaged', 'Mark Damaged'))
    return choices


def _apply_copy_inventory_action(
    copy: LibraryBookCopy,
    *,
    action: str,
    note: str | None = None,
    restored_condition: str | None = None,
) -> dict:
    if copy.book.book_type == 'digital':
        raise ValueError('Digital books do not use physical inventory workflows.')

    allowed_actions = {value for value, _ in _copy_inventory_action_choices(copy)}
    if action not in allowed_actions:
        raise ValueError('That workflow action is not allowed for the current copy state.')

    active_loan = _active_loan_for_copy(copy)
    previous_status = copy.status
    previous_condition = copy.condition
    ready_reservation = None
    message = ''

    if action in {'mark_damaged', 'send_maintenance', 'write_off', 'replacement_received'} and active_loan is not None:
        raise ValueError('Return or resolve the active loan before changing this inventory state.')

    if copy.status == 'held' and action in {'mark_damaged', 'send_maintenance', 'mark_lost', 'write_off', 'replacement_received'}:
        ready_reservation = _requeue_ready_hold_for_copy(copy)

    if action == 'mark_damaged':
        copy.condition = 'damaged'
        copy.status = 'damaged'
        _append_copy_note(copy, note)
        message = f'{copy.accession_number} marked as damaged.'
        _log_copy_event(
            copy,
            action='marked_damaged',
            previous_status=previous_status,
            new_status=copy.status,
            previous_condition=previous_condition,
            new_condition=copy.condition,
            note=note,
        )
    elif action == 'send_maintenance':
        copy.status = 'maintenance'
        _append_copy_note(copy, note)
        message = f'{copy.accession_number} moved to maintenance.'
        _log_copy_event(
            copy,
            action='sent_to_maintenance',
            previous_status=previous_status,
            new_status=copy.status,
            previous_condition=previous_condition,
            new_condition=copy.condition,
            note=note,
        )
    elif action == 'mark_repaired':
        copy.condition = _replacement_condition(restored_condition)
        copy.status = 'available'
        _append_copy_note(copy, note)
        _activate_next_reservation_hold(copy.book_id, copy)
        message = f'{copy.accession_number} repaired and returned to active stock.'
        _log_copy_event(
            copy,
            action='marked_repaired',
            previous_status=previous_status,
            new_status=copy.status,
            previous_condition=previous_condition,
            new_condition=copy.condition,
            note=note,
        )
    elif action == 'mark_lost':
        copy.status = 'lost'
        _append_copy_note(copy, note)
        if active_loan is not None:
            active_loan.status = 'lost'
            active_loan.returned_at = utc_now_naive()
            active_loan.returned_to_user_id = current_user.id
            lost_note = 'Marked lost'
            if note:
                lost_note = f'{lost_note}: {note}'
            active_loan.notes = f'{active_loan.notes}\n{lost_note}'.strip() if active_loan.notes else lost_note
        message = f'{copy.accession_number} marked as lost.'
        _log_copy_event(
            copy,
            action='marked_lost',
            previous_status=previous_status,
            new_status=copy.status,
            previous_condition=previous_condition,
            new_condition=copy.condition,
            note=note,
            loan=active_loan,
        )
        _notify_lost_copy_follow_up(copy, active_loan)
    elif action == 'write_off':
        copy.status = 'written_off'
        _append_copy_note(copy, note)
        message = f'{copy.accession_number} written off from active inventory.'
        _log_copy_event(
            copy,
            action='written_off',
            previous_status=previous_status,
            new_status=copy.status,
            previous_condition=previous_condition,
            new_condition=copy.condition,
            note=note,
        )
    elif action == 'replacement_received':
        replacement_accession = _next_accession_number(copy.book)
        replacement_copy = LibraryBookCopy(
            college_id=copy.college_id,
            book_id=copy.book_id,
            location_id=copy.location_id,
            replacement_of_copy_id=copy.id,
            accession_number=replacement_accession,
            barcode=replacement_accession,
            rack_location=copy.rack_location,
            condition=_replacement_condition(restored_condition),
            status='available',
            notes=f'Replacement copy for {copy.accession_number}.',
        )
        db.session.add(replacement_copy)
        if copy.status != 'written_off':
            copy.status = 'written_off'
        _append_copy_note(copy, note or f'Replacement copy received: {replacement_copy.accession_number}.')
        db.session.flush()
        _activate_next_reservation_hold(copy.book_id, replacement_copy)
        message = f'Replacement copy {replacement_copy.accession_number} created for {copy.accession_number}.'
        _log_copy_event(
            copy,
            action='replacement_received',
            previous_status=previous_status,
            new_status=copy.status,
            previous_condition=previous_condition,
            new_condition=copy.condition,
            note=note or f'Replacement copy created: {replacement_copy.accession_number}.',
        )
        _log_copy_event(
            replacement_copy,
            action='replacement_created',
            previous_status=None,
            new_status=replacement_copy.status,
            previous_condition=None,
            new_condition=replacement_copy.condition,
            note=f'Replacement for {copy.accession_number}.',
        )
        return {'message': message, 'ready_reservation': ready_reservation, 'replacement_copy': replacement_copy}

    if ready_reservation is not None and copy.status != 'available':
        _activate_next_reservation_hold(copy.book_id)

    return {'message': message, 'ready_reservation': ready_reservation, 'replacement_copy': None}


def _fulfill_matching_reservation(copy: LibraryBookCopy, *, student_id: int | None = None, teacher_id: int | None = None) -> None:
    if not student_id and not teacher_id:
        return
    query = LibraryReservation.query.filter(
        LibraryReservation.college_id == _college_id(),
        LibraryReservation.book_id == copy.book_id,
        LibraryReservation.status.in_(['pending', 'ready_for_pickup']),
    )
    if student_id:
        query = query.filter_by(student_id=student_id)
    else:
        query = query.filter_by(teacher_id=teacher_id)
    reservation = query.order_by(
        db.case((LibraryReservation.status == 'ready_for_pickup', 0), else_=1),
        LibraryReservation.created_at.asc(),
    ).first()
    if reservation is None:
        return
    reservation.status = 'fulfilled'
    reservation.fulfilled_at = utc_now_naive()
    reservation.pickup_expires_at = None
    reservation.ready_at = reservation.ready_at or utc_now_naive()
    reservation.held_copy_id = copy.id


def _active_borrower_loan_count(*, student_id: int | None = None, teacher_id: int | None = None) -> int:
    query = LibraryLoan.query.filter(
        LibraryLoan.college_id == _college_id(),
        LibraryLoan.status.in_(['active', 'overdue']),
    )
    if student_id:
        query = query.filter(LibraryLoan.student_id == student_id)
    if teacher_id:
        query = query.filter(LibraryLoan.teacher_id == teacher_id)
    return query.count()


def _normalized_money(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError('Enter a valid money amount.')


def _calculate_overdue_days(loan: LibraryLoan, rule: LibraryRule, *, reference_time=None) -> int:
    reference_time = reference_time or utc_now_naive()
    overdue_days = (reference_time.date() - loan.due_at.date()).days
    overdue_days -= max(rule.grace_days or 0, 0)
    return max(overdue_days, 0)


def _suggested_fine_for_loan(loan: LibraryLoan, rule: LibraryRule, *, reference_time=None) -> Decimal:
    overdue_days = _calculate_overdue_days(loan, rule, reference_time=reference_time)
    if overdue_days <= 0:
        return Decimal('0.00')
    policy = _policy_for_borrower(rule, loan.borrower_role)
    return (policy['fine_per_day'] * overdue_days).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _recalculate_fine_status(fine: LibraryFine) -> None:
    outstanding = Decimal(str(fine.outstanding_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    amount_paid = Decimal(str(fine.amount_paid or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    amount_waived = Decimal(str(fine.amount_waived or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if outstanding <= 0:
        fine.status = 'waived' if amount_waived > 0 and amount_paid <= 0 else 'paid'
        fine.settled_at = utc_now_naive()
    elif amount_paid > 0 or amount_waived > 0:
        fine.status = 'partial'
        fine.settled_at = None
    else:
        fine.status = 'unpaid'
        fine.settled_at = None


def _create_or_update_overdue_fine(
    loan: LibraryLoan,
    *,
    amount: Decimal,
    created_by_user_id: int | None = None,
    notes: str | None = None,
) -> LibraryFine | None:
    if amount <= 0:
        return None
    fine = (
        LibraryFine.query
        .filter_by(college_id=_college_id(), loan_id=loan.id, reason='overdue')
        .order_by(LibraryFine.id.asc())
        .first()
    )
    if fine is None:
        fine = LibraryFine(
            college_id=_college_id(),
            loan_id=loan.id,
            book_id=loan.book_id,
            student_id=loan.student_id,
            teacher_id=loan.teacher_id,
            reason='overdue',
            amount_assessed=amount,
            created_by_user_id=created_by_user_id,
            notes=notes,
        )
        db.session.add(fine)
    else:
        fine.amount_assessed = amount
        if notes:
            fine.notes = notes
    _recalculate_fine_status(fine)
    return fine


def _outstanding_fine_query():
    return (
        LibraryFine.query
        .filter(
            LibraryFine.college_id == _college_id(),
            LibraryFine.status.in_(['unpaid', 'partial']),
        )
        .order_by(LibraryFine.created_at.asc())
    )


def _fine_query_for_borrower(*, student_id: int | None = None, teacher_id: int | None = None, statuses=None):
    query = LibraryFine.query.filter(LibraryFine.college_id == _college_id())
    if student_id:
        query = query.filter(LibraryFine.student_id == student_id)
    if teacher_id:
        query = query.filter(LibraryFine.teacher_id == teacher_id)
    if statuses:
        query = query.filter(LibraryFine.status.in_(list(statuses)))
    return query.order_by(LibraryFine.created_at.desc())


def _fine_total(fines) -> Decimal:
    total = Decimal('0.00')
    for fine in fines:
        total += Decimal(str(fine.outstanding_amount))
    return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _refresh_reservation_holds(college_id: int) -> None:
    now = utc_now_naive()
    changed = False
    ready_reservations = (
        LibraryReservation.query
        .filter(
            LibraryReservation.college_id == college_id,
            LibraryReservation.status == 'ready_for_pickup',
            LibraryReservation.pickup_expires_at.isnot(None),
            LibraryReservation.pickup_expires_at < now,
        )
        .order_by(LibraryReservation.pickup_expires_at.asc())
        .all()
    )
    for reservation in ready_reservations:
        if reservation.held_copy is not None:
            _release_copy_hold(reservation.held_copy)
        reservation.status = 'expired'
        reservation.expired_at = now
        reservation.pickup_expires_at = None
        reservation.held_copy_id = None
        changed = True
        if reservation.book and reservation.book.book_type in {'physical', 'hybrid'}:
            held_copy = (
                LibraryBookCopy.query
                .filter_by(college_id=college_id, book_id=reservation.book_id, status='available')
                .order_by(LibraryBookCopy.id.asc())
                .first()
            )
            if held_copy is not None:
                _activate_next_reservation_hold(reservation.book_id, held_copy)
    if changed:
        db.session.commit()


def _resolve_copy_from_scan(token: str | None) -> LibraryBookCopy | None:
    value = (token or '').strip()
    if not value:
        return None
    if '\n' in value:
        tagged = _extract_qr_field(value, 'barcode', 'accession')
        if tagged:
            value = tagged
    value = value.lower()
    return (
        LibraryBookCopy.query
        .filter(
            LibraryBookCopy.college_id == _college_id(),
            db.or_(
                db.func.lower(LibraryBookCopy.barcode) == value,
                db.func.lower(LibraryBookCopy.accession_number) == value,
            ),
        )
        .first()
    )


def _extract_qr_field(raw_value: str, *field_names: str) -> str | None:
    mapping = {}
    for line in raw_value.splitlines():
        if ':' not in line:
            continue
        key, value = line.split(':', 1)
        mapping[key.strip().lower()] = value.strip()
    for field_name in field_names:
        match = mapping.get(field_name.lower())
        if match:
            return match
    return None


def _resolve_borrower_from_scan(token: str | None):
    value = (token or '').strip()
    if not value:
        return None
    if ':' in value:
        borrower_kind, raw_id = value.split(':', 1)
        borrower_kind = borrower_kind.strip().lower()
        try:
            borrower_id = int(raw_id.strip())
        except (TypeError, ValueError):
            borrower_id = None
        if borrower_kind in {'student', 'teacher'} and borrower_id:
            return {'borrower_kind': borrower_kind, 'borrower_id': borrower_id, 'label': value}
    if '\n' in value:
        tagged = _extract_qr_field(value, 'scan', 'card', 'roll', 'employee id', 'employee')
        if tagged:
            value = tagged
    normalized = value.lower()

    student_card = (
        StudentIDCard.query
        .filter(
            StudentIDCard.college_id == _college_id(),
            StudentIDCard.status == 'approved',
            db.func.lower(StudentIDCard.card_number) == normalized,
        )
        .first()
    )
    if student_card is not None:
        return {
            'borrower_kind': 'student',
            'borrower_id': student_card.student_id,
            'label': f'Student · {student_card.student.user.name}',
        }

    student = (
        Student.query
        .filter(
            Student.college_id == _college_id(),
            db.func.lower(Student.roll_number) == normalized,
        )
        .first()
    )
    if student is not None:
        return {
            'borrower_kind': 'student',
            'borrower_id': student.id,
            'label': f'Student · {student.user.name}',
        }

    teacher = (
        Teacher.query
        .filter(
            Teacher.college_id == _college_id(),
            db.func.lower(Teacher.employee_id) == normalized,
        )
        .first()
    )
    if teacher is not None:
        return {
            'borrower_kind': 'teacher',
            'borrower_id': teacher.id,
            'label': f'Teacher · {teacher.user.name}',
        }
    return None


def _current_borrower_outstanding_total(*, student_id: int | None = None, teacher_id: int | None = None) -> Decimal:
    fines = _fine_query_for_borrower(student_id=student_id, teacher_id=teacher_id, statuses=['unpaid', 'partial']).all()
    return _fine_total(fines)


def _student_scan_value(student: Student) -> str:
    card = getattr(student, 'id_card', None)
    if card is not None and card.status == 'approved' and card.card_number:
        return card.card_number
    return student.roll_number


def _teacher_scan_value(teacher: Teacher) -> str:
    return teacher.employee_id


def _borrower_has_overdue_loan(*, student_id: int | None = None, teacher_id: int | None = None) -> LibraryLoan | None:
    query = LibraryLoan.query.filter(
        LibraryLoan.college_id == _college_id(),
        LibraryLoan.status == 'overdue',
    )
    if student_id:
        query = query.filter(LibraryLoan.student_id == student_id)
    if teacher_id:
        query = query.filter(LibraryLoan.teacher_id == teacher_id)
    return query.order_by(LibraryLoan.due_at.asc()).first()


def _resolve_issue_borrower(copy: LibraryBookCopy, borrower_kind: str, borrower_id: int | None, library_rule: LibraryRule) -> dict:
    student_id = None
    teacher_id = None
    borrower_role = None
    borrower_label = None
    if borrower_kind == 'student':
        student = Student.query.filter_by(id=borrower_id, college_id=_college_id()).first()
        if student is None:
            raise ValueError('Selected student was not found.')
        if copy.book.department_id and copy.book.department_id != student.department_id:
            raise ValueError('This book belongs to a different department than the selected student.')
        if copy.book.semester and copy.book.semester != student.semester:
            raise ValueError('This book belongs to a different semester than the selected student.')
        student_id = student.id
        borrower_role = 'student'
        borrower_label = student.user.name
    elif borrower_kind == 'teacher':
        teacher = Teacher.query.filter_by(id=borrower_id, college_id=_college_id()).first()
        if teacher is None:
            raise ValueError('Selected teacher was not found.')
        teacher_id = teacher.id
        borrower_role = 'teacher'
        borrower_label = teacher.user.name
    else:
        raise ValueError('Choose a valid borrower type.')

    borrower_policy = _policy_for_borrower(library_rule, borrower_role)
    active_count = _active_borrower_loan_count(student_id=student_id, teacher_id=teacher_id)
    if active_count >= borrower_policy['max_active_loans']:
        raise ValueError(
            f"{borrower_policy['label']} borrowing limit reached. Max active books: {borrower_policy['max_active_loans']}."
        )

    overdue_loan = _borrower_has_overdue_loan(student_id=student_id, teacher_id=teacher_id)
    if overdue_loan is not None:
        raise ValueError(
            f"{borrower_policy['label']} has overdue book '{overdue_loan.book.title}'. Return overdue books before issuing another title."
        )

    outstanding_total = _current_borrower_outstanding_total(student_id=student_id, teacher_id=teacher_id)
    if outstanding_total > 0:
        raise ValueError(
            f"{borrower_policy['label']} has outstanding library fines of Rs. {outstanding_total:.2f}. Clear them before issuing another title."
        )

    existing_title = (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == _college_id(),
            LibraryLoan.book_id == copy.book_id,
            LibraryLoan.status.in_(['active', 'overdue']),
            LibraryLoan.student_id == student_id if student_id else db.true(),
            LibraryLoan.teacher_id == teacher_id if teacher_id else db.true(),
        )
        .first()
    )
    if existing_title is not None:
        raise ValueError('This borrower already has this title in current loans.')

    return {
        'student_id': student_id,
        'teacher_id': teacher_id,
        'borrower_role': borrower_role,
        'borrower_policy': borrower_policy,
        'borrower_label': borrower_label,
    }


def _issue_copy_to_borrower(
    copy: LibraryBookCopy,
    *,
    borrower_kind: str,
    borrower_id: int | None,
    requested_due_days: int | None = None,
    notes: str | None = None,
):
    library_rule = _library_rule_for_college()
    if copy.book.book_type == 'digital':
        raise ValueError('E-books are read directly in the system and do not need to be issued.')
    if copy.status not in {'available', 'held'}:
        raise ValueError('That copy is not currently available for issue.')

    borrower_context = _resolve_issue_borrower(copy, borrower_kind, borrower_id, library_rule)

    due_days = borrower_context['borrower_policy']['due_days']
    if requested_due_days:
        due_days = max(1, min(requested_due_days, borrower_context['borrower_policy']['due_days']))

    active_existing = (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == _college_id(),
            LibraryLoan.copy_id == copy.id,
            LibraryLoan.status.in_(['active', 'overdue']),
        )
        .first()
    )
    if active_existing:
        raise ValueError('That copy already has an active loan.')

    held_reservation = None
    if copy.status == 'held':
        held_reservation = (
            LibraryReservation.query
            .filter_by(college_id=_college_id(), held_copy_id=copy.id, status='ready_for_pickup')
            .first()
        )
        if held_reservation is None:
            raise ValueError('This copy is marked as held and cannot be issued until the hold is released.')
        if not held_reservation.matches_borrower(
            student_id=borrower_context['student_id'],
            teacher_id=borrower_context['teacher_id'],
        ):
            deadline = held_reservation.pickup_expires_at.strftime('%d %b %Y') if held_reservation.pickup_expires_at else 'the pickup deadline'
            raise ValueError(
                f"This copy is on the hold shelf for {held_reservation.borrower_label} until {deadline}."
            )

    earliest_reservation = (
        LibraryReservation.query
        .filter(
            LibraryReservation.college_id == _college_id(),
            LibraryReservation.book_id == copy.book_id,
            LibraryReservation.status.in_(['pending', 'ready_for_pickup']),
        )
        .order_by(
            db.case((LibraryReservation.status == 'ready_for_pickup', 0), else_=1),
            LibraryReservation.created_at.asc(),
        )
        .first()
    )
    if earliest_reservation and not earliest_reservation.matches_borrower(
        student_id=borrower_context['student_id'],
        teacher_id=borrower_context['teacher_id'],
    ):
        raise ValueError(
            f"This title has a pending reservation queue. Next borrower: {earliest_reservation.borrower_label}."
        )

    loan = LibraryLoan(
        college_id=_college_id(),
        book_id=copy.book_id,
        copy_id=copy.id,
        student_id=borrower_context['student_id'],
        teacher_id=borrower_context['teacher_id'],
        issued_by_user_id=current_user.id,
        due_at=utc_now_naive() + timedelta(days=due_days),
        notes=notes,
        status='active',
    )
    copy.status = 'issued'
    db.session.add(loan)
    _fulfill_matching_reservation(
        copy,
        student_id=borrower_context['student_id'],
        teacher_id=borrower_context['teacher_id'],
    )
    db.session.commit()
    return {
        'due_days': due_days,
        'borrower_label': borrower_context['borrower_label'],
        'loan': loan,
    }


def _return_loan_record(loan: LibraryLoan, *, fine_raw: str | None = None):
    if not loan.is_active:
        raise ValueError('This loan is already closed.')
    library_rule = _library_rule_for_college()
    if fine_raw:
        fine_amount = _normalized_money(fine_raw)
    else:
        fine_amount = _suggested_fine_for_loan(loan, library_rule)

    loan.returned_at = utc_now_naive()
    loan.status = 'returned'
    loan.returned_to_user_id = current_user.id
    loan.fine_amount = fine_amount
    if fine_amount > 0:
        fine = _create_or_update_overdue_fine(
            loan,
            amount=fine_amount,
            created_by_user_id=current_user.id,
        )
        if fine is not None and fine.outstanding_amount > 0:
            _notify_fine_assessed(fine)
    loan.copy.status = 'available'
    ready_reservation = _activate_next_reservation_hold(loan.book_id, loan.copy)
    db.session.commit()
    queue_count = (
        LibraryReservation.query
        .filter(
            LibraryReservation.college_id == _college_id(),
            LibraryReservation.book_id == loan.book_id,
            LibraryReservation.status.in_(['pending', 'ready_for_pickup']),
        )
        .count()
    )
    return {'fine_amount': fine_amount, 'queue_count': queue_count, 'ready_reservation': ready_reservation}


def _refresh_overdue_loans(college_id: int) -> None:
    now = utc_now_naive()
    changed = False
    overdue_loans = (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == college_id,
            LibraryLoan.status == 'active',
            LibraryLoan.due_at < now,
        )
        .all()
    )
    for loan in overdue_loans:
        loan.status = 'overdue'
        _notify_overdue_loan(loan)
        changed = True
    if changed:
        db.session.commit()


def _refresh_library_runtime_state(college_id: int) -> None:
    _refresh_overdue_loans(college_id)
    _refresh_reservation_holds(college_id)


def _save_ebook_file(upload_file) -> tuple[str, str]:
    filename = secure_filename(upload_file.filename or '')
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in _ALLOWED_EBOOK_EXTENSIONS:
        raise ValueError('E-book must be a PDF or EPUB file.')
    storage_name = f'library-{utc_now_naive().strftime("%Y%m%d%H%M%S%f")}.{ext}'
    abs_path = os.path.join(current_app.config['LIBRARY_UPLOAD_FOLDER'], storage_name)
    upload_file.save(abs_path)
    return build_library_relpath(storage_name), filename


def _delete_ebook_file(rel_path: str | None) -> None:
    abs_path = resolve_library_path(current_app, rel_path)
    if abs_path and os.path.exists(abs_path):
        os.remove(abs_path)


def _ebook_mimetype(path: str, filename: str | None = None) -> str:
    mime, _ = mimetypes.guess_type(filename or path)
    return mime or 'application/octet-stream'


def _ebook_extension(book: LibraryBook) -> str:
    filename = book.ebook_filename or ''
    return filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''


def _ebook_file_or_404(book: LibraryBook) -> str:
    if not book.digital_enabled:
        abort(404)
    abs_path = resolve_library_path(current_app, book.ebook_file_path)
    if not abs_path or not os.path.exists(abs_path):
        abort(404)
    return abs_path


def _ebook_preview_page_limit(book: LibraryBook) -> int:
    if book.ebook_access_level != 'preview_only':
        return 0
    return max(book.ebook_preview_page_limit or 10, 1)


def _ebook_total_pages(abs_path: str, *, extension: str) -> int | None:
    if extension != 'pdf':
        return None
    try:
        return len(PdfReader(abs_path).pages)
    except Exception:
        return None


def _can_open_ebook_reader(book: LibraryBook) -> bool:
    return current_user.role in {'admin', 'sub_admin', 'librarian', 'teacher', 'student'} and book.digital_enabled


def _can_download_ebook(book: LibraryBook) -> bool:
    return (
        _can_open_ebook_reader(book)
        and book.ebook_access_level == 'full_read'
        and book.ebook_download_allowed
    )


def _reader_progress_for_current_user(book_id: int) -> LibraryReadingProgress | None:
    return LibraryReadingProgress.query.filter_by(
        college_id=_college_id(),
        book_id=book_id,
        user_id=current_user.id,
    ).first()


def _upsert_reader_progress(
    book: LibraryBook,
    *,
    last_page: int | None = None,
    progress_percent: Decimal | None = None,
    last_position: str | None = None,
    total_pages: int | None = None,
) -> LibraryReadingProgress:
    progress = _reader_progress_for_current_user(book.id)
    if progress is None:
        progress = LibraryReadingProgress(
            college_id=_college_id(),
            book_id=book.id,
            user_id=current_user.id,
        )
        db.session.add(progress)
    progress.last_page = last_page
    progress.progress_percent = progress_percent
    progress.last_position = last_position
    progress.total_pages = total_pages
    progress.last_read_at = utc_now_naive()
    return progress


def _limited_preview_pdf(abs_path: str, *, max_pages: int) -> io.BytesIO:
    reader = PdfReader(abs_path)
    writer = PdfWriter()
    for page in reader.pages[:max_pages]:
        writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer


def _record_ebook_access(book: LibraryBook, action: str) -> None:
    access_log = LibraryAccessLog(
        college_id=_college_id(),
        book_id=book.id,
        student_id=current_user.student_profile.id if current_user.role == 'student' and current_user.student_profile else None,
        teacher_id=current_user.teacher_profile.id if current_user.role == 'teacher' and current_user.teacher_profile else None,
        action=action,
    )
    db.session.add(access_log)
    db.session.commit()


def _get_or_create_category(name: str | None, description: str | None = None) -> LibraryCategory | None:
    cleaned = (name or '').strip()
    if not cleaned:
        return None
    category = LibraryCategory.query.filter_by(college_id=_college_id(), name=cleaned).first()
    if category:
        return category
    category = LibraryCategory(
        college_id=_college_id(),
        name=cleaned,
        description=(description or '').strip() or None,
    )
    db.session.add(category)
    db.session.flush()
    return category


def _assign_library_rule_fields(rule: LibraryRule) -> None:
    def _bounded_int(field: str, *, minimum: int, maximum: int, default: int | None = None) -> int:
        raw = request.form.get(field, type=int)
        if raw is None:
            if default is None:
                raise ValueError('Complete all required library rule fields.')
            raw = default
        return max(minimum, min(raw, maximum))

    rule.student_max_active_loans = _bounded_int('student_max_active_loans', minimum=1, maximum=20)
    rule.teacher_max_active_loans = _bounded_int('teacher_max_active_loans', minimum=1, maximum=30)
    rule.student_due_days = _bounded_int('student_due_days', minimum=1, maximum=90)
    rule.teacher_due_days = _bounded_int('teacher_due_days', minimum=1, maximum=180)
    rule.student_max_renewals = _bounded_int('student_max_renewals', minimum=0, maximum=10)
    rule.teacher_max_renewals = _bounded_int('teacher_max_renewals', minimum=0, maximum=10)
    rule.student_renew_days = _bounded_int('student_renew_days', minimum=1, maximum=60)
    rule.teacher_renew_days = _bounded_int('teacher_renew_days', minimum=1, maximum=90)
    rule.grace_days = _bounded_int('grace_days', minimum=0, maximum=30)
    rule.reservation_hold_days = _bounded_int(
        'reservation_hold_days',
        minimum=1,
        maximum=14,
        default=rule.reservation_hold_days or LIBRARY_RULE_DEFAULTS['reservation_hold_days'],
    )
    rule.student_fine_per_day = _normalized_money(request.form.get('student_fine_per_day', '0'))
    rule.teacher_fine_per_day = _normalized_money(request.form.get('teacher_fine_per_day', '0'))
    rule.regulations = (request.form.get('regulations') or '').strip() or None


def _active_library_locations() -> list[LibraryLocation]:
    locations = (
        LibraryLocation.query
        .filter_by(college_id=_college_id(), is_active=True)
        .all()
    )
    return sorted(locations, key=lambda item: (item.full_label.lower(), item.id))


def _active_rack_locations() -> list[LibraryLocation]:
    racks = (
        LibraryLocation.query
        .filter_by(college_id=_college_id(), is_active=True, location_type='rack')
        .all()
    )
    return sorted(racks, key=lambda item: (item.full_label.lower(), item.id))


def _location_choices(*, include_inactive: bool = False, exclude: LibraryLocation | None = None) -> list[LibraryLocation]:
    query = LibraryLocation.query.filter_by(college_id=_college_id())
    if not include_inactive:
        query = query.filter_by(is_active=True)

    rows = query.all()
    if exclude is not None:
        rows = [row for row in rows if row.id != exclude.id and not row.is_descendant_of(exclude)]
    return sorted(rows, key=lambda item: (item.full_label.lower(), item.id))


def _location_roots() -> list[LibraryLocation]:
    locations = (
        LibraryLocation.query
        .filter_by(college_id=_college_id())
        .all()
    )
    roots = [location for location in locations if location.parent_id is None]
    return sorted(roots, key=lambda item: ((item.department.name.lower() if item.department else ''), item.name.lower(), item.id))


def _non_cell_location_choices(*, include_inactive: bool = False, exclude: LibraryLocation | None = None) -> list[LibraryLocation]:
    rows = [location for location in _location_choices(include_inactive=include_inactive, exclude=exclude) if location.location_type != 'cell']
    return rows


def _rack_cells() -> list[LibraryLocation]:
    cells = (
        LibraryLocation.query
        .filter_by(college_id=_college_id(), location_type='cell')
        .all()
    )
    return sorted(
        cells,
        key=lambda item: (
            item.parent.full_label.lower() if item.parent else '',
            item.row_label or '',
            item.column_label or '',
            item.id,
        ),
    )


def _grid_sort_key(value: str | None) -> tuple[int, int | str]:
    cleaned = (value or '').strip()
    if cleaned.isdigit():
        return (0, int(cleaned))
    return (1, cleaned.lower())


def _resolve_location(location_id: int | None) -> LibraryLocation | None:
    if not location_id:
        return None
    location = LibraryLocation.query.filter_by(id=location_id, college_id=_college_id()).first()
    if location is None:
        raise ValueError('Selected library location does not exist.')
    return location


def _normalize_grid_label(value: str | None) -> str | None:
    cleaned = (value or '').strip()
    return cleaned or None


def _grid_option_values(count: int | None) -> list[str]:
    if not count or count <= 0:
        return []
    return [str(index) for index in range(1, count + 1)]


def _rack_assignment_groups() -> list[dict]:
    groups: list[dict] = []
    for rack in _active_rack_locations():
        rows = _grid_option_values(rack.row_count)
        columns = _grid_option_values(rack.column_count)
        cells = sorted(
            [child for child in rack.children if child.location_type == 'cell'],
            key=lambda item: (_grid_sort_key(item.row_label), _grid_sort_key(item.column_label), item.id),
        )
        cell_map = {
            f'{cell.row_label}:{cell.column_label}': cell
            for cell in cells
            if cell.row_label and cell.column_label
        }
        groups.append({
            'rack': rack,
            'rows': rows,
            'columns': columns,
            'cells': cells,
            'cell_map': cell_map,
            'assigned_count': sum(
                1
                for cell in cells
                if cell.department_id or cell.subject_id or cell.semester
            ),
        })
    return groups


def _auditable_copy_statuses() -> tuple[str, ...]:
    return ('available', 'held', 'maintenance', 'damaged')


def _auditable_copies_query(*, rack_id: int | None = None):
    query = (
        LibraryBookCopy.query
        .join(LibraryBook, LibraryBook.id == LibraryBookCopy.book_id)
        .filter(
            LibraryBookCopy.college_id == _college_id(),
            LibraryBook.book_type.in_(['physical', 'hybrid']),
            LibraryBook.is_active.is_(True),
            LibraryBookCopy.status.in_(_auditable_copy_statuses()),
        )
    )
    if rack_id:
        rack = _scoped_location_or_404(rack_id)
        branch_ids = _location_branch_ids(rack)
        query = query.filter(LibraryBookCopy.location_id.in_(branch_ids))
    return query


def _scoped_audit_session_or_404(session_id: int) -> LibraryAuditSession:
    session = db.session.get(LibraryAuditSession, session_id)
    if session is None or session.college_id != _college_id():
        abort(404)
    return session


def _append_audit_entry_note(entry: LibraryAuditEntry, note: str | None) -> None:
    cleaned = (note or '').strip()
    if not cleaned:
        return
    entry.notes = f'{entry.notes}\n{cleaned}'.strip() if entry.notes else cleaned


def _matches_text(value: str, query: str) -> bool:
    if not query:
        return True
    return query.lower() in value.lower()


def _location_search_blob(location: LibraryLocation) -> str:
    parts = [
        location.name or '',
        location.code or '',
        location.full_label or '',
        location.type_label or '',
        location.academic_scope_label or '',
        location.coordinate_label or '',
        location.grid_label or '',
        location.notes or '',
    ]
    return ' '.join(parts)


def _location_scope_matches(
    location: LibraryLocation,
    *,
    department_id: int | None = None,
    semester: int | None = None,
    subject_id: int | None = None,
) -> bool:
    if department_id and location.department_id != department_id:
        return False
    if semester and location.semester != semester:
        return False
    if subject_id and location.subject_id != subject_id:
        return False
    return True


def _prune_location_tree(
    nodes: list[LibraryLocation],
    *,
    query: str = '',
    department_id: int | None = None,
    semester: int | None = None,
    subject_id: int | None = None,
) -> list[LibraryLocation]:
    filtered: list[LibraryLocation] = []
    for node in nodes:
        original_children = list(node.children)
        pruned_children = _prune_location_tree(
            original_children,
            query=query,
            department_id=department_id,
            semester=semester,
            subject_id=subject_id,
        )
        node.children = pruned_children
        self_matches = _matches_text(_location_search_blob(node), query) and _location_scope_matches(
            node,
            department_id=department_id,
            semester=semester,
            subject_id=subject_id,
        )
        if self_matches or pruned_children:
            filtered.append(node)
        else:
            node.children = original_children
    return filtered


def _filter_racks(racks: list[LibraryLocation], query: str) -> list[LibraryLocation]:
    if not query:
        return racks
    return [rack for rack in racks if _matches_text(_location_search_blob(rack), query)]


def _filter_rack_assignment_groups(
    groups: list[dict],
    *,
    query: str = '',
    rack_id: int | None = None,
    department_id: int | None = None,
    semester: int | None = None,
    subject_id: int | None = None,
) -> list[dict]:
    filtered_groups: list[dict] = []
    for group in groups:
        rack = group['rack']
        if rack_id and rack.id != rack_id:
            continue

        rack_matches = _matches_text(_location_search_blob(rack), query)
        filtered_cells = []
        for cell in group['cells']:
            if department_id and cell.department_id != department_id:
                continue
            if semester and cell.semester != semester:
                continue
            if subject_id and cell.subject_id != subject_id:
                continue
            if query and not rack_matches and not _matches_text(_location_search_blob(cell), query):
                continue
            filtered_cells.append(cell)

        if query or department_id or semester or subject_id or rack_id:
            if not rack_matches and not filtered_cells:
                continue
            cell_map = {
                f'{cell.row_label}:{cell.column_label}': cell
                for cell in filtered_cells
                if cell.row_label and cell.column_label
            }
            filtered_groups.append({
                'rack': rack,
                'rows': group['rows'],
                'columns': group['columns'],
                'cells': filtered_cells,
                'cell_map': cell_map,
                'assigned_count': sum(
                    1 for cell in filtered_cells if cell.department_id or cell.subject_id or cell.semester
                ),
            })
        else:
            filtered_groups.append(group)
    return filtered_groups


def _rack_defaults_for_location(location: LibraryLocation | None) -> tuple[LibraryLocation | None, str, str]:
    if location is None:
        return None, '', ''
    if location.location_type == 'rack':
        return location, '', ''
    if location.parent and location.parent.location_type == 'rack':
        return location.parent, location.row_label or '', location.column_label or ''
    return None, location.row_label or '', location.column_label or ''


def _sync_rack_grid_cells(rack: LibraryLocation) -> None:
    if rack.location_type != 'rack' or not rack.row_count or not rack.column_count:
        return

    existing_cells = {
        (cell.row_label or '', cell.column_label or ''): cell
        for cell in rack.children
        if cell.location_type == 'cell'
    }
    for row_value in _grid_option_values(rack.row_count):
        for column_value in _grid_option_values(rack.column_count):
            key = (row_value, column_value)
            cell = existing_cells.get(key)
            if cell is None:
                cell = LibraryLocation(
                    college_id=rack.college_id,
                    parent_id=rack.id,
                    department_id=None,
                    subject_id=None,
                    name=f'Cell {row_value}-{column_value}',
                    code=f'{rack.code}-{row_value}-{column_value}' if rack.code else None,
                    location_type='cell',
                    semester=None,
                    row_label=row_value,
                    column_label=column_value,
                    is_active=rack.is_active,
                )
                db.session.add(cell)
                continue

            cell.parent_id = rack.id
            cell.row_label = row_value
            cell.column_label = column_value
            cell.is_active = rack.is_active
            if not cell.code and rack.code:
                cell.code = f'{rack.code}-{row_value}-{column_value}'


def _resolve_book_location_from_form(*, field_prefix: str = 'location', allow_fallback: bool = True) -> LibraryLocation | None:
    direct_location_id = request.form.get(f'{field_prefix}_id', type=int)
    if direct_location_id:
        return _resolve_location(direct_location_id)

    rack_id = request.form.get(f'{field_prefix}_rack_id', type=int)
    row_label = _normalize_grid_label(request.form.get(f'{field_prefix}_row'))
    column_label = _normalize_grid_label(request.form.get(f'{field_prefix}_column'))
    if not rack_id:
        return None

    rack = _resolve_location(rack_id)
    if rack is None or rack.location_type != 'rack':
        raise ValueError('Selected rack does not exist.')

    if rack.row_count and rack.column_count:
        if not row_label or not column_label:
            raise ValueError('Select both rack row and rack column.')
        if row_label not in _grid_option_values(rack.row_count) or column_label not in _grid_option_values(rack.column_count):
            raise ValueError('Selected rack row or column is outside the rack grid.')
        cell = LibraryLocation.query.filter_by(
            college_id=_college_id(),
            parent_id=rack.id,
            location_type='cell',
            row_label=row_label,
            column_label=column_label,
        ).first()
        if cell is None:
            raise ValueError('Selected rack cell does not exist.')
        return cell

    if allow_fallback:
        return rack
    raise ValueError('Selected rack does not define row and column positions yet.')


def _location_redirect_target() -> str:
    next_view = (request.form.get('next_view') or '').strip()
    allowed = {
        'library.manage_locations',
        'library.manage_racks',
        'library.manage_rack_assignments',
    }
    if next_view in allowed:
        return next_view
    return 'library.manage_locations'


def _book_redirect_target() -> str:
    next_view = (request.form.get('next_view') or '').strip()
    allowed = {
        'library.admin_dashboard',
        'library.catalog',
    }
    if next_view in allowed:
        return next_view
    return 'library.admin_dashboard'


def _circulation_redirect_target() -> str:
    next_view = (request.form.get('next_view') or '').strip()
    allowed = {
        'library.circulation_desk',
        'library.admin_dashboard',
    }
    if next_view in allowed:
        return next_view
    return 'library.circulation_desk'


def _location_branch_nodes(location: LibraryLocation) -> list[LibraryLocation]:
    nodes: list[LibraryLocation] = []

    def _visit(node: LibraryLocation) -> None:
        for child in node.children:
            _visit(child)
        nodes.append(node)

    _visit(location)
    return nodes


def _location_branch_ids(location: LibraryLocation) -> list[int]:
    return [node.id for node in _location_branch_nodes(location)]


def _assign_location_fields(location: LibraryLocation) -> None:
    name = (request.form.get('name') or '').strip()
    if not name:
        raise ValueError('Location name is required.')

    location_type = (request.form.get('location_type') or 'rack').strip()
    if location_type not in LIBRARY_LOCATION_TYPES:
        raise ValueError('Invalid location type selected.')

    department_id = request.form.get('department_id', type=int)
    if department_id:
        department = Department.query.filter_by(id=department_id, college_id=_college_id()).first()
        if department is None:
            raise ValueError('Selected department does not exist.')

    subject_id = request.form.get('subject_id', type=int)
    if subject_id:
        subject = Subject.query.filter_by(id=subject_id, college_id=_college_id()).first()
        if subject is None:
            raise ValueError('Selected subject does not exist.')
        if department_id and subject.department_id and subject.department_id != department_id:
            raise ValueError('Selected subject belongs to a different department.')
        if not department_id:
            department_id = subject.department_id

    semester = request.form.get('semester', type=int) or None
    if semester is not None and not 1 <= semester <= 12:
        raise ValueError('Semester must be between 1 and 12.')

    row_count = request.form.get('row_count', type=int) or None
    column_count = request.form.get('column_count', type=int) or None
    row_label = (request.form.get('row_label') or '').strip() or None
    column_label = (request.form.get('column_label') or '').strip() or None

    if location_type == 'rack':
        if not row_count or not column_count:
            raise ValueError('Rack locations must define how many rows and columns they contain.')
        if row_count < 1 or column_count < 1:
            raise ValueError('Rack rows and columns must be at least 1.')
        department_id = None
        subject_id = None
        semester = None
        row_label = None
        column_label = None
    else:
        row_count = None
        column_count = None

    parent_id = request.form.get('parent_id', type=int)
    parent = None
    if parent_id:
        parent = _resolve_location(parent_id)
        if location.id and parent.id == location.id:
            raise ValueError('A location cannot be its own parent.')
        if location.id and parent.is_descendant_of(location):
            raise ValueError('Choose a parent outside this location branch.')
        if parent.location_type == 'rack':
            if location_type != 'cell':
                raise ValueError('Children under a rack must be rack cells.')
            if not row_label or not column_label:
                raise ValueError('Rack cells must define both row and column.')
        else:
            if department_id and parent.department_id and parent.department_id != department_id:
                raise ValueError('Parent hierarchy belongs to a different department.')
            if not department_id:
                department_id = parent.department_id
            if subject_id and parent.subject_id and parent.subject_id != subject_id:
                raise ValueError('Parent hierarchy belongs to a different subject.')
            if not subject_id:
                subject_id = parent.subject_id
            if semester and parent.semester and parent.semester != semester:
                raise ValueError('Parent hierarchy belongs to a different semester.')
            if not semester:
                semester = parent.semester

    code = (request.form.get('code') or '').strip() or None
    if code:
        duplicate_query = LibraryLocation.query.filter_by(college_id=_college_id(), code=code)
        if location.id:
            duplicate_query = duplicate_query.filter(LibraryLocation.id != location.id)
        if duplicate_query.first():
            raise ValueError('Another library location already uses that code.')

    duplicate_name_query = LibraryLocation.query.filter_by(
        college_id=_college_id(),
        parent_id=parent.id if parent else None,
        name=name,
    )
    if location.id:
        duplicate_name_query = duplicate_name_query.filter(LibraryLocation.id != location.id)
    if duplicate_name_query.first():
        raise ValueError('Another location at this level already uses that name.')

    location.college_id = _college_id()
    location.parent_id = parent.id if parent else None
    location.department_id = department_id or None
    location.subject_id = subject_id or None
    location.name = name
    location.code = code
    location.location_type = location_type
    location.semester = semester
    location.row_count = row_count
    location.column_count = column_count
    location.row_label = row_label
    location.column_label = column_label
    location.notes = (request.form.get('notes') or '').strip() or None
    location.is_active = request.form.get('is_active', '1') == '1'


def _assign_book_fields(book: LibraryBook, *, require_digital_file: bool) -> None:
    category_mode = (request.form.get('category_mode') or 'existing').strip()
    category = None
    if category_mode == 'new':
        category = _get_or_create_category(
            request.form.get('new_category_name'),
            request.form.get('new_category_description'),
        )
    else:
        category_id = request.form.get('category_id', type=int)
        if category_id:
            category = LibraryCategory.query.filter_by(
                id=category_id,
                college_id=_college_id(),
            ).first()
            if category is None:
                raise ValueError('Selected category does not exist.')

    department_id = request.form.get('department_id', type=int)
    subject_id = request.form.get('subject_id', type=int)
    if department_id:
        department = Department.query.filter_by(id=department_id, college_id=_college_id()).first()
        if department is None:
            raise ValueError('Selected department does not exist.')
    if subject_id:
        subject = Subject.query.filter_by(id=subject_id, college_id=_college_id()).first()
        if subject is None:
            raise ValueError('Selected subject does not exist.')
        if department_id and subject.department_id and subject.department_id != department_id:
            raise ValueError('Selected subject belongs to a different department.')
        if not department_id:
            department_id = subject.department_id
    default_location = _resolve_book_location_from_form(field_prefix='default_location')
    if default_location and department_id and default_location.department_id and default_location.department_id != department_id:
        raise ValueError('Selected default location belongs to a different department.')
    if default_location and not department_id and default_location.department_id:
        department_id = default_location.department_id
    if default_location and subject_id and default_location.subject_id and default_location.subject_id != subject_id:
        raise ValueError('Selected default location belongs to a different subject.')
    if default_location and not subject_id and default_location.subject_id:
        subject_id = default_location.subject_id

    title = (request.form.get('title') or '').strip()
    author = (request.form.get('author') or '').strip()
    if not title or not author:
        raise ValueError('Title and author are required.')

    book_type = (request.form.get('book_type') or 'physical').strip()
    if book_type not in LIBRARY_BOOK_TYPES:
        raise ValueError('Invalid book type selected.')
    if book_type == 'digital':
        default_location = None

    ebook_access_level = (request.form.get('ebook_access_level') or 'full_read').strip()
    if ebook_access_level not in LIBRARY_EBOOK_ACCESS_LEVELS:
        raise ValueError('Invalid e-book access mode selected.')
    ebook_download_allowed = request.form.get('ebook_download_allowed', '1') == '1'
    ebook_preview_page_limit = request.form.get('ebook_preview_page_limit', type=int) or None
    if ebook_preview_page_limit is not None:
        ebook_preview_page_limit = max(1, min(ebook_preview_page_limit, 500))

    ebook_file = request.files.get('ebook_file')
    if book_type in {'digital', 'hybrid'}:
        if require_digital_file and (not ebook_file or not ebook_file.filename):
            raise ValueError('Digital and hybrid books require an e-book file.')
        if ebook_file and ebook_file.filename:
            old_path = book.ebook_file_path
            new_rel_path, original_name = _save_ebook_file(ebook_file)
            book.ebook_file_path = new_rel_path
            book.ebook_filename = original_name
            if old_path and old_path != new_rel_path:
                _delete_ebook_file(old_path)
        if ebook_access_level == 'preview_only':
            ebook_download_allowed = False
    elif request.form.get('remove_ebook') == '1':
        old_path = book.ebook_file_path
        book.ebook_file_path = None
        book.ebook_filename = None
        _delete_ebook_file(old_path)
        ebook_access_level = 'full_read'
        ebook_download_allowed = True
        ebook_preview_page_limit = None

    isbn = (request.form.get('isbn') or '').strip() or None
    if isbn:
        duplicate_query = LibraryBook.query.filter_by(college_id=_college_id(), isbn=isbn)
        if book.id:
            duplicate_query = duplicate_query.filter(LibraryBook.id != book.id)
        if duplicate_query.first():
            raise ValueError('Another library book already uses that ISBN.')

    book.college_id = _college_id()
    book.category_id = category.id if category else None
    book.department_id = department_id or None
    book.subject_id = subject_id or None
    book.default_location_id = default_location.id if default_location else None
    book.title = title
    book.author = author
    book.isbn = isbn
    book.publisher = (request.form.get('publisher') or '').strip() or None
    book.edition = (request.form.get('edition') or '').strip() or None
    book.language = (request.form.get('language') or '').strip() or None
    book.semester = request.form.get('semester', type=int) or None
    if default_location and default_location.semester and book.semester and default_location.semester != book.semester:
        raise ValueError('Selected default location belongs to a different semester.')
    if default_location and not book.semester and default_location.semester:
        book.semester = default_location.semester
    book.book_type = book_type
    book.ebook_access_level = ebook_access_level
    book.ebook_download_allowed = ebook_download_allowed
    book.ebook_preview_page_limit = ebook_preview_page_limit if ebook_access_level == 'preview_only' else None
    book.description = (request.form.get('description') or '').strip() or None
    book.tags = (request.form.get('tags') or '').strip() or None
    book.shelf_code = (request.form.get('shelf_code') or '').strip() or None
    book.is_active = request.form.get('is_active', '1') == '1'


def _next_accession_number(book: LibraryBook, offset: int = 1) -> str:
    current_count = LibraryBookCopy.query.filter_by(college_id=book.college_id, book_id=book.id).count()
    return f'LB-{book.id:04d}-{current_count + offset:03d}'


def _add_copies(
    book: LibraryBook,
    quantity: int,
    *,
    location: LibraryLocation | None = None,
    rack_location: str | None = None,
) -> int:
    if quantity <= 0:
        return 0
    if location and book.department_id and location.department_id and location.department_id != book.department_id:
        raise ValueError('Selected copy location belongs to a different department.')
    if location and book.subject_id and location.subject_id and location.subject_id != book.subject_id:
        raise ValueError('Selected copy location belongs to a different subject.')
    if location and book.semester and location.semester and location.semester != book.semester:
        raise ValueError('Selected copy location belongs to a different semester.')
    created = 0
    for index in range(quantity):
        accession_number = _next_accession_number(book, index + 1)
        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            location_id=location.id if location else book.default_location_id,
            accession_number=accession_number,
            barcode=accession_number,
            rack_location=rack_location or book.shelf_code,
            condition='good',
            status='available',
        )
        db.session.add(copy)
        created += 1
    return created


def _borrower_display_options() -> dict:
    students = (
        Student.query
        .join(Student.user)
        .filter(Student.college_id == _college_id())
        .order_by(db.func.lower(Student.roll_number))
        .all()
    )
    teachers = (
        Teacher.query
        .join(Teacher.user)
        .filter(Teacher.college_id == _college_id())
        .order_by(db.func.lower(Teacher.employee_id))
        .all()
    )
    return {'students': students, 'teachers': teachers}


def _catalog_query():
    query = LibraryBook.query.filter_by(college_id=_college_id(), is_active=True)

    q = (request.args.get('q') or '').strip()
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                LibraryBook.title.ilike(like),
                LibraryBook.author.ilike(like),
                LibraryBook.isbn.ilike(like),
                LibraryBook.tags.ilike(like),
            )
        )

    category_id = request.args.get('category_id', type=int)
    if category_id:
        query = query.filter(LibraryBook.category_id == category_id)

    book_format = (request.args.get('format') or '').strip()
    if book_format == 'physical':
        query = query.filter(LibraryBook.book_type.in_(['physical', 'hybrid']))
    elif book_format == 'digital':
        query = query.filter(LibraryBook.book_type.in_(['digital', 'hybrid']))

    department_id = request.args.get('department_id', type=int)
    if department_id:
        query = query.filter(LibraryBook.department_id == department_id)

    semester = request.args.get('semester', type=int)
    if semester:
        query = query.filter(LibraryBook.semester == semester)

    subject_id = request.args.get('subject_id', type=int)
    if subject_id:
        query = query.filter(LibraryBook.subject_id == subject_id)

    if current_user.role == 'student' and current_user.student_profile:
        student = current_user.student_profile
        query = query.filter(
            db.or_(
                LibraryBook.department_id.is_(None),
                LibraryBook.department_id == student.department_id,
            )
        )
        query = query.filter(LibraryBook.semester == student.semester)

    return query.order_by(LibraryBook.title.asc()), {
        'q': q,
        'category_id': category_id,
        'format': book_format,
        'department_id': department_id,
        'semester': semester,
        'subject_id': subject_id,
    }


def _current_loans_for_book(book_id: int):
    return (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == _college_id(),
            LibraryLoan.book_id == book_id,
            LibraryLoan.status.in_(['active', 'overdue']),
        )
        .order_by(LibraryLoan.due_at.asc())
        .all()
    )


@library_bp.route('/library')
@login_required
def index():
    _ensure_library_user()
    if _can_manage_library():
        return redirect(url_for('library.admin_dashboard'))
    if current_user.role in {'teacher', 'student'}:
        return redirect(url_for('library.catalog'))
    if current_user.role == 'parent':
        return redirect(url_for('library.parent_overview'))
    abort(403)


@library_bp.route('/library/admin')
@login_required
def admin_dashboard():
    if not _can_manage_library():
        abort(403)
    _refresh_library_runtime_state(_college_id())
    can_operate = _can_operate_library()
    circulation_url = url_for('library.circulation_desk') if can_operate else None
    library_rule = _library_rule_for_college()
    borrower_rules = {
        'student': _policy_for_borrower(library_rule, 'student'),
        'teacher': _policy_for_borrower(library_rule, 'teacher'),
    }
    book_query = LibraryBook.query.filter_by(college_id=_college_id())
    q = (request.args.get('q') or '').strip()
    if q:
        like = f'%{q}%'
        book_query = book_query.filter(
            db.or_(
                LibraryBook.title.ilike(like),
                LibraryBook.author.ilike(like),
                LibraryBook.isbn.ilike(like),
            )
        )
    books = book_query.order_by(LibraryBook.created_at.desc()).all()

    active_loans = (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == _college_id(),
            LibraryLoan.status.in_(['active', 'overdue']),
        )
        .order_by(LibraryLoan.due_at.asc())
        .all()
    )
    recent_access_logs = (
        LibraryAccessLog.query
        .filter_by(college_id=_college_id())
        .order_by(LibraryAccessLog.accessed_at.desc())
        .limit(8)
        .all()
    )
    recent_loans = (
        LibraryLoan.query
        .filter(LibraryLoan.college_id == _college_id())
        .order_by(LibraryLoan.issued_at.desc())
        .limit(8)
        .all()
    )
    pending_reservations = (
        LibraryReservation.query
        .filter(
            LibraryReservation.college_id == _college_id(),
            LibraryReservation.status.in_(['pending', 'ready_for_pickup']),
        )
        .order_by(
            db.case((LibraryReservation.status == 'ready_for_pickup', 0), else_=1),
            LibraryReservation.created_at.asc(),
        )
        .limit(12)
        .all()
    )
    outstanding_fines = _outstanding_fine_query().all()
    pending_fines = outstanding_fines[:12]
    recent_location_updates = (
        LibraryLocation.query
        .filter_by(college_id=_college_id())
        .order_by(LibraryLocation.updated_at.desc())
        .limit(8)
        .all()
    )
    recent_inventory_events = (
        LibraryCopyEvent.query
        .filter_by(college_id=_college_id())
        .order_by(LibraryCopyEvent.created_at.desc())
        .limit(8)
        .all()
    )

    stats = {
        'total_titles': LibraryBook.query.filter_by(college_id=_college_id()).count(),
        'physical_copies': LibraryBookCopy.query.filter_by(college_id=_college_id()).count(),
        'available_copies': LibraryBookCopy.query.filter_by(college_id=_college_id(), status='available').count(),
        'damaged_copies': LibraryBookCopy.query.filter_by(college_id=_college_id(), status='damaged').count(),
        'lost_copies': LibraryBookCopy.query.filter_by(college_id=_college_id(), status='lost').count(),
        'written_off_copies': LibraryBookCopy.query.filter_by(college_id=_college_id(), status='written_off').count(),
        'active_loans': len(active_loans),
        'overdue_loans': sum(1 for loan in active_loans if loan.status == 'overdue'),
        'digital_titles': LibraryBook.query.filter(
            LibraryBook.college_id == _college_id(),
            LibraryBook.book_type.in_(['digital', 'hybrid']),
        ).count(),
        'pending_reservations': LibraryReservation.query.filter(
            LibraryReservation.college_id == _college_id(),
            LibraryReservation.status.in_(['pending', 'ready_for_pickup']),
        ).count(),
        'pending_fines': len(outstanding_fines),
        'outstanding_fine_total': _fine_total(outstanding_fines),
        'location_nodes': LibraryLocation.query.filter_by(college_id=_college_id()).count(),
        'total_racks': LibraryLocation.query.filter_by(college_id=_college_id(), location_type='rack').count(),
        'assigned_cells': LibraryLocation.query.filter(
            LibraryLocation.college_id == _college_id(),
            LibraryLocation.location_type == 'cell',
            db.or_(
                LibraryLocation.department_id.isnot(None),
                LibraryLocation.subject_id.isnot(None),
                LibraryLocation.semester.isnot(None),
            ),
        ).count(),
        'total_categories': LibraryCategory.query.filter_by(college_id=_college_id()).count(),
    }

    available_copies = []
    borrower_options = {'students': [], 'teachers': []}
    if can_operate:
        available_copies = (
            LibraryBookCopy.query
            .join(LibraryBook, LibraryBook.id == LibraryBookCopy.book_id)
            .filter(
                LibraryBookCopy.college_id == _college_id(),
                LibraryBookCopy.status == 'available',
                LibraryBook.is_active.is_(True),
                LibraryBook.book_type.in_(['physical', 'hybrid']),
            )
            .order_by(LibraryBook.title.asc(), LibraryBookCopy.accession_number.asc())
            .all()
        )
        borrower_options = _borrower_display_options()
    suggested_fines = {loan.id: _suggested_fine_for_loan(loan, library_rule) for loan in active_loans}

    categories = LibraryCategory.query.filter_by(college_id=_college_id()).order_by(LibraryCategory.name.asc()).all()
    location_roots = _location_roots()
    departments = Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all()
    subjects = Subject.query.filter_by(college_id=_college_id()).order_by(Subject.name.asc()).all()

    return render_template(
        'library/admin_dashboard.html',
        can_operate=can_operate,
        circulation_url=circulation_url,
        is_overseer=_is_library_overseer(),
        stats=stats,
        books=books,
        q=q,
        active_loans=active_loans,
        recent_loans=recent_loans,
        pending_reservations=pending_reservations,
        pending_fines=pending_fines,
        recent_location_updates=recent_location_updates,
        available_copies=available_copies,
        categories=categories,
        borrower_options=borrower_options,
        recent_access_logs=recent_access_logs,
        recent_inventory_events=recent_inventory_events,
        location_roots=location_roots,
        library_rule=library_rule,
        borrower_rules=borrower_rules,
        suggested_fines=suggested_fines,
        departments=departments,
        subjects=subjects,
    )


@library_bp.route('/library/circulation')
@login_required
def circulation_desk():
    if not _can_operate_library():
        abort(403)
    _refresh_library_runtime_state(_college_id())
    library_rule = _library_rule_for_college()
    borrower_rules = {
        'student': _policy_for_borrower(library_rule, 'student'),
        'teacher': _policy_for_borrower(library_rule, 'teacher'),
    }
    active_loans = (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == _college_id(),
            LibraryLoan.status.in_(['active', 'overdue']),
        )
        .order_by(LibraryLoan.due_at.asc())
        .all()
    )
    pending_reservations = (
        LibraryReservation.query
        .filter(
            LibraryReservation.college_id == _college_id(),
            LibraryReservation.status.in_(['pending', 'ready_for_pickup']),
        )
        .order_by(
            db.case((LibraryReservation.status == 'ready_for_pickup', 0), else_=1),
            LibraryReservation.created_at.asc(),
        )
        .limit(12)
        .all()
    )
    pending_fines = _outstanding_fine_query().limit(12).all()
    available_copies = (
        LibraryBookCopy.query
        .join(LibraryBook, LibraryBook.id == LibraryBookCopy.book_id)
        .filter(
            LibraryBookCopy.college_id == _college_id(),
            LibraryBookCopy.status == 'available',
            LibraryBook.is_active.is_(True),
            LibraryBook.book_type.in_(['physical', 'hybrid']),
        )
        .order_by(LibraryBook.title.asc(), LibraryBookCopy.accession_number.asc())
        .all()
    )
    inventory_copies = (
        LibraryBookCopy.query
        .join(LibraryBook, LibraryBook.id == LibraryBookCopy.book_id)
        .filter(
            LibraryBookCopy.college_id == _college_id(),
            LibraryBook.book_type.in_(['physical', 'hybrid']),
        )
        .order_by(LibraryBook.title.asc(), LibraryBookCopy.accession_number.asc())
        .all()
    )
    recent_inventory_events = (
        LibraryCopyEvent.query
        .filter_by(college_id=_college_id())
        .order_by(LibraryCopyEvent.created_at.desc())
        .limit(12)
        .all()
    )
    departments = Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all()
    subjects = Subject.query.filter_by(college_id=_college_id()).order_by(Subject.name.asc()).all()
    borrower_options = _borrower_display_options()
    suggested_fines = {loan.id: _suggested_fine_for_loan(loan, library_rule) for loan in active_loans}
    return render_template(
        'library/circulation_desk.html',
        library_rule=library_rule,
        borrower_rules=borrower_rules,
        active_loans=active_loans,
        pending_reservations=pending_reservations,
        pending_fines=pending_fines,
        available_copies=available_copies,
        inventory_copies=inventory_copies,
        copy_action_options={copy.id: _copy_inventory_action_choices(copy) for copy in inventory_copies},
        recent_inventory_events=recent_inventory_events,
        departments=departments,
        subjects=subjects,
        borrower_options=borrower_options,
        suggested_fines=suggested_fines,
    )


@library_bp.route('/library/audits')
@login_required
def stock_audit():
    if not _can_operate_library():
        abort(403)
    _refresh_library_runtime_state(_college_id())

    active_session_id = request.args.get('session_id', type=int)
    active_session = None
    if active_session_id:
        active_session = _scoped_audit_session_or_404(active_session_id)
    else:
        active_session = (
            LibraryAuditSession.query
            .filter_by(college_id=_college_id(), status='open')
            .order_by(LibraryAuditSession.started_at.desc())
            .first()
        )

    open_sessions = (
        LibraryAuditSession.query
        .filter_by(college_id=_college_id(), status='open')
        .order_by(LibraryAuditSession.started_at.desc())
        .all()
    )
    completed_sessions = (
        LibraryAuditSession.query
        .filter_by(college_id=_college_id(), status='completed')
        .order_by(LibraryAuditSession.completed_at.desc())
        .limit(12)
        .all()
    )

    audit_entries = []
    if active_session is not None:
        audit_entries = (
            LibraryAuditEntry.query
            .join(LibraryBookCopy, LibraryBookCopy.id == LibraryAuditEntry.copy_id)
            .join(LibraryBook, LibraryBook.id == LibraryBookCopy.book_id)
            .filter(LibraryAuditEntry.session_id == active_session.id)
            .order_by(
                LibraryAuditEntry.is_present.desc(),
                LibraryAuditEntry.discrepancy_status.asc(),
                LibraryBook.title.asc(),
                LibraryBookCopy.accession_number.asc(),
            )
            .all()
        )

    overview = {
        'auditable_copies': _auditable_copies_query().count(),
        'open_sessions': len(open_sessions),
        'completed_sessions': len(completed_sessions),
    }

    return render_template(
        'library/stock_audit.html',
        active_session=active_session,
        open_sessions=open_sessions,
        completed_sessions=completed_sessions,
        audit_entries=audit_entries,
        discrepancy_action_options={entry.id: _audit_discrepancy_action_choices(entry) for entry in audit_entries},
        rack_choices=_active_rack_locations(),
        overview=overview,
    )


@library_bp.route('/library/audits', methods=['POST'])
@login_required
def create_stock_audit():
    if not _can_operate_library():
        abort(403)

    rack_id = request.form.get('rack_id', type=int) or None
    title = (request.form.get('title') or '').strip() or 'Library Stock Audit'
    notes = (request.form.get('notes') or '').strip() or None

    existing_open = LibraryAuditSession.query.filter_by(college_id=_college_id(), status='open').first()
    if existing_open is not None:
        flash('Finish the current open stock audit before starting a new one.', 'warning')
        return redirect(url_for('library.stock_audit', session_id=existing_open.id))

    copies = (
        _auditable_copies_query(rack_id=rack_id)
        .order_by(LibraryBookCopy.accession_number.asc())
        .all()
    )
    if not copies:
        flash('No auditable physical copies matched the selected scope.', 'warning')
        return redirect(url_for('library.stock_audit'))

    audit_session = LibraryAuditSession(
        college_id=_college_id(),
        rack_id=rack_id,
        created_by_user_id=current_user.id,
        title=title,
        notes=notes,
        status='open',
        expected_count=len(copies),
    )
    db.session.add(audit_session)
    db.session.flush()

    for copy in copies:
        db.session.add(
            LibraryAuditEntry(
                session_id=audit_session.id,
                copy_id=copy.id,
                expected_status=copy.status,
                expected_condition=copy.condition,
            )
        )

    db.session.commit()
    flash(f'Stock audit started with {len(copies)} expected copy/copies.', 'success')
    return redirect(url_for('library.stock_audit', session_id=audit_session.id))


@library_bp.route('/library/audits/<int:session_id>/scan', methods=['POST'])
@login_required
def scan_stock_audit_copy(session_id: int):
    if not _can_operate_library():
        abort(403)
    audit_session = _scoped_audit_session_or_404(session_id)
    if audit_session.status != 'open':
        flash('This stock audit session is already completed.', 'warning')
        return redirect(url_for('library.stock_audit', session_id=audit_session.id))

    copy = _resolve_copy_from_scan((request.form.get('copy_scan') or '').strip())
    if copy is None:
        flash('Copy scan did not match any library barcode or accession number.', 'warning')
        return redirect(url_for('library.stock_audit', session_id=audit_session.id))

    entry = LibraryAuditEntry.query.filter_by(session_id=audit_session.id, copy_id=copy.id).first()
    if entry is None:
        flash('That copy is outside the selected stock-audit scope.', 'warning')
        return redirect(url_for('library.stock_audit', session_id=audit_session.id))

    if not entry.is_present:
        entry.is_present = True
        entry.scanned_at = utc_now_naive()
        entry.scanned_by_user_id = current_user.id
        audit_session.scanned_count = sum(1 for item in audit_session.entries if item.is_present)
        db.session.commit()
        flash(f'{copy.accession_number} verified in stock.', 'success')
    else:
        flash(f'{copy.accession_number} was already verified in this audit.', 'info')

    return redirect(url_for('library.stock_audit', session_id=audit_session.id))


@library_bp.route('/library/audits/entries/<int:entry_id>/toggle', methods=['POST'])
@login_required
def toggle_stock_audit_entry(entry_id: int):
    if not _can_operate_library():
        abort(403)
    entry = db.session.get(LibraryAuditEntry, entry_id)
    if entry is None or entry.session.college_id != _college_id():
        abort(404)
    if entry.session.status != 'open':
        flash('This stock audit session is already completed.', 'warning')
        return redirect(url_for('library.stock_audit', session_id=entry.session_id))

    entry.is_present = not entry.is_present
    entry.scanned_at = utc_now_naive() if entry.is_present else None
    entry.scanned_by_user_id = current_user.id if entry.is_present else None
    entry.session.scanned_count = sum(1 for item in entry.session.entries if item.is_present)
    db.session.commit()
    flash(f"{entry.copy.accession_number} marked as {'present' if entry.is_present else 'missing'} for this audit.", 'success')
    return redirect(url_for('library.stock_audit', session_id=entry.session_id))


@library_bp.route('/library/audits/<int:session_id>/finalize', methods=['POST'])
@login_required
def finalize_stock_audit(session_id: int):
    if not _can_operate_library():
        abort(403)
    audit_session = _scoped_audit_session_or_404(session_id)
    if audit_session.status != 'open':
        flash('This stock audit session is already completed.', 'info')
        return redirect(url_for('library.stock_audit', session_id=audit_session.id))

    audit_session.scanned_count = sum(1 for entry in audit_session.entries if entry.is_present)
    audit_session.missing_count = max(audit_session.expected_count - audit_session.scanned_count, 0)
    audit_session.status = 'completed'
    audit_session.completed_at = utc_now_naive()
    audit_session.completed_by_user_id = current_user.id
    db.session.commit()
    flash(
        f"Stock audit completed. Verified {audit_session.scanned_count} of {audit_session.expected_count} expected copies. Missing: {audit_session.missing_count}.",
        'success',
    )
    return redirect(url_for('library.stock_audit', session_id=audit_session.id))


@library_bp.route('/library/audits/entries/<int:entry_id>/resolve', methods=['POST'])
@login_required
def resolve_stock_audit_discrepancy(entry_id: int):
    if not _can_operate_library():
        abort(403)
    entry = db.session.get(LibraryAuditEntry, entry_id)
    if entry is None or entry.session.college_id != _college_id():
        abort(404)
    if entry.session.status != 'completed':
        flash('Finish the audit session before resolving discrepancies.', 'warning')
        return redirect(url_for('library.stock_audit', session_id=entry.session_id))
    if entry.is_present:
        flash('This audit entry is already verified as present.', 'info')
        return redirect(url_for('library.stock_audit', session_id=entry.session_id))

    action = (request.form.get('discrepancy_action') or '').strip()
    note = (request.form.get('note') or '').strip() or None
    allowed_actions = {value for value, _ in _audit_discrepancy_action_choices(entry)}
    if action not in allowed_actions:
        flash('That discrepancy action is not available for this audit entry.', 'warning')
        return redirect(url_for('library.stock_audit', session_id=entry.session_id))

    try:
        ready_reservation = None
        if action == 'follow_up_required':
            _append_audit_entry_note(entry, note)
            _append_copy_note(entry.copy, note)
            _log_copy_event(
                entry.copy,
                action='audit_follow_up_required',
                previous_status=entry.copy.status,
                new_status=entry.copy.status,
                previous_condition=entry.copy.condition,
                new_condition=entry.copy.condition,
                note=note or f'Follow-up required from audit session {entry.session.title}.',
            )
            _notify_audit_follow_up(entry)
        elif action == 'marked_lost':
            result = _apply_copy_inventory_action(
                entry.copy,
                action='mark_lost',
                note=note or f'Marked lost from audit session {entry.session.title}.',
            )
            ready_reservation = result.get('ready_reservation')
        elif action == 'marked_damaged':
            result = _apply_copy_inventory_action(
                entry.copy,
                action='mark_damaged',
                note=note or f'Marked damaged from audit session {entry.session.title}.',
            )
            ready_reservation = result.get('ready_reservation')
        else:
            raise ValueError('Unsupported discrepancy action.')

        entry.discrepancy_status = action
        entry.resolved_at = utc_now_naive()
        entry.resolved_by_user_id = current_user.id
        _append_audit_entry_note(entry, note)
        db.session.commit()
        flash(f'{entry.copy.accession_number} updated from the audit discrepancy workflow.', 'success')
        if ready_reservation is not None:
            flash(
                f"Hold for {ready_reservation.borrower_label} was released and moved back into the reservation queue.",
                'info',
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')

    return redirect(url_for('library.stock_audit', session_id=entry.session_id))


@library_bp.route('/library/rules', methods=['POST'])
@login_required
def update_rules():
    if not _is_library_overseer():
        abort(403)

    rule = LibraryRule.query.filter_by(college_id=_college_id()).first()
    if rule is None:
        rule = LibraryRule(college_id=_college_id(), **_library_rule_defaults())
        db.session.add(rule)

    try:
        _assign_library_rule_fields(rule)
        db.session.commit()
        flash('Library circulation rules updated.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')

    return redirect(url_for('library.admin_dashboard'))


@library_bp.route('/library/locations')
@login_required
def manage_locations():
    if not _can_operate_library():
        abort(403)

    q = (request.args.get('q') or '').strip()
    department_id = request.args.get('department_id', type=int)
    semester = request.args.get('semester', type=int)
    subject_id = request.args.get('subject_id', type=int)

    edit_location = None
    edit_id = request.args.get('edit_id', type=int)
    if edit_id:
        edit_location = _scoped_location_or_404(edit_id)

    location_roots = _prune_location_tree(
        _location_roots(),
        query=q,
        department_id=department_id,
        semester=semester,
        subject_id=subject_id,
    )

    return render_template(
        'library/hierarchy_tree.html',
        location_roots=location_roots,
        departments=Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all(),
        subjects=Subject.query.filter_by(college_id=_college_id()).order_by(Subject.name.asc()).all(),
        filters={'q': q, 'department_id': department_id, 'semester': semester, 'subject_id': subject_id},
        edit_location=edit_location,
    )


@library_bp.route('/library/racks')
@login_required
def manage_racks():
    if not _can_operate_library():
        abort(403)

    q = (request.args.get('q') or '').strip()
    edit_rack = None
    edit_id = request.args.get('edit_id', type=int)
    if edit_id:
        edit_rack = _scoped_location_or_404(edit_id)
        if edit_rack.location_type != 'rack':
            abort(404)

    return render_template(
        'library/rack_setup.html',
        racks=_filter_racks(_active_rack_locations(), q),
        parent_choices=_non_cell_location_choices(include_inactive=True, exclude=edit_rack),
        filters={'q': q},
        edit_rack=edit_rack,
    )


@library_bp.route('/library/rack-assignments')
@login_required
def manage_rack_assignments():
    if not _can_operate_library():
        abort(403)

    q = (request.args.get('q') or '').strip()
    rack_id = request.args.get('rack_id', type=int)
    department_id = request.args.get('department_id', type=int)
    semester = request.args.get('semester', type=int)
    subject_id = request.args.get('subject_id', type=int)

    edit_cell = None
    edit_id = request.args.get('edit_id', type=int)
    if edit_id:
        edit_cell = _scoped_location_or_404(edit_id)
        if edit_cell.location_type != 'cell':
            abort(404)

    rack_groups = _filter_rack_assignment_groups(
        _rack_assignment_groups(),
        query=q,
        rack_id=rack_id,
        department_id=department_id,
        semester=semester,
        subject_id=subject_id,
    )

    return render_template(
        'library/rack_assignments.html',
        cells=_rack_cells(),
        rack_groups=rack_groups,
        rack_choices=_active_rack_locations(),
        departments=Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all(),
        subjects=Subject.query.filter_by(college_id=_college_id()).order_by(Subject.name.asc()).all(),
        filters={
            'q': q,
            'rack_id': rack_id,
            'department_id': department_id,
            'semester': semester,
            'subject_id': subject_id,
        },
        edit_cell=edit_cell,
    )


@library_bp.route('/library/locations/create', methods=['POST'])
@login_required
def create_location():
    if not _can_operate_library():
        abort(403)

    location = LibraryLocation()
    try:
        _assign_location_fields(location)
        db.session.add(location)
        db.session.flush()
        _sync_rack_grid_cells(location)
        db.session.commit()
        flash('Library location created.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for(_location_redirect_target()))


@library_bp.route('/library/locations/<int:location_id>/edit', methods=['POST'])
@login_required
def edit_location(location_id: int):
    if not _can_operate_library():
        abort(403)

    location = _scoped_location_or_404(location_id)
    try:
        _assign_location_fields(location)
        db.session.flush()
        _sync_rack_grid_cells(location)
        db.session.commit()
        flash('Library location updated.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for(_location_redirect_target(), edit_id=location.id))
    return redirect(url_for(_location_redirect_target()))


@library_bp.route('/library/locations/<int:location_id>/delete', methods=['POST'])
@login_required
def delete_location(location_id: int):
    if not _can_operate_library():
        abort(403)

    location = _scoped_location_or_404(location_id)
    try:
        branch_ids = _location_branch_ids(location)
        linked_book = (
            LibraryBook.query
            .filter(
                LibraryBook.college_id == _college_id(),
                LibraryBook.default_location_id.in_(branch_ids),
            )
            .first()
        )
        if linked_book:
            raise ValueError(f'Cannot delete this location because "{linked_book.title}" is assigned to it.')

        linked_copy = (
            LibraryBookCopy.query
            .filter(
                LibraryBookCopy.college_id == _college_id(),
                LibraryBookCopy.location_id.in_(branch_ids),
            )
            .first()
        )
        if linked_copy:
            raise ValueError(f'Cannot delete this location because copy "{linked_copy.accession_number}" is stored there.')

        nodes = _location_branch_nodes(location)
        deleted_children = max(0, len(nodes) - 1)
        label = location.full_label
        for node in nodes:
            db.session.delete(node)
        db.session.commit()
        if deleted_children:
            flash(f'Deleted {label} and {deleted_children} child node(s).', 'success')
        else:
            flash(f'Deleted {label}.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for(_location_redirect_target()))


@library_bp.route('/library/books/create', methods=['GET', 'POST'])
@login_required
def create_book():
    if not _can_operate_library():
        abort(403)
    categories = LibraryCategory.query.filter_by(college_id=_college_id()).order_by(LibraryCategory.name.asc()).all()
    departments = Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all()
    subjects = Subject.query.filter_by(college_id=_college_id()).order_by(Subject.name.asc()).all()
    location_choices = _active_library_locations()
    rack_choices = _active_rack_locations()

    if request.method == 'POST':
        book = LibraryBook()
        try:
            _assign_book_fields(book, require_digital_file=True)
            db.session.add(book)
            db.session.flush()
            initial_copy_count = request.form.get('initial_copy_count', type=int) or 0
            if book.book_type in {'physical', 'hybrid'} and initial_copy_count <= 0:
                initial_copy_count = 1
            created_copies = _add_copies(
                book,
                initial_copy_count,
                location=_resolve_book_location_from_form(field_prefix='initial_location'),
                rack_location=(request.form.get('rack_location') or '').strip() or None,
            )
            db.session.commit()
            flash(f'Library book created with {created_copies} copy/copies.', 'success')
            return redirect(url_for('library.book_detail', book_id=book.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')

    return render_template(
        'library/book_form.html',
        book=None,
        categories=categories,
        departments=departments,
        subjects=subjects,
        location_choices=location_choices,
        rack_choices=rack_choices,
        default_rack=None,
        default_row='',
        default_column='',
        book_types=LIBRARY_BOOK_TYPES,
        ebook_access_levels=LIBRARY_EBOOK_ACCESS_LEVELS,
    )


@library_bp.route('/library/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_book(book_id: int):
    if not _can_operate_library():
        abort(403)
    book = _scoped_book_or_404(book_id)
    categories = LibraryCategory.query.filter_by(college_id=_college_id()).order_by(LibraryCategory.name.asc()).all()
    departments = Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all()
    subjects = Subject.query.filter_by(college_id=_college_id()).order_by(Subject.name.asc()).all()
    location_choices = _active_library_locations()
    rack_choices = _active_rack_locations()
    default_rack, default_row, default_column = _rack_defaults_for_location(book.default_location)

    if request.method == 'POST':
        try:
            _assign_book_fields(book, require_digital_file=False)
            db.session.commit()
            flash('Library book updated.', 'success')
            return redirect(url_for('library.book_detail', book_id=book.id))
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'danger')

    return render_template(
        'library/book_form.html',
        book=book,
        categories=categories,
        departments=departments,
        subjects=subjects,
        location_choices=location_choices,
        rack_choices=rack_choices,
        default_rack=default_rack,
        default_row=default_row,
        default_column=default_column,
        book_types=LIBRARY_BOOK_TYPES,
        ebook_access_levels=LIBRARY_EBOOK_ACCESS_LEVELS,
    )


@library_bp.route('/library/books/<int:book_id>/delete', methods=['POST'])
@login_required
def delete_book(book_id: int):
    if not _can_operate_library():
        abort(403)

    book = _scoped_book_or_404(book_id)
    try:
        active_loan = next((loan for loan in book.loans if loan.is_active), None)
        if active_loan is not None:
            raise ValueError('Cannot delete a book while it still has active or overdue loans.')

        title = book.title
        ebook_path = book.ebook_file_path
        db.session.delete(book)
        db.session.commit()
        _delete_ebook_file(ebook_path)
        flash(f'Deleted "{title}" from the library.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('library.book_detail', book_id=book.id))
    return redirect(url_for(_book_redirect_target()))


@library_bp.route('/library/books/<int:book_id>/copies', methods=['POST'])
@login_required
def add_copies(book_id: int):
    if not _can_operate_library():
        abort(403)
    book = _scoped_book_or_404(book_id)
    quantity = request.form.get('quantity', type=int) or 0
    if book.book_type not in {'physical', 'hybrid'}:
        flash('Digital-only books cannot have physical copies.', 'warning')
        return redirect(url_for('library.book_detail', book_id=book.id))
    if quantity <= 0:
        flash('Enter a valid quantity of copies to add.', 'warning')
        return redirect(url_for('library.book_detail', book_id=book.id))

    try:
        created = _add_copies(
            book,
            quantity,
            location=_resolve_book_location_from_form(field_prefix='copy_location'),
            rack_location=(request.form.get('rack_location') or '').strip() or None,
        )
        db.session.commit()
        flash(f'Added {created} new copy/copies.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for('library.book_detail', book_id=book.id))


@library_bp.route('/library/copies/<int:copy_id>/workflow', methods=['POST'])
@login_required
def update_copy_workflow(copy_id: int):
    if not _can_operate_library():
        abort(403)
    _refresh_library_runtime_state(_college_id())
    copy = _scoped_copy_or_404(copy_id)
    action = (request.form.get('workflow_action') or '').strip()
    note = (request.form.get('workflow_note') or '').strip() or None
    restored_condition = (request.form.get('restored_condition') or '').strip() or None
    try:
        result = _apply_copy_inventory_action(
            copy,
            action=action,
            note=note,
            restored_condition=restored_condition,
        )
        db.session.commit()
        flash(result['message'], 'success')
        if result.get('ready_reservation') is not None:
            flash(
                f"Hold for {result['ready_reservation'].borrower_label} was released and moved back into the reservation queue.",
                'info',
            )
        if result.get('replacement_copy') is not None:
            flash(
                f"Replacement copy {result['replacement_copy'].accession_number} is now available for circulation.",
                'info',
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    return redirect(url_for('library.book_detail', book_id=copy.book_id))


@library_bp.route('/library/copies/workflow/scan', methods=['POST'])
@login_required
def update_copy_workflow_from_scan():
    if not _can_operate_library():
        abort(403)
    _refresh_library_runtime_state(_college_id())
    copy = _scoped_copy_or_404(request.form.get('copy_id', type=int)) if request.form.get('copy_id', type=int) else _resolve_copy_from_scan((request.form.get('copy_scan') or '').strip())
    if copy is None:
        flash('Copy scan did not match any library barcode or accession number.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    action = (request.form.get('workflow_action') or '').strip()
    note = (request.form.get('workflow_note') or '').strip() or None
    restored_condition = (request.form.get('restored_condition') or '').strip() or None
    try:
        result = _apply_copy_inventory_action(
            copy,
            action=action,
            note=note,
            restored_condition=restored_condition,
        )
        db.session.commit()
        flash(result['message'], 'success')
        if result.get('ready_reservation') is not None:
            flash(
                f"Hold for {result['ready_reservation'].borrower_label} was released and moved back into the reservation queue.",
                'info',
            )
        if result.get('replacement_copy') is not None:
            flash(
                f"Replacement copy {result['replacement_copy'].accession_number} is now available for circulation.",
                'info',
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'warning')
    return redirect(url_for(_circulation_redirect_target()))


@library_bp.route('/library/books/<int:book_id>')
@login_required
def book_detail(book_id: int):
    _ensure_library_user()
    book = _scoped_book_or_404(book_id)
    if not _student_can_access_book(book):
        abort(404)
    _refresh_library_runtime_state(_college_id())

    current_loans = _current_loans_for_book(book.id)
    pending_reservations = _pending_reservations_for_book(book.id)
    recent_access_logs = (
        LibraryAccessLog.query
        .filter_by(college_id=_college_id(), book_id=book.id)
        .order_by(LibraryAccessLog.accessed_at.desc())
        .limit(10)
        .all()
    )
    can_preview_ebook = _can_open_ebook_reader(book)
    can_download_ebook = _can_download_ebook(book)
    reader_progress = _reader_progress_for_current_user(book.id) if can_preview_ebook else None
    ebook_extension = _ebook_extension(book)
    ebook_total_pages = None
    if book.digital_enabled:
        try:
            ebook_total_pages = _ebook_total_pages(_ebook_file_or_404(book), extension=ebook_extension)
        except Exception:
            ebook_total_pages = None
    recent_inventory_events = (
        LibraryCopyEvent.query
        .filter_by(college_id=_college_id(), book_id=book.id)
        .order_by(LibraryCopyEvent.created_at.desc())
        .limit(12)
        .all()
    )

    default_rack, default_row, default_column = _rack_defaults_for_location(book.default_location)
    return render_template(
        'library/book_detail.html',
        book=book,
        current_loans=current_loans,
        pending_reservations=pending_reservations,
        recent_access_logs=recent_access_logs,
        can_preview_ebook=can_preview_ebook,
        can_download_ebook=can_download_ebook,
        reader_progress=reader_progress,
        ebook_total_pages=ebook_total_pages,
        ebook_preview_limit=_ebook_preview_page_limit(book),
        current_user_reservation=_pending_reservation_for_user(book.id),
        location_choices=_active_library_locations(),
        rack_choices=_active_rack_locations(),
        default_rack=default_rack,
        default_row=default_row,
        default_column=default_column,
        ebook_extension=ebook_extension,
        recent_inventory_events=recent_inventory_events,
        copy_action_options={copy.id: _copy_inventory_action_choices(copy) for copy in book.copies},
    )


@library_bp.route('/library/catalog')
@login_required
def catalog():
    _ensure_library_user()
    if current_user.role not in {'admin', 'sub_admin', 'librarian', 'teacher', 'student'}:
        abort(403)
    _refresh_library_runtime_state(_college_id())

    page = max(request.args.get('page', 1, type=int), 1)
    query, filters = _catalog_query()
    pagination = query.paginate(page=page, per_page=20, error_out=False)
    categories = LibraryCategory.query.filter_by(college_id=_college_id()).order_by(LibraryCategory.name.asc()).all()
    departments = Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all()
    subjects = Subject.query.filter_by(college_id=_college_id()).order_by(Subject.name.asc()).all()

    return render_template(
        'library/catalog.html',
        books=pagination.items,
        pagination=pagination,
        categories=categories,
        departments=departments,
        subjects=subjects,
        filters=filters,
        borrower_policy=_current_borrower_policy(),
        library_rule=_library_rule_for_college(),
        pending_reservation_book_ids=_pending_reservation_book_ids_for_user(),
    )


@library_bp.route('/library/issue', methods=['POST'])
@login_required
def issue_book():
    if not _can_operate_library():
        abort(403)
    _refresh_library_runtime_state(_college_id())
    copy = _scoped_copy_or_404(request.form.get('copy_id', type=int))
    borrower_kind = (request.form.get('borrower_kind') or '').strip()
    borrower_id = request.form.get('borrower_id', type=int)
    borrower_ref = (request.form.get('borrower_ref') or '').strip()
    if borrower_ref and ':' in borrower_ref:
        borrower_kind, borrower_value = borrower_ref.split(':', 1)
        borrower_kind = borrower_kind.strip()
        try:
            borrower_id = int(borrower_value)
        except (TypeError, ValueError):
            borrower_id = None
    requested_due_days = request.form.get('due_days', type=int)
    notes = (request.form.get('notes') or '').strip() or None

    try:
        issue_result = _issue_copy_to_borrower(
            copy,
            borrower_kind=borrower_kind,
            borrower_id=borrower_id,
            requested_due_days=requested_due_days,
            notes=notes,
        )
        flash(f"Book issued successfully. Due in {issue_result['due_days']} day(s).", 'success')
    except ValueError as exc:
        flash(str(exc), 'warning')
    return redirect(url_for(_circulation_redirect_target()))


@library_bp.route('/library/issue/scan', methods=['POST'])
@login_required
def scan_issue_book():
    if not _can_operate_library():
        abort(403)
    _refresh_library_runtime_state(_college_id())
    borrower_scan = (request.form.get('borrower_scan') or '').strip()
    copy_scan = (request.form.get('copy_scan') or '').strip()
    requested_due_days = request.form.get('due_days', type=int)
    notes = (request.form.get('notes') or '').strip() or None

    borrower_match = _resolve_borrower_from_scan(borrower_scan)
    if borrower_match is None:
        flash('Borrower scan did not match any approved student card, roll number, or teacher employee ID.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    copy = _resolve_copy_from_scan(copy_scan)
    if copy is None:
        flash('Copy scan did not match any library barcode or accession number.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    try:
        issue_result = _issue_copy_to_borrower(
            copy,
            borrower_kind=borrower_match['borrower_kind'],
            borrower_id=borrower_match['borrower_id'],
            requested_due_days=requested_due_days,
            notes=notes,
        )
        flash(
            f"Scanned issue completed for {issue_result['borrower_label']}. Due in {issue_result['due_days']} day(s).",
            'success',
        )
    except ValueError as exc:
        flash(str(exc), 'warning')
    return redirect(url_for(_circulation_redirect_target()))


@library_bp.route('/library/books/<int:book_id>/reserve', methods=['POST'])
@login_required
def reserve_book(book_id: int):
    _ensure_library_user()
    if current_user.role not in {'student', 'teacher'}:
        abort(403)

    book = _scoped_book_or_404(book_id)
    if not _student_can_access_book(book):
        abort(404)
    if not book.physical_enabled:
        flash('Only physical library titles can be reserved.', 'warning')
        return redirect(url_for('library.book_detail', book_id=book.id))
    if book.available_copies > 0:
        flash('This title currently has available copies, so reservation is not needed.', 'info')
        return redirect(url_for('library.book_detail', book_id=book.id))

    identity = _current_borrower_identity()
    if identity is None:
        abort(403)

    existing_reservation = _pending_reservation_for_user(book.id)
    if existing_reservation is not None:
        flash('You already have an active reservation for this title.', 'info')
        return redirect(url_for('library.book_detail', book_id=book.id))

    active_loan_query = LibraryLoan.query.filter(
        LibraryLoan.college_id == _college_id(),
        LibraryLoan.book_id == book.id,
        LibraryLoan.status.in_(['active', 'overdue']),
    )
    if identity['student_id']:
        active_loan_query = active_loan_query.filter_by(student_id=identity['student_id'])
    else:
        active_loan_query = active_loan_query.filter_by(teacher_id=identity['teacher_id'])
    if active_loan_query.first() is not None:
        flash('You already have this title in your current loans.', 'info')
        return redirect(url_for('library.book_detail', book_id=book.id))

    reservation = LibraryReservation(
        college_id=_college_id(),
        book_id=book.id,
        student_id=identity['student_id'],
        teacher_id=identity['teacher_id'],
        notes=(request.form.get('notes') or '').strip() or None,
    )
    db.session.add(reservation)
    db.session.commit()
    flash('Book reservation placed successfully. Librarian will see it in the pending queue.', 'success')
    return redirect(url_for('library.book_detail', book_id=book.id))


@library_bp.route('/library/reservations/<int:reservation_id>/cancel', methods=['POST'])
@login_required
def cancel_reservation(reservation_id: int):
    _ensure_library_user()
    reservation = db.session.get(LibraryReservation, reservation_id)
    if reservation is None or reservation.college_id != _college_id():
        abort(404)
    identity = _current_borrower_identity()
    if identity is None:
        abort(403)
    if not reservation.matches_borrower(student_id=identity['student_id'], teacher_id=identity['teacher_id']):
        abort(403)
    if reservation.status not in {'pending', 'ready_for_pickup'}:
        flash('Only active reservations can be cancelled.', 'warning')
        return redirect(url_for('library.my_loans'))

    held_copy = reservation.held_copy
    reservation.status = 'cancelled'
    reservation.cancelled_at = utc_now_naive()
    reservation.pickup_expires_at = None
    reservation.ready_at = reservation.ready_at or utc_now_naive()
    reservation.held_copy_id = None
    if held_copy is not None:
        _release_copy_hold(held_copy)
        _activate_next_reservation_hold(reservation.book_id, held_copy)
    db.session.commit()
    flash('Reservation cancelled.', 'success')
    return redirect(url_for('library.my_loans'))


@library_bp.route('/library/loans/<int:loan_id>/return', methods=['POST'])
@login_required
def return_loan(loan_id: int):
    if not _can_operate_library():
        abort(403)
    loan = _scoped_loan_or_404(loan_id)
    if not loan.is_active:
        flash('This loan is already closed.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    try:
        result = _return_loan_record(loan, fine_raw=(request.form.get('fine_amount') or '').strip())
        flash(
            f"Book returned successfully.{'' if result['fine_amount'] <= 0 else f' Fine applied: Rs. {result['fine_amount']:.2f}.'}",
            'success',
        )
        if result.get('ready_reservation') is not None:
            pickup_by = result['ready_reservation'].pickup_expires_at.strftime('%d %b %Y') if result['ready_reservation'].pickup_expires_at else 'the configured deadline'
            flash(
                f"{result['ready_reservation'].borrower_label} can now pick up this title. Hold expires on {pickup_by}.",
                'info',
            )
        if result['queue_count']:
            flash(
                f"Reservation queue waiting for this title: {result['queue_count']} pending request(s).",
                'info',
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for(_circulation_redirect_target()))


@library_bp.route('/library/return/scan', methods=['POST'])
@login_required
def scan_return_book():
    if not _can_operate_library():
        abort(403)
    copy_scan = (request.form.get('copy_scan') or '').strip()
    copy = _resolve_copy_from_scan(copy_scan)
    if copy is None:
        flash('Copy scan did not match any library barcode or accession number.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    loan = (
        LibraryLoan.query
        .filter(
            LibraryLoan.college_id == _college_id(),
            LibraryLoan.copy_id == copy.id,
            LibraryLoan.status.in_(['active', 'overdue']),
        )
        .order_by(LibraryLoan.issued_at.desc())
        .first()
    )
    if loan is None:
        flash('No active loan was found for that scanned copy.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    try:
        result = _return_loan_record(loan, fine_raw=(request.form.get('fine_amount') or '').strip())
        flash(
            f"Scanned return completed for {loan.book.title}.{'' if result['fine_amount'] <= 0 else f' Fine applied: Rs. {result['fine_amount']:.2f}.'}",
            'success',
        )
        if result.get('ready_reservation') is not None:
            pickup_by = result['ready_reservation'].pickup_expires_at.strftime('%d %b %Y') if result['ready_reservation'].pickup_expires_at else 'the configured deadline'
            flash(
                f"{result['ready_reservation'].borrower_label} can now pick up this title. Hold expires on {pickup_by}.",
                'info',
            )
        if result['queue_count']:
            flash(
                f"Reservation queue waiting for this title: {result['queue_count']} pending request(s).",
                'info',
            )
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'danger')
    return redirect(url_for(_circulation_redirect_target()))


@library_bp.route('/library/fines/<int:fine_id>/settle', methods=['POST'])
@login_required
def settle_fine(fine_id: int):
    if not _can_operate_library():
        abort(403)
    fine = db.session.get(LibraryFine, fine_id)
    if fine is None or fine.college_id != _college_id():
        abort(404)

    try:
        payment_amount = _normalized_money((request.form.get('payment_amount') or '').strip() or '0')
        waive_amount = _normalized_money((request.form.get('waive_amount') or '').strip() or '0')
    except ValueError as exc:
        flash(str(exc), 'danger')
        return redirect(url_for(_circulation_redirect_target()))

    notes = (request.form.get('notes') or '').strip()
    outstanding_before = Decimal(str(fine.outstanding_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if outstanding_before <= 0:
        flash('This fine is already settled.', 'info')
        return redirect(url_for(_circulation_redirect_target()))
    if payment_amount <= 0 and waive_amount <= 0:
        flash('Enter a payment amount or waive amount to settle this fine.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))
    if payment_amount + waive_amount > outstanding_before:
        flash(f'Settlement exceeds the outstanding balance of Rs. {outstanding_before:.2f}.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    fine.amount_paid = Decimal(str(fine.amount_paid)) + payment_amount
    fine.amount_waived = Decimal(str(fine.amount_waived)) + waive_amount
    if notes:
        fine.notes = f'{fine.notes}\n{notes}'.strip() if fine.notes else notes
    fine.settled_by_user_id = current_user.id
    _recalculate_fine_status(fine)
    db.session.commit()

    outstanding_after = Decimal(str(fine.outstanding_amount)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if outstanding_after <= 0:
        flash('Fine settled successfully.', 'success')
    else:
        flash(f'Fine updated. Remaining balance: Rs. {outstanding_after:.2f}.', 'success')
    return redirect(url_for(_circulation_redirect_target()))


@library_bp.route('/library/loans/<int:loan_id>/renew', methods=['POST'])
@login_required
def renew_loan(loan_id: int):
    if not _can_operate_library():
        abort(403)
    loan = _scoped_loan_or_404(loan_id)
    if not loan.is_active:
        flash('Only active or overdue loans can be renewed.', 'warning')
        return redirect(url_for(_circulation_redirect_target()))

    library_rule = _library_rule_for_college()
    borrower_policy = _policy_for_borrower(library_rule, loan.borrower_role)
    if loan.renewed_count >= borrower_policy['max_renewals']:
        flash(
            f"Maximum renewals reached for this {borrower_policy['label'].lower()} loan.",
            'warning',
        )
        return redirect(url_for(_circulation_redirect_target()))

    extra_days = borrower_policy['renew_days']
    base_time = loan.due_at if loan.due_at > utc_now_naive() else utc_now_naive()
    loan.due_at = base_time + timedelta(days=extra_days)
    loan.renewed_count += 1
    loan.status = 'active'
    db.session.commit()
    flash(f'Loan renewed successfully for {extra_days} day(s).', 'success')
    return redirect(url_for(_circulation_redirect_target()))


@library_bp.route('/library/my-loans')
@login_required
def my_loans():
    _ensure_library_user()
    _refresh_library_runtime_state(_college_id())
    q = (request.args.get('q') or '').strip().lower()

    if current_user.role == 'student':
        student = current_user.student_profile
        if student is None:
            abort(404)
        query = LibraryLoan.query.filter_by(college_id=_college_id(), student_id=student.id)
        outstanding_fines = _fine_query_for_borrower(student_id=student.id, statuses=['unpaid', 'partial']).all()
        fine_history = _fine_query_for_borrower(student_id=student.id, statuses=['paid', 'waived']).all()
    elif current_user.role == 'teacher':
        teacher = current_user.teacher_profile
        if teacher is None:
            abort(404)
        query = LibraryLoan.query.filter_by(college_id=_college_id(), teacher_id=teacher.id)
        outstanding_fines = _fine_query_for_borrower(teacher_id=teacher.id, statuses=['unpaid', 'partial']).all()
        fine_history = _fine_query_for_borrower(teacher_id=teacher.id, statuses=['paid', 'waived']).all()
    else:
        abort(403)

    active_loans = query.filter(LibraryLoan.status.in_(['active', 'overdue'])).order_by(LibraryLoan.due_at.asc()).all()
    history_loans = query.filter(LibraryLoan.status.in_(['returned', 'lost'])).order_by(LibraryLoan.issued_at.desc()).all()
    reservation_query = _user_reservation_query()
    active_reservations = []
    reservation_history = []
    if reservation_query is not None:
        active_reservations = (
            reservation_query
            .filter(LibraryReservation.status.in_(['pending', 'ready_for_pickup']))
            .order_by(
                db.case((LibraryReservation.status == 'ready_for_pickup', 0), else_=1),
                LibraryReservation.created_at.asc(),
            )
            .all()
        )
        reservation_history = (
            reservation_query
            .filter(LibraryReservation.status.in_(['fulfilled', 'cancelled', 'expired']))
            .order_by(LibraryReservation.created_at.desc())
            .all()
        )
    if q:
        active_loans = [
            loan for loan in active_loans
            if q in f'{loan.book.title} {loan.book.author} {loan.copy.accession_number}'.lower()
        ]
        history_loans = [
            loan for loan in history_loans
            if q in f'{loan.book.title} {loan.book.author} {loan.copy.accession_number}'.lower()
        ]
        active_reservations = [
            reservation for reservation in active_reservations
            if q in f'{reservation.book.title} {reservation.book.author}'.lower()
        ]
        reservation_history = [
            reservation for reservation in reservation_history
            if q in f'{reservation.book.title} {reservation.book.author}'.lower()
        ]
        outstanding_fines = [
            fine for fine in outstanding_fines
            if q in f'{fine.book.title} {fine.borrower_label} {fine.reason}'.lower()
        ]
        fine_history = [
            fine for fine in fine_history
            if q in f'{fine.book.title} {fine.borrower_label} {fine.reason}'.lower()
        ]

    return render_template(
        'library/my_loans.html',
        active_loans=active_loans,
        history_loans=history_loans,
        active_reservations=active_reservations,
        reservation_history=reservation_history,
        outstanding_fines=outstanding_fines,
        fine_history=fine_history,
        outstanding_fine_total=_fine_total(outstanding_fines),
        q=q,
        borrower_policy=_current_borrower_policy(),
        library_rule=_library_rule_for_college(),
    )


@library_bp.route('/library/parent')
@login_required
@parent_required
def parent_overview():
    _refresh_library_runtime_state(_college_id())
    q = (request.args.get('q') or '').strip().lower()
    links = (
        ParentStudent.query
        .filter_by(college_id=_college_id(), parent_id=current_user.id)
        .all()
    )

    child_rows = []
    for link in links:
        loans = (
            LibraryLoan.query
            .filter_by(college_id=_college_id(), student_id=link.student_id)
            .order_by(LibraryLoan.issued_at.desc())
            .all()
        )
        outstanding_fines = _fine_query_for_borrower(student_id=link.student_id, statuses=['unpaid', 'partial']).all()
        fine_history = _fine_query_for_borrower(student_id=link.student_id, statuses=['paid', 'waived']).limit(5).all()
        active_loans = [loan for loan in loans if loan.status in {'active', 'overdue'}]
        history_loans = [loan for loan in loans if loan.status in {'returned', 'lost'}][:5]

        if q:
            student_blob = f'{link.student.user.name} {link.student.roll_number}'.lower()
            active_loans = [
                loan for loan in active_loans
                if q in f'{loan.book.title} {loan.copy.accession_number}'.lower()
            ]
            history_loans = [
                loan for loan in history_loans
                if q in f'{loan.book.title} {loan.copy.accession_number}'.lower()
            ]
            outstanding_fines = [
                fine for fine in outstanding_fines
                if q in f'{fine.book.title} {fine.reason}'.lower()
            ]
            fine_history = [
                fine for fine in fine_history
                if q in f'{fine.book.title} {fine.reason}'.lower()
            ]
            if q not in student_blob and not active_loans and not history_loans and not outstanding_fines and not fine_history:
                continue

        child_rows.append({
            'student': link.student,
            'active_loans': active_loans,
            'history_loans': history_loans,
            'outstanding_fines': outstanding_fines,
            'fine_history': fine_history,
            'outstanding_fine_total': _fine_total(outstanding_fines),
        })

    return render_template(
        'library/parent_overview.html',
        child_rows=child_rows,
        q=q,
        student_policy=_policy_for_borrower(_library_rule_for_college(), 'student'),
        library_rule=_library_rule_for_college(),
    )


@library_bp.route('/library/borrower-cards')
@login_required
def borrower_cards():
    if not _can_operate_library():
        abort(403)
    q = (request.args.get('q') or '').strip()
    department_id = request.args.get('department_id', type=int)
    borrower_type = (request.args.get('borrower_type') or '').strip().lower()

    student_query = (
        Student.query
        .filter(Student.college_id == _college_id())
        .join(Student.user)
        .join(Student.department)
    )
    teacher_query = (
        Teacher.query
        .filter(Teacher.college_id == _college_id())
        .join(Teacher.user)
        .join(Teacher.department)
    )
    if department_id:
        student_query = student_query.filter(Student.department_id == department_id)
        teacher_query = teacher_query.filter(Teacher.department_id == department_id)
    if q:
        like = f'%{q}%'
        student_query = student_query.filter(
            db.or_(Student.roll_number.ilike(like), Student.user.has(User.name.ilike(like)))
        )
        teacher_query = teacher_query.filter(
            db.or_(Teacher.employee_id.ilike(like), Teacher.user.has(User.name.ilike(like)))
        )

    students = student_query.order_by(Student.roll_number.asc()).all() if borrower_type != 'teacher' else []
    teachers = teacher_query.order_by(Teacher.employee_id.asc()).all() if borrower_type != 'student' else []
    departments = Department.query.filter_by(college_id=_college_id()).order_by(Department.name.asc()).all()
    return render_template(
        'library/borrower_cards.html',
        students=students,
        teachers=teachers,
        departments=departments,
        filters={
            'q': q,
            'department_id': department_id,
            'borrower_type': borrower_type,
        },
    )


@library_bp.route('/library/borrower-cards/student/<int:student_id>')
@login_required
def print_student_borrower_card(student_id: int):
    if not _can_operate_library():
        abort(403)
    student = Student.query.filter_by(id=student_id, college_id=_college_id()).first_or_404()
    scan_value = _student_scan_value(student)
    qr_img = make_library_borrower_qr(
        name=student.user.name,
        scan_value=scan_value,
        borrower_type='student',
        department=student.department.name if student.department else None,
        semester=f'Semester {student.semester}' if student.semester else None,
    )
    return render_template(
        'library/borrower_card_print.html',
        borrower=student,
        borrower_type='student',
        scan_value=scan_value,
        qr_img=qr_img,
        title='Library Borrower Card',
    )


@library_bp.route('/library/borrower-cards/teacher/<int:teacher_id>')
@login_required
def print_teacher_borrower_card(teacher_id: int):
    if not _can_operate_library():
        abort(403)
    teacher = Teacher.query.filter_by(id=teacher_id, college_id=_college_id()).first_or_404()
    scan_value = _teacher_scan_value(teacher)
    qr_img = make_library_borrower_qr(
        name=teacher.user.name,
        scan_value=scan_value,
        borrower_type='teacher',
        department=teacher.department.name if teacher.department else None,
    )
    return render_template(
        'library/borrower_card_print.html',
        borrower=teacher,
        borrower_type='teacher',
        scan_value=scan_value,
        qr_img=qr_img,
        title='Library Borrower Card',
    )


@library_bp.route('/library/copies/<int:copy_id>/label')
@login_required
def print_copy_label(copy_id: int):
    if not _can_operate_library():
        abort(403)
    copy = _scoped_copy_or_404(copy_id)
    qr_img = make_library_copy_qr(copy)
    return render_template(
        'library/copy_labels_print.html',
        copies=[copy],
        qr_map={copy.id: qr_img},
        title='Library Copy Label',
        single_copy=copy,
    )


@library_bp.route('/library/books/<int:book_id>/labels')
@login_required
def print_book_copy_labels(book_id: int):
    if not _can_operate_library():
        abort(403)
    book = _scoped_book_or_404(book_id)
    copies = list(book.copies)
    qr_map = {copy.id: make_library_copy_qr(copy) for copy in copies}
    return render_template(
        'library/copy_labels_print.html',
        copies=copies,
        qr_map=qr_map,
        title=f'{book.title} Copy Labels',
        single_copy=None,
    )


@library_bp.route('/library/books/<int:book_id>/reader')
@login_required
def ebook_reader(book_id: int):
    _ensure_library_user()
    book = _scoped_book_or_404(book_id)
    if not _student_can_access_book(book):
        abort(404)
    if not _can_open_ebook_reader(book):
        abort(403)

    abs_path = _ebook_file_or_404(book)
    ebook_extension = _ebook_extension(book)
    total_pages = _ebook_total_pages(abs_path, extension=ebook_extension)
    preview_limit = _ebook_preview_page_limit(book)
    progress = _reader_progress_for_current_user(book.id)
    history_query = LibraryAccessLog.query.filter_by(college_id=_college_id(), book_id=book.id)
    if current_user.role == 'student' and current_user.student_profile:
        history_query = history_query.filter_by(student_id=current_user.student_profile.id)
    elif current_user.role == 'teacher' and current_user.teacher_profile:
        history_query = history_query.filter_by(teacher_id=current_user.teacher_profile.id)
    else:
        history_query = history_query.filter(
            LibraryAccessLog.student_id.is_(None),
            LibraryAccessLog.teacher_id.is_(None),
        )
    reading_history = history_query.order_by(LibraryAccessLog.accessed_at.desc()).limit(10).all()
    max_page = None
    if total_pages:
        max_page = min(total_pages, preview_limit) if preview_limit else total_pages
    current_page = progress.last_page if progress and progress.last_page else 1
    if max_page:
        current_page = max(1, min(current_page, max_page))
    current_progress = float(progress.progress_percent) if progress and progress.progress_percent is not None else 0

    return render_template(
        'library/reader.html',
        book=book,
        ebook_extension=ebook_extension,
        total_pages=total_pages,
        max_page=max_page,
        preview_limit=preview_limit,
        can_download_ebook=_can_download_ebook(book),
        progress=progress,
        current_page=current_page,
        current_progress=current_progress,
        reading_history=reading_history,
    )


@library_bp.route('/library/books/<int:book_id>/progress', methods=['POST'])
@login_required
def save_reading_progress(book_id: int):
    _ensure_library_user()
    book = _scoped_book_or_404(book_id)
    if not _student_can_access_book(book):
        abort(404)
    if not _can_open_ebook_reader(book):
        abort(403)

    abs_path = _ebook_file_or_404(book)
    ebook_extension = _ebook_extension(book)
    total_pages = _ebook_total_pages(abs_path, extension=ebook_extension)
    preview_limit = _ebook_preview_page_limit(book)
    max_page = min(total_pages, preview_limit) if total_pages and preview_limit else total_pages

    raw_page = request.form.get('last_page', type=int)
    last_page = raw_page if raw_page and raw_page > 0 else None
    if last_page and max_page:
        last_page = min(last_page, max_page)

    raw_progress = request.form.get('progress_percent')
    progress_percent = None
    if raw_progress not in (None, ''):
        progress_percent = _normalized_money(raw_progress)
        if progress_percent < 0:
            progress_percent = Decimal('0.00')
        if progress_percent > 100:
            progress_percent = Decimal('100.00')

    last_position = (request.form.get('last_position') or '').strip() or None
    if last_position and len(last_position) > 255:
        last_position = last_position[:255]

    _upsert_reader_progress(
        book,
        last_page=last_page,
        progress_percent=progress_percent,
        last_position=last_position,
        total_pages=total_pages,
    )
    db.session.commit()

    if request.accept_mimetypes.best == 'application/json':
        return jsonify({'ok': True})

    flash('Reading progress saved.', 'success')
    return redirect(url_for('library.ebook_reader', book_id=book.id))


@library_bp.route('/library/books/<int:book_id>/preview')
@login_required
def preview_ebook(book_id: int):
    _ensure_library_user()
    if current_user.role not in {'admin', 'sub_admin', 'librarian', 'teacher', 'student'}:
        abort(403)

    book = _scoped_book_or_404(book_id)
    if not _student_can_access_book(book):
        abort(404)
    if not _can_open_ebook_reader(book):
        abort(403)
    abs_path = _ebook_file_or_404(book)
    _record_ebook_access(book, 'view')
    if book.ebook_access_level == 'preview_only' and _ebook_extension(book) == 'pdf':
        preview_buffer = _limited_preview_pdf(abs_path, max_pages=_ebook_preview_page_limit(book))
        return send_file(
            preview_buffer,
            as_attachment=False,
            download_name=book.ebook_filename or os.path.basename(abs_path),
            mimetype='application/pdf',
        )

    return send_file(
        abs_path,
        as_attachment=False,
        download_name=book.ebook_filename or os.path.basename(abs_path),
        mimetype=_ebook_mimetype(abs_path, book.ebook_filename),
        conditional=True,
    )


@library_bp.route('/library/books/<int:book_id>/download')
@login_required
def download_ebook(book_id: int):
    _ensure_library_user()
    if current_user.role not in {'admin', 'sub_admin', 'librarian', 'teacher', 'student'}:
        abort(403)

    book = _scoped_book_or_404(book_id)
    if not _student_can_access_book(book):
        abort(404)
    if not _can_download_ebook(book):
        abort(403)
    abs_path = _ebook_file_or_404(book)
    _record_ebook_access(book, 'download')

    return send_file(
        abs_path,
        as_attachment=True,
        download_name=book.ebook_filename or os.path.basename(abs_path),
    )
