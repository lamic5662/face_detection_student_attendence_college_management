import io
import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from pypdf import PdfWriter

from extensions import db, mail
from models.academic_calendar import AcademicCalendarEvent
from models.assignment import AssignmentSubmission
from models.college import College
from models.college_feature import CollegeFeatureAccess
from models.content import TeacherContent
from models.department import Department
from models.fee import FeePayment, FeeStructure
from models.id_card import IDCardTemplate, StudentIDCard
from models.leave import LeaveRequest
from models.library import (
    LibraryAuditEntry,
    LibraryAuditSession,
    LibraryBook,
    LibraryBookCopy,
    LibraryCopyEvent,
    LibraryFine,
    LibraryLoan,
    LibraryLocation,
    LibraryReadingProgress,
    LibraryReservation,
    LibraryRule,
)
from models.notice import Notice
from models.notice_read import NoticeRead
from models.parent import TeacherStatus
from models.plan_pricing import PlanPricing
from models.platform_audit import PlatformAuditLog
from models.platform_audit_read import PlatformAuditRead
from models.setting import CollegeSetting
from models.student import Student
from models.subject import Subject
from models.teacher import Teacher
from models.timetable import TimetableSlot
from models.university import University
from models.user import User
from models.user_notification import UserNotification
from services.ai_context import build_context
from utils.account_setup import build_public_url, generate_password_setup_token
from utils.deploy_assets import write_deployment_bundle
from utils.library_storage import build_library_relpath
from utils.time import utc_now_naive


def make_valid_png_bytes(size=(64, 64), color=(13, 110, 253, 255)):
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


def login(client, email, password="Password@123", college_code=None):
    data = {"email": email, "password": password}
    if college_code:
        data["college_code"] = college_code
    return client.post(
        "/login",
        data=data,
        follow_redirects=False,
    )


def test_student_can_save_dashboard_preferences_and_return_to_dashboard(app, client):
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/preferences/dashboard",
        data={
            "dashboard_widgets": ["location_sharing", "fee_status"],
            "next": "/student/dashboard",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Dashboard widgets updated." in response.data
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user.get_dashboard_widget_keys() == ["location_sharing", "fee_status"]


def test_teacher_can_save_dashboard_preferences_and_return_to_dashboard(app, client):
    login(client, "teacher1@example.com")

    response = client.post(
        "/preferences/dashboard",
        data={
            "dashboard_widgets": ["stats_overview", "notice_board"],
            "next": "/teacher/dashboard",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Dashboard widgets updated." in response.data
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["teacher_user_id"])
        assert user.get_dashboard_widget_keys() == ["stats_overview", "notice_board"]


def test_parent_can_save_dashboard_preferences_and_return_to_dashboard(app, client):
    login(
        client,
        "parent1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/preferences/dashboard",
        data={
            "dashboard_widgets": ["college_notices"],
            "next": "/parent/dashboard",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Dashboard widgets updated." in response.data
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["parent_user_id"])
        assert user.get_dashboard_widget_keys() == ["college_notices"]


def test_student_notice_feed_is_not_rate_limited_by_dashboard_polling(app, client):
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    for _ in range(55):
        response = client.get("/notices/feed", headers={"Accept": "application/json"})
        assert response.status_code == 200


def test_super_admin_notification_feed_is_not_rate_limited_by_dashboard_polling(
    app, client
):
    login(client, "superadmin@example.com")

    for _ in range(55):
        response = client.get(
            "/super-admin/notifications/feed", headers={"Accept": "application/json"}
        )
        assert response.status_code == 200


def test_super_admin_dashboard_does_not_render_college_branding(app, client):
    with app.app_context():
        setting = CollegeSetting.get(
            db.session.get(College, app.config["TEST_DATA"]["college_id"])
        )
        setting.college_name = "Alpha College"
        setting.logo_path = "uploads/college_logos/alpha/logo.png"
        db.session.commit()

    login(client, "superadmin@example.com")
    response = client.get("/super-admin/dashboard")

    assert response.status_code == 200
    assert b"SmartAttend Platform" in response.data
    assert b'title="Alpha College"' not in response.data
    assert b"uploads/college_logos/alpha/logo.png" not in response.data


def test_ai_widget_is_hidden_when_backend_is_not_configured(app, client):
    login(client, "teacher1@example.com")

    with patch(
        "services.ai_service.unavailable_reason",
        return_value="GROQ_API_KEY is not configured.",
    ):
        response = client.get("/teacher/dashboard")

    assert response.status_code == 200
    assert b'id="sa-ai-btn"' not in response.data


def test_notice_form_shows_ai_setup_hint_when_backend_is_not_configured(app, client):
    login(client, "admin@example.com")

    with patch(
        "services.ai_service.unavailable_reason",
        return_value="GROQ_API_KEY is not configured.",
    ):
        response = client.get("/notices/create")

    assert response.status_code == 200
    assert b"AI Generate unavailable" in response.data
    assert b"GROQ_API_KEY is not configured." in response.data
    assert b'id="aiGenBtn"' not in response.data


def test_ai_controls_render_when_ai_service_is_available(app, client):
    login(client, "admin@example.com")

    with patch("services.ai_service.unavailable_reason", return_value=None):
        response = client.get("/notices/create")

    assert response.status_code == 200
    assert b'id="sa-ai-btn"' in response.data
    assert b'id="aiGenBtn"' in response.data


def test_ai_context_uses_user_name_without_context_fetch_error(app):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["teacher_user_id"])
        context = build_context(
            user, app.config["TEST_DATA"]["college_id"], "attendance summary"
        )

    assert "Context fetch error" not in context
    assert "Teacher One" in context


def test_login_page_uses_versioned_stylesheet_url(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert b"css/style.css?v=" in response.data


def test_login_page_disables_browser_cache(client):
    response = client.get("/login")

    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


def test_authenticated_dashboard_disables_browser_cache(app, client):
    login(client, "admin@example.com")
    response = client.get("/admin/dashboard")

    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


def test_logout_redirect_disables_browser_cache(app, client):
    login(client, "admin@example.com")
    response = client.get("/logout", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


def test_teacher_cannot_download_another_teachers_session_report(app, client):
    login(client, "teacher1@example.com")

    foreign_session_id = app.config["TEST_DATA"]["foreign_session_id"]
    response = client.get(f"/teacher/reports/session/{foreign_session_id}/download")

    assert response.status_code == 403


def test_student_with_temporary_password_is_prompted_on_first_login(app, client):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        user.set_temporary_password("TempPass@123")
        db.session.commit()

    response = login(
        client,
        "student1@example.com",
        password="TempPass@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/password-setup-prompt")


def test_student_with_temporary_password_cannot_open_dashboard_before_changing_it(
    app, client
):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        user.set_temporary_password("TempPass@123")
        db.session.commit()

    login(
        client,
        "student1@example.com",
        password="TempPass@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/student/dashboard", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/password-setup-prompt")


def test_student_can_request_password_setup_email(app, client):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        user.set_temporary_password("TempPass@123")
        db.session.commit()

    login(
        client,
        "student1@example.com",
        password="TempPass@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    sent_messages = []

    def _capture_message(message):
        sent_messages.append(message)

    with patch.object(mail, "send", side_effect=_capture_message):
        response = client.post(
            "/password-setup-prompt/send-email", follow_redirects=True
        )

    assert response.status_code == 200
    assert sent_messages
    assert sent_messages[0].recipients == ["student1@example.com"]
    assert b"you still need to set your new password before continuing" in response.data
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user.password_setup_email_sent_at is not None


def test_college_user_can_request_forgot_password_email(app, client):
    sent_messages = []

    def _capture_message(message):
        sent_messages.append(message)

    with patch.object(mail, "send", side_effect=_capture_message):
        response = client.post(
            "/forgot-password",
            data={
                "college_code": app.config["TEST_DATA"]["college_code"],
                "email": "student1@example.com",
            },
            follow_redirects=True,
        )

    assert response.status_code == 200


def test_library_feature_can_be_disabled_for_student(app, client):
    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        access = CollegeFeatureAccess.query.filter_by(
            college_id=college_id, feature_key="library"
        ).first()
        if access is None:
            access = CollegeFeatureAccess(
                college_id=college_id, feature_key="library", enabled=False
            )
            db.session.add(access)
        else:
            access.enabled = False
        db.session.commit()

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/library/catalog")

    assert response.status_code == 403


def test_librarian_can_create_issue_and_student_can_view_library_loan(app, client):
    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    create_response = client.post(
        "/library/books/create",
        data={
            "title": "Database Systems",
            "author": "C. J. Date",
            "book_type": "physical",
            "department_id": "",
            "subject_id": "",
            "category_mode": "new",
            "new_category_name": "Reference",
            "semester": "1",
            "initial_copy_count": "2",
            "rack_location": "R1-S2",
            "is_active": "1",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    with app.app_context():
        book = LibraryBook.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"], title="Database Systems"
        ).first()
        assert book is not None
        assert (
            LibraryBookCopy.query.filter_by(
                college_id=book.college_id, book_id=book.id
            ).count()
            == 2
        )
        copy = (
            LibraryBookCopy.query.filter_by(college_id=book.college_id, book_id=book.id)
            .order_by(LibraryBookCopy.id.asc())
            .first()
        )

    issue_response = client.post(
        "/library/issue",
        data={
            "copy_id": str(copy.id),
            "borrower_ref": f"student:{app.config['TEST_DATA']['student_profile_id']}",
            "due_days": "10",
        },
        follow_redirects=False,
    )

    assert issue_response.status_code == 302

    with app.app_context():
        loan = LibraryLoan.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"], copy_id=copy.id
        ).first()
        copy = db.session.get(LibraryBookCopy, copy.id)
        assert loan is not None
        assert loan.student_id == app.config["TEST_DATA"]["student_profile_id"]
        assert copy.status == "issued"

    client.get("/logout")
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    student_response = client.get("/library/my-loans")

    assert student_response.status_code == 200
    assert b"Database Systems" in student_response.data


def test_admin_can_save_library_rules_and_librarian_issue_enforces_them(app, client):
    login(client, "admin@example.com")
    save_response = client.post(
        "/library/rules",
        data={
            "student_max_active_loans": "1",
            "teacher_max_active_loans": "4",
            "student_due_days": "5",
            "teacher_due_days": "21",
            "student_max_renewals": "1",
            "teacher_max_renewals": "2",
            "student_renew_days": "3",
            "teacher_renew_days": "10",
            "student_fine_per_day": "4.50",
            "teacher_fine_per_day": "1.25",
            "grace_days": "1",
            "regulations": "Students must return books on time.",
        },
        follow_redirects=False,
    )

    assert save_response.status_code == 302

    with app.app_context():
        rule = LibraryRule.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"]
        ).first()
        assert rule is not None
        assert rule.student_due_days == 5
        assert float(rule.student_fine_per_day) == 4.5

        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Rule Driven Book",
            author="Policy Author",
            book_type="physical",
            semester=1,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()
        first_copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-RULE-001",
            barcode="LB-RULE-001",
            condition="good",
            status="available",
        )
        second_copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-RULE-002",
            barcode="LB-RULE-002",
            condition="good",
            status="available",
        )
        db.session.add_all([first_copy, second_copy])
        db.session.commit()
        first_copy_id = first_copy.id
        second_copy_id = second_copy.id

    client.get("/logout")
    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    first_issue = client.post(
        "/library/issue",
        data={
            "copy_id": str(first_copy_id),
            "borrower_ref": f"student:{app.config['TEST_DATA']['student_profile_id']}",
            "due_days": "20",
        },
        follow_redirects=False,
    )
    assert first_issue.status_code == 302

    with app.app_context():
        first_loan = LibraryLoan.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            copy_id=first_copy_id,
        ).first()
        assert first_loan is not None
        assert (first_loan.due_at.date() - date.today()).days == 5

    second_issue = client.post(
        "/library/issue",
        data={
            "copy_id": str(second_copy_id),
            "borrower_ref": f"student:{app.config['TEST_DATA']['student_profile_id']}",
            "due_days": "5",
        },
        follow_redirects=False,
    )
    assert second_issue.status_code == 302

    with app.app_context():
        active_student_loans = LibraryLoan.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            status="active",
        ).all()
        assert len(active_student_loans) == 1


def test_library_return_uses_admin_overdue_fine_rule(app, client):
    with app.app_context():
        rule = LibraryRule(
            college_id=app.config["TEST_DATA"]["college_id"],
            student_max_active_loans=3,
            teacher_max_active_loans=5,
            student_due_days=14,
            teacher_due_days=30,
            student_max_renewals=1,
            teacher_max_renewals=2,
            student_renew_days=7,
            teacher_renew_days=14,
            student_fine_per_day=4.00,
            teacher_fine_per_day=1.00,
            grace_days=1,
            regulations="Overdue fines are applied automatically.",
        )
        db.session.add(rule)

        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Overdue Policy Book",
            author="Fine Author",
            book_type="physical",
            semester=1,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-FINE-001",
            barcode="LB-FINE-001",
            condition="good",
            status="issued",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() - timedelta(days=3),
            status="overdue",
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/loans/{loan_id}/return",
        data={},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        loan = db.session.get(LibraryLoan, loan_id)
        assert float(loan.fine_amount) == 8.0
        assert loan.status == "returned"
        fine = LibraryFine.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"], loan_id=loan_id
        ).first()
        assert fine is not None
        assert float(fine.amount_assessed) == 8.0
        assert fine.status == "unpaid"
        assert fine.student_id == app.config["TEST_DATA"]["student_profile_id"]


def test_librarian_can_partially_and_fully_settle_library_fine(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Fine Settlement Book",
            author="Ledger Author",
            book_type="physical",
            semester=1,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-FINE-002",
            barcode="LB-FINE-002",
            condition="good",
            status="available",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() - timedelta(days=4),
            returned_at=utc_now_naive(),
            status="returned",
            fine_amount=12.00,
        )
        db.session.add(loan)
        db.session.flush()

        fine = LibraryFine(
            college_id=book.college_id,
            loan_id=loan.id,
            book_id=book.id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            reason="overdue",
            amount_assessed=12.00,
            created_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
        )
        db.session.add(fine)
        db.session.commit()
        fine_id = fine.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    partial = client.post(
        f"/library/fines/{fine_id}/settle",
        data={
            "payment_amount": "5.00",
            "waive_amount": "0.00",
            "notes": "Collected first payment",
        },
        follow_redirects=False,
    )
    assert partial.status_code == 302

    with app.app_context():
        fine = db.session.get(LibraryFine, fine_id)
        assert fine is not None
        assert float(fine.amount_paid) == 5.0
        assert fine.status == "partial"
        assert float(fine.outstanding_amount) == 7.0

    settled = client.post(
        f"/library/fines/{fine_id}/settle",
        data={
            "payment_amount": "0.00",
            "waive_amount": "7.00",
            "notes": "Remaining balance waived",
        },
        follow_redirects=False,
    )
    assert settled.status_code == 302

    with app.app_context():
        fine = db.session.get(LibraryFine, fine_id)
        assert fine is not None
        assert float(fine.amount_waived) == 7.0
        assert float(fine.outstanding_amount) == 0.0
        assert fine.status == "paid"
        assert fine.settled_at is not None


def test_librarian_can_issue_book_by_scan_using_student_card_and_copy_barcode(
    app, client
):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        card = StudentIDCard(
            college_id=student.college_id,
            student_id=student.id,
            card_number="COL-SCAN-001",
            status="approved",
        )
        db.session.add(card)

        book = LibraryBook(
            college_id=student.college_id,
            title="Scannable Library Book",
            author="Scan Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-SCAN-001",
            barcode="BC-SCAN-001",
            condition="good",
            status="available",
        )
        db.session.add(copy)
        db.session.commit()
        copy_id = copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/library/issue/scan",
        data={
            "borrower_scan": "COL-SCAN-001",
            "copy_scan": "BC-SCAN-001",
            "due_days": "4",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert copy is not None
        assert copy.status == "issued"
        loan = LibraryLoan.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            copy_id=copy_id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            status="active",
        ).first()
        assert loan is not None


def test_scan_issue_is_blocked_when_borrower_has_outstanding_library_fine(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        card = StudentIDCard(
            college_id=student.college_id,
            student_id=student.id,
            card_number="COL-SCAN-002",
            status="approved",
        )
        db.session.add(card)

        old_book = LibraryBook(
            college_id=student.college_id,
            title="Old Fine Book",
            author="Ledger Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(old_book)
        db.session.flush()

        old_copy = LibraryBookCopy(
            college_id=old_book.college_id,
            book_id=old_book.id,
            accession_number="LB-SCAN-OLD",
            barcode="BC-SCAN-OLD",
            condition="good",
            status="available",
        )
        db.session.add(old_copy)
        db.session.flush()

        old_loan = LibraryLoan(
            college_id=student.college_id,
            book_id=old_book.id,
            copy_id=old_copy.id,
            student_id=student.id,
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() - timedelta(days=5),
            returned_at=utc_now_naive(),
            status="returned",
            fine_amount=10.00,
        )
        db.session.add(old_loan)
        db.session.flush()

        fine = LibraryFine(
            college_id=student.college_id,
            loan_id=old_loan.id,
            book_id=old_book.id,
            student_id=student.id,
            reason="overdue",
            amount_assessed=10.00,
        )
        db.session.add(fine)

        new_book = LibraryBook(
            college_id=student.college_id,
            title="Blocked Scan Book",
            author="Scan Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(new_book)
        db.session.flush()

        new_copy = LibraryBookCopy(
            college_id=new_book.college_id,
            book_id=new_book.id,
            accession_number="LB-SCAN-002",
            barcode="BC-SCAN-002",
            condition="good",
            status="available",
        )
        db.session.add(new_copy)
        db.session.commit()
        new_copy_id = new_copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/library/issue/scan",
        data={
            "borrower_scan": "COL-SCAN-002",
            "copy_scan": "BC-SCAN-002",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        copy = db.session.get(LibraryBookCopy, new_copy_id)
        assert copy is not None
        assert copy.status == "available"
        loan = LibraryLoan.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            copy_id=new_copy_id,
        ).first()
        assert loan is None


def test_librarian_can_return_book_by_scan_using_copy_barcode(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=student.college_id,
            title="Scannable Return Book",
            author="Scan Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-SCAN-RETURN",
            barcode="BC-SCAN-RETURN",
            condition="good",
            status="issued",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=student.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=student.id,
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() - timedelta(days=2),
            status="overdue",
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id
        copy_id = copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/library/return/scan",
        data={"copy_scan": "BC-SCAN-RETURN"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        loan = db.session.get(LibraryLoan, loan_id)
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert loan is not None
        assert copy is not None
        assert loan.status == "returned"
        assert copy.status == "available"


def test_scan_issue_accepts_full_qr_payload_text(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        card = StudentIDCard(
            college_id=student.college_id,
            student_id=student.id,
            card_number="COL-QR-001",
            status="approved",
        )
        db.session.add(card)

        book = LibraryBook(
            college_id=student.college_id,
            title="QR Payload Book",
            author="QR Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-QR-001",
            barcode="BC-QR-001",
            condition="good",
            status="available",
        )
        db.session.add(copy)
        db.session.commit()
        copy_id = copy.id

    borrower_payload = "\n".join(
        [
            "Type: Library Borrower",
            "Name: Student One",
            "Role: Student",
            "Scan: COL-QR-001",
            "Department: Test Department",
            "Semester: Semester 1",
        ]
    )
    copy_payload = "\n".join(
        [
            "Type: Library Copy",
            "Title: QR Payload Book",
            "Accession: LB-QR-001",
            "Barcode: BC-QR-001",
            "Location: Main Rack",
        ]
    )

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/library/issue/scan",
        data={
            "borrower_scan": borrower_payload,
            "copy_scan": copy_payload,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert copy is not None
        assert copy.status == "issued"


def test_librarian_can_open_borrower_card_print_views(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        teacher = db.session.get(Teacher, app.config["TEST_DATA"]["teacher_profile_id"])
        assert student is not None
        assert teacher is not None

        card = StudentIDCard(
            college_id=student.college_id,
            student_id=student.id,
            card_number="COL-CARD-PRINT",
            status="approved",
        )
        db.session.add(card)
        db.session.commit()
        student_id = student.id
        teacher_id = teacher.id
        teacher_employee_id = teacher.employee_id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    listing = client.get("/library/borrower-cards")
    assert listing.status_code == 200

    student_card = client.get(f"/library/borrower-cards/student/{student_id}")
    assert student_card.status_code == 200
    assert b"COL-CARD-PRINT" in student_card.data

    teacher_card = client.get(f"/library/borrower-cards/teacher/{teacher_id}")
    assert teacher_card.status_code == 200
    assert teacher_employee_id.encode() in teacher_card.data


def test_librarian_can_open_circulation_desk_page(app, client):
    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/library/circulation")
    assert response.status_code == 200
    assert b"Circulation Desk" in response.data
    assert b"Scan Issue Book" in response.data


def test_librarian_can_print_copy_labels(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=student.college_id,
            title="Printable Labels Book",
            author="Print Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-PRINT-001",
            barcode="BC-PRINT-001",
            condition="good",
            status="available",
        )
        db.session.add(copy)
        db.session.commit()
        copy_id = copy.id
        book_id = book.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    single = client.get(f"/library/copies/{copy_id}/label")
    assert single.status_code == 200
    assert b"BC-PRINT-001" in single.data

    all_labels = client.get(f"/library/books/{book_id}/labels")
    assert all_labels.status_code == 200
    assert b"LB-PRINT-001" in all_labels.data


def test_student_can_preview_ebook_inside_library_system(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Digital Signals",
            author="Signal Author",
            book_type="digital",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        ebook_path = os.path.join(
            app.config["LIBRARY_UPLOAD_FOLDER"], "digital-signals-test.pdf"
        )
        with open(ebook_path, "wb") as handle:
            handle.write(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n")

        book.ebook_file_path = build_library_relpath(os.path.basename(ebook_path))
        book.ebook_filename = "digital-signals.pdf"
        db.session.commit()
        book_id = book.id

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get(f"/library/books/{book_id}/preview")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"

    with app.app_context():
        book = db.session.get(LibraryBook, book_id)
        assert book is not None
        assert any(log.action == "view" for log in book.access_logs)


def test_preview_only_ebook_reader_saves_progress_and_blocks_download(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Preview Only Signals",
            author="Signal Author",
            book_type="digital",
            department_id=student.department_id,
            semester=student.semester,
            ebook_access_level="preview_only",
            ebook_download_allowed=False,
            ebook_preview_page_limit=2,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        ebook_path = os.path.join(
            app.config["LIBRARY_UPLOAD_FOLDER"], "preview-only-signals.pdf"
        )
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        with open(ebook_path, "wb") as handle:
            writer.write(handle)

        book.ebook_file_path = build_library_relpath(os.path.basename(ebook_path))
        book.ebook_filename = "preview-only-signals.pdf"
        db.session.commit()
        book_id = book.id

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    reader_response = client.get(f"/library/books/{book_id}/reader")
    assert reader_response.status_code == 200
    assert b"Preview Only" in reader_response.data
    assert b"Save Progress" in reader_response.data

    save_progress_response = client.post(
        f"/library/books/{book_id}/progress",
        data={
            "last_page": "1",
            "progress_percent": "45",
            "last_position": "Reached concept summary",
        },
        follow_redirects=False,
    )
    assert save_progress_response.status_code == 302

    download_response = client.get(f"/library/books/{book_id}/download")
    assert download_response.status_code == 403

    with app.app_context():
        progress = LibraryReadingProgress.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            book_id=book_id,
            user_id=app.config["TEST_DATA"]["student_user_id"],
        ).first()
        assert progress is not None
        assert progress.last_page == 1
        assert float(progress.progress_percent) == 45.0
        assert progress.last_position == "Reached concept summary"


def test_student_can_reserve_unavailable_physical_book_and_cancel(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        teacher = db.session.get(Teacher, app.config["TEST_DATA"]["teacher_profile_id"])
        assert student is not None
        assert teacher is not None

        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Reserved Operating Systems",
            author="Queue Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-RES-001",
            barcode="LB-RES-001",
            condition="good",
            status="issued",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            teacher_id=teacher.id,
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() + timedelta(days=5),
            status="active",
        )
        db.session.add(loan)
        db.session.commit()
        book_id = book.id

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    reserve_response = client.post(
        f"/library/books/{book_id}/reserve", data={}, follow_redirects=False
    )
    assert reserve_response.status_code == 302

    with app.app_context():
        reservation = LibraryReservation.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            book_id=book_id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            status="pending",
        ).first()
        assert reservation is not None
        reservation_id = reservation.id

    my_loans_response = client.get("/library/my-loans")
    assert my_loans_response.status_code == 200
    assert b"Reserved Operating Systems" in my_loans_response.data
    assert b"Active Reservations" in my_loans_response.data

    cancel_response = client.post(
        f"/library/reservations/{reservation_id}/cancel",
        data={},
        follow_redirects=False,
    )
    assert cancel_response.status_code == 302

    with app.app_context():
        reservation = db.session.get(LibraryReservation, reservation_id)
        assert reservation is not None
        assert reservation.status == "cancelled"


def test_librarian_issue_respects_pending_reservation_queue(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        teacher = db.session.get(Teacher, app.config["TEST_DATA"]["teacher_profile_id"])
        assert student is not None
        assert teacher is not None

        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Queued Book",
            author="Queue Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-QUEUE-001",
            barcode="LB-QUEUE-001",
            condition="good",
            status="available",
        )
        db.session.add(copy)
        db.session.flush()

        reservation = LibraryReservation(
            college_id=book.college_id,
            book_id=book.id,
            student_id=student.id,
            status="pending",
        )
        db.session.add(reservation)
        db.session.commit()
        copy_id = copy.id
        reservation_id = reservation.id
        teacher_id = teacher.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    blocked_issue = client.post(
        "/library/issue",
        data={
            "copy_id": str(copy_id),
            "borrower_ref": f"teacher:{teacher_id}",
            "due_days": "10",
        },
        follow_redirects=False,
    )
    assert blocked_issue.status_code == 302

    with app.app_context():
        assert (
            LibraryLoan.query.filter_by(
                college_id=app.config["TEST_DATA"]["college_id"],
                copy_id=copy_id,
            ).first()
            is None
        )
        reservation = db.session.get(LibraryReservation, reservation_id)
        assert reservation is not None
        assert reservation.status == "pending"

    successful_issue = client.post(
        "/library/issue",
        data={
            "copy_id": str(copy_id),
            "borrower_ref": f"student:{app.config['TEST_DATA']['student_profile_id']}",
            "due_days": "10",
        },
        follow_redirects=False,
    )
    assert successful_issue.status_code == 302

    with app.app_context():
        reservation = db.session.get(LibraryReservation, reservation_id)
        assert reservation is not None
        assert reservation.status == "fulfilled"
        loan = LibraryLoan.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            copy_id=copy_id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
        ).first()
        assert loan is not None


def test_returned_book_moves_next_reservation_to_ready_for_pickup(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Pickup Workflow Book",
            author="Queue Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-HOLD-001",
            barcode="LB-HOLD-001",
            condition="good",
            status="issued",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            teacher_id=app.config["TEST_DATA"]["teacher_profile_id"],
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() + timedelta(days=3),
            status="active",
        )
        reservation = LibraryReservation(
            college_id=book.college_id,
            book_id=book.id,
            student_id=student.id,
            status="pending",
        )
        db.session.add_all([loan, reservation])
        db.session.commit()
        loan_id = loan.id
        reservation_id = reservation.id
        copy_id = copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/loans/{loan_id}/return",
        data={"next_view": "library.circulation_desk"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        reservation = db.session.get(LibraryReservation, reservation_id)
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert reservation is not None
        assert copy is not None
        assert reservation.status == "ready_for_pickup"
        assert reservation.held_copy_id == copy.id
        assert reservation.pickup_expires_at is not None
        assert copy.status == "held"


def test_cancelling_ready_reservation_releases_held_copy(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=student.college_id,
            title="Cancel Hold Book",
            author="Queue Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-HOLD-002",
            barcode="LB-HOLD-002",
            condition="good",
            status="held",
        )
        db.session.add(copy)
        db.session.flush()

        reservation = LibraryReservation(
            college_id=book.college_id,
            book_id=book.id,
            student_id=student.id,
            status="ready_for_pickup",
            held_copy_id=copy.id,
            ready_at=utc_now_naive(),
            pickup_expires_at=utc_now_naive() + timedelta(days=2),
        )
        db.session.add(reservation)
        db.session.commit()
        reservation_id = reservation.id
        copy_id = copy.id

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/reservations/{reservation_id}/cancel",
        data={},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        reservation = db.session.get(LibraryReservation, reservation_id)
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert reservation is not None
        assert copy is not None
        assert reservation.status == "cancelled"
        assert copy.status == "available"


def test_expired_pickup_hold_releases_copy_and_marks_reservation_expired(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=student.college_id,
            title="Expired Hold Book",
            author="Queue Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-HOLD-003",
            barcode="LB-HOLD-003",
            condition="good",
            status="held",
        )
        db.session.add(copy)
        db.session.flush()

        reservation = LibraryReservation(
            college_id=book.college_id,
            book_id=book.id,
            student_id=student.id,
            status="ready_for_pickup",
            held_copy_id=copy.id,
            ready_at=utc_now_naive() - timedelta(days=3),
            pickup_expires_at=utc_now_naive() - timedelta(days=1),
        )
        db.session.add(reservation)
        db.session.commit()
        reservation_id = reservation.id
        copy_id = copy.id

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/library/my-loans")
    assert response.status_code == 200

    with app.app_context():
        reservation = db.session.get(LibraryReservation, reservation_id)
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert reservation is not None
        assert copy is not None
        assert reservation.status == "expired"
        assert reservation.expired_at is not None
        assert copy.status == "available"


def test_librarian_can_open_library_management_dashboard(app, client):
    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/library/admin")
    racks_response = client.get("/library/racks")
    assignments_response = client.get("/library/rack-assignments")
    tree_response = client.get("/library/locations")

    assert response.status_code == 200
    assert b"Library Management" in response.data
    assert racks_response.status_code == 200
    assert assignments_response.status_code == 200
    assert tree_response.status_code == 200


def test_librarian_can_create_location_hierarchy_and_assign_book(app, client):
    with app.app_context():
        department = (
            Department.query.filter_by(college_id=app.config["TEST_DATA"]["college_id"])
            .order_by(Department.id.asc())
            .first()
        )
        subject = db.session.get(Subject, app.config["TEST_DATA"]["own_subject_id"])
        assert department is not None
        assert subject is not None

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    rack_response = client.post(
        "/library/locations/create",
        data={
            "name": "Rack Alpha",
            "code": "R-ALPHA",
            "location_type": "rack",
            "row_count": "3",
            "column_count": "4",
            "is_active": "1",
        },
        follow_redirects=False,
    )

    assert rack_response.status_code == 302

    with app.app_context():
        rack = LibraryLocation.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            code="R-ALPHA",
        ).first()
        assert rack is not None
        assert rack.semester is None
        assert rack.subject_id is None
        assert rack.row_count == 3
        assert rack.column_count == 4

    with app.app_context():
        shelf = LibraryLocation.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            parent_id=rack.id,
            location_type="cell",
            row_label="2",
            column_label="3",
        ).first()
        assert shelf is not None
        assert shelf.parent_id == rack.id
        assert shelf.row_label == "2"
        assert shelf.column_label == "3"
        assert shelf.subject_id is None
        assert shelf.semester is None

    assign_cell_response = client.post(
        f"/library/locations/{shelf.id}/edit",
        data={
            "name": shelf.name,
            "code": shelf.code or "",
            "location_type": "cell",
            "parent_id": str(rack.id),
            "department_id": str(department.id),
            "semester": "1",
            "subject_id": str(subject.id),
            "row_label": "2",
            "column_label": "3",
            "is_active": "1",
        },
        follow_redirects=False,
    )

    assert assign_cell_response.status_code == 302

    with app.app_context():
        shelf = db.session.get(LibraryLocation, shelf.id)
        assert shelf.subject_id == subject.id
        assert shelf.semester == 1
        assert shelf.department_id == department.id

    create_response = client.post(
        "/library/books/create",
        data={
            "title": "Operating Systems",
            "author": "Silberschatz",
            "book_type": "physical",
            "department_id": str(department.id),
            "subject_id": str(subject.id),
            "category_mode": "new",
            "new_category_name": "Core Texts",
            "semester": "1",
            "default_location_rack_id": str(rack.id),
            "default_location_row": "2",
            "default_location_column": "3",
            "initial_location_rack_id": str(rack.id),
            "initial_location_row": "2",
            "initial_location_column": "3",
            "initial_copy_count": "1",
            "is_active": "1",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    with app.app_context():
        book = LibraryBook.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Operating Systems",
        ).first()
        assert book is not None
        assert book.default_location_id == shelf.id
        assert book.subject_id == subject.id
        assert book.semester == 1

        copy = LibraryBookCopy.query.filter_by(
            college_id=book.college_id, book_id=book.id
        ).first()
        assert copy is not None
        assert copy.location_id == shelf.id


def test_librarian_can_delete_unused_rack_branch(app, client):
    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    create_response = client.post(
        "/library/locations/create",
        data={
            "name": "Delete Rack",
            "code": "R-DELETE",
            "location_type": "rack",
            "row_count": "2",
            "column_count": "2",
            "is_active": "1",
            "next_view": "library.manage_racks",
        },
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    with app.app_context():
        rack = LibraryLocation.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            code="R-DELETE",
        ).first()
        assert rack is not None
        rack_id = rack.id

    delete_response = client.post(
        f"/library/locations/{rack_id}/delete",
        data={"next_view": "library.manage_racks"},
        follow_redirects=False,
    )

    assert delete_response.status_code == 302

    with app.app_context():
        assert db.session.get(LibraryLocation, rack_id) is None
        assert not LibraryLocation.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            parent_id=rack_id,
        ).all()


def test_librarian_cannot_delete_book_with_active_loan(app, client):
    with app.app_context():
        student = (
            Student.query.filter_by(college_id=app.config["TEST_DATA"]["college_id"])
            .order_by(Student.id.asc())
            .first()
        )
        assert student is not None

        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Delete Guard Book",
            author="Guard Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number=f"LB-{book.id:04d}-001",
            barcode=f"LB-{book.id:04d}-001",
            condition="good",
            status="issued",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=student.id,
            issued_by_user_id=app.config["TEST_DATA"]["admin_user_id"],
            due_at=utc_now_naive() + timedelta(days=7),
            status="active",
        )
        db.session.add(loan)
        db.session.commit()
        book_id = book.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/books/{book_id}/delete",
        data={"next_view": "library.admin_dashboard"},
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        assert db.session.get(LibraryBook, book_id) is not None


def test_librarian_can_mark_copy_damaged_and_repaired(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Workflow Copy",
            author="Inventory Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-WORK-001",
            barcode="LB-WORK-001",
            status="available",
            condition="good",
        )
        db.session.add(copy)
        db.session.commit()
        copy_id = copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    damaged_response = client.post(
        f"/library/copies/{copy_id}/workflow",
        data={"workflow_action": "mark_damaged", "workflow_note": "Cover torn."},
        follow_redirects=False,
    )
    repaired_response = client.post(
        f"/library/copies/{copy_id}/workflow",
        data={
            "workflow_action": "mark_repaired",
            "restored_condition": "fair",
            "workflow_note": "Rebound and ready.",
        },
        follow_redirects=False,
    )

    assert damaged_response.status_code == 302
    assert repaired_response.status_code == 302

    with app.app_context():
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert copy is not None
        assert copy.status == "available"
        assert copy.condition == "fair"

        events = (
            LibraryCopyEvent.query.filter_by(copy_id=copy_id)
            .order_by(LibraryCopyEvent.id.asc())
            .all()
        )
        assert [event.action for event in events] == [
            "marked_damaged",
            "marked_repaired",
        ]


def test_librarian_can_mark_issued_copy_lost_and_close_loan(app, client):
    with app.app_context():
        student = (
            Student.query.filter_by(college_id=app.config["TEST_DATA"]["college_id"])
            .order_by(Student.id.asc())
            .first()
        )
        assert student is not None

        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Lost Workflow Copy",
            author="Inventory Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-LOST-001",
            barcode="LB-LOST-001",
            status="issued",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=student.id,
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() + timedelta(days=7),
            status="active",
        )
        db.session.add(loan)
        db.session.commit()
        copy_id = copy.id
        loan_id = loan.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/copies/{copy_id}/workflow",
        data={
            "workflow_action": "mark_lost",
            "workflow_note": "Borrower reported the copy missing.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        copy = db.session.get(LibraryBookCopy, copy_id)
        loan = db.session.get(LibraryLoan, loan_id)
        assert copy is not None
        assert loan is not None
        assert copy.status == "lost"
        assert loan.status == "lost"
        assert loan.returned_at is not None

        event = LibraryCopyEvent.query.filter_by(
            copy_id=copy_id, loan_id=loan_id, action="marked_lost"
        ).first()
        assert event is not None


def test_librarian_can_receive_replacement_copy(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Replacement Workflow Copy",
            author="Inventory Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        old_copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-REPL-001",
            barcode="LB-REPL-001",
            status="damaged",
            condition="damaged",
        )
        db.session.add(old_copy)
        db.session.commit()
        old_copy_id = old_copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/copies/{old_copy_id}/workflow",
        data={
            "workflow_action": "replacement_received",
            "restored_condition": "new",
            "workflow_note": "Vendor supplied a new copy.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        old_copy = db.session.get(LibraryBookCopy, old_copy_id)
        replacement = LibraryBookCopy.query.filter_by(
            replacement_of_copy_id=old_copy_id
        ).first()
        assert old_copy is not None
        assert replacement is not None
        assert old_copy.status == "written_off"
        assert replacement.status == "available"
        assert replacement.condition == "new"

        events = (
            LibraryCopyEvent.query.filter(
                LibraryCopyEvent.copy_id.in_([old_copy_id, replacement.id])
            )
            .order_by(LibraryCopyEvent.id.asc())
            .all()
        )
        assert any(event.action == "replacement_received" for event in events)
        assert any(event.action == "replacement_created" for event in events)


def test_librarian_can_run_stock_audit_session(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Audit Book",
            author="Audit Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        first_copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-AUD-001",
            barcode="LB-AUD-001",
            status="available",
            condition="good",
        )
        second_copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-AUD-002",
            barcode="LB-AUD-002",
            status="maintenance",
            condition="fair",
        )
        db.session.add_all([first_copy, second_copy])
        db.session.commit()
        first_copy_id = first_copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    create_response = client.post(
        "/library/audits",
        data={"title": "Main Shelf Check"},
        follow_redirects=False,
    )

    assert create_response.status_code == 302

    with app.app_context():
        audit_session = LibraryAuditSession.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Main Shelf Check",
        ).first()
        assert audit_session is not None
        assert audit_session.expected_count == 2
        session_id = audit_session.id
        entry = LibraryAuditEntry.query.filter_by(
            session_id=session_id, copy_id=first_copy_id
        ).first()
        assert entry is not None

    scan_response = client.post(
        f"/library/audits/{session_id}/scan",
        data={"copy_scan": "LB-AUD-001"},
        follow_redirects=False,
    )
    finalize_response = client.post(
        f"/library/audits/{session_id}/finalize",
        follow_redirects=False,
    )

    assert scan_response.status_code == 302
    assert finalize_response.status_code == 302

    with app.app_context():
        audit_session = db.session.get(LibraryAuditSession, session_id)
        assert audit_session is not None
        assert audit_session.status == "completed"
        assert audit_session.scanned_count == 1
        assert audit_session.missing_count == 1


def test_completed_stock_audit_can_mark_missing_copy_lost(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Audit Missing Lost",
            author="Audit Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-AUD-LOST-001",
            barcode="LB-AUD-LOST-001",
            status="available",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        session = LibraryAuditSession(
            college_id=book.college_id,
            created_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            completed_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            title="Completed Missing Audit",
            status="completed",
            expected_count=1,
            scanned_count=0,
            missing_count=1,
            completed_at=utc_now_naive(),
        )
        db.session.add(session)
        db.session.flush()

        entry = LibraryAuditEntry(
            session_id=session.id,
            copy_id=copy.id,
            expected_status="available",
            expected_condition="good",
            is_present=False,
        )
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id
        copy_id = copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/audits/entries/{entry_id}/resolve",
        data={
            "discrepancy_action": "marked_lost",
            "note": "Missing during shelf check.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        entry = db.session.get(LibraryAuditEntry, entry_id)
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert entry is not None
        assert copy is not None
        assert entry.discrepancy_status == "marked_lost"
        assert entry.resolved_at is not None
        assert copy.status == "lost"


def test_completed_stock_audit_can_mark_follow_up_required(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Audit Follow Up",
            author="Audit Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-AUD-FUP-001",
            barcode="LB-AUD-FUP-001",
            status="available",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        session = LibraryAuditSession(
            college_id=book.college_id,
            created_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            completed_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            title="Completed Follow Up Audit",
            status="completed",
            expected_count=1,
            scanned_count=0,
            missing_count=1,
            completed_at=utc_now_naive(),
        )
        db.session.add(session)
        db.session.flush()

        entry = LibraryAuditEntry(
            session_id=session.id,
            copy_id=copy.id,
            expected_status="available",
            expected_condition="good",
            is_present=False,
        )
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id
        copy_id = copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/audits/entries/{entry_id}/resolve",
        data={
            "discrepancy_action": "follow_up_required",
            "note": "Check other room first.",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302

    with app.app_context():
        entry = db.session.get(LibraryAuditEntry, entry_id)
        copy = db.session.get(LibraryBookCopy, copy_id)
        assert entry is not None
        assert copy is not None
        assert entry.discrepancy_status == "follow_up_required"
        assert entry.resolved_at is not None
        assert copy.status == "available"


def test_ready_pickup_private_notification_appears_in_student_feed(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=student.college_id,
            title="Pickup Notice Title",
            author="Queue Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-NOTIFY-PICKUP-001",
            barcode="LB-NOTIFY-PICKUP-001",
            status="issued",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            teacher_id=app.config["TEST_DATA"]["teacher_profile_id"],
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() + timedelta(days=2),
            status="active",
        )
        reservation = LibraryReservation(
            college_id=book.college_id,
            book_id=book.id,
            student_id=student.id,
            status="pending",
        )
        db.session.add_all([loan, reservation])
        db.session.commit()
        loan_id = loan.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/loans/{loan_id}/return",
        data={"next_view": "library.circulation_desk"},
        follow_redirects=False,
    )
    assert response.status_code == 302

    client.get("/logout")
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    feed = client.get("/notices/feed")

    assert feed.status_code == 200
    payload = feed.get_json()
    assert any(
        item["title"] == "Library pickup ready: Pickup Notice Title"
        and item["target_role"] == "private"
        and item["is_read"] is False
        for item in payload["items"]
    )

    with app.app_context():
        notification = (
            UserNotification.query.filter_by(
                college_id=app.config["TEST_DATA"]["college_id"],
                user_id=app.config["TEST_DATA"]["student_user_id"],
                title="Library pickup ready: Pickup Notice Title",
            )
            .order_by(UserNotification.id.desc())
            .first()
        )
        assert notification is not None


def test_overdue_private_notification_appears_in_student_feed(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=student.college_id,
            title="Overdue Notice Title",
            author="Fine Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-NOTIFY-OVERDUE-001",
            barcode="LB-NOTIFY-OVERDUE-001",
            status="issued",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=student.id,
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() - timedelta(days=2),
            status="active",
        )
        db.session.add(loan)
        db.session.commit()

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    page = client.get("/library/my-loans")
    assert page.status_code == 200

    feed = client.get("/notices/feed")
    assert feed.status_code == 200
    payload = feed.get_json()
    assert any(
        item["title"] == "Library overdue: Overdue Notice Title"
        and item["target_role"] == "private"
        for item in payload["items"]
    )


def test_fine_private_notification_appears_in_student_feed(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        rule = LibraryRule(
            college_id=student.college_id,
            student_max_active_loans=3,
            teacher_max_active_loans=5,
            student_due_days=14,
            teacher_due_days=30,
            student_max_renewals=1,
            teacher_max_renewals=2,
            student_renew_days=7,
            teacher_renew_days=14,
            student_fine_per_day=5.00,
            teacher_fine_per_day=1.00,
            grace_days=0,
        )
        db.session.add(rule)

        book = LibraryBook(
            college_id=student.college_id,
            title="Fine Notice Title",
            author="Ledger Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-NOTIFY-FINE-001",
            barcode="LB-NOTIFY-FINE-001",
            status="issued",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=student.id,
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() - timedelta(days=2),
            status="overdue",
        )
        db.session.add(loan)
        db.session.commit()
        loan_id = loan.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/loans/{loan_id}/return", data={}, follow_redirects=False
    )
    assert response.status_code == 302

    client.get("/logout")
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    feed = client.get("/notices/feed")

    assert feed.status_code == 200
    payload = feed.get_json()
    assert any(
        item["title"] == "Library fine: Fine Notice Title"
        and item["category"] == "fee"
        and item["target_role"] == "private"
        for item in payload["items"]
    )


def test_lost_copy_private_notification_appears_in_student_feed(app, client):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None

        book = LibraryBook(
            college_id=student.college_id,
            title="Lost Notice Title",
            author="Inventory Author",
            book_type="physical",
            department_id=student.department_id,
            semester=student.semester,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-NOTIFY-LOST-001",
            barcode="LB-NOTIFY-LOST-001",
            status="issued",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=student.id,
            issued_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            due_at=utc_now_naive() + timedelta(days=5),
            status="active",
        )
        db.session.add(loan)
        db.session.commit()
        copy_id = copy.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/copies/{copy_id}/workflow",
        data={
            "workflow_action": "mark_lost",
            "workflow_note": "Borrower reported it missing.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    client.get("/logout")
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    feed = client.get("/notices/feed")

    assert feed.status_code == 200
    payload = feed.get_json()
    assert any(
        item["title"] == "Library follow-up: copy marked lost for Lost Notice Title"
        and item["category"] == "urgent"
        and item["target_role"] == "private"
        for item in payload["items"]
    )


def test_audit_follow_up_private_notification_appears_in_admin_feed(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Audit Notice Title",
            author="Audit Author",
            book_type="physical",
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-NOTIFY-AUD-001",
            barcode="LB-NOTIFY-AUD-001",
            status="available",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        session = LibraryAuditSession(
            college_id=book.college_id,
            created_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            completed_by_user_id=app.config["TEST_DATA"]["librarian_user_id"],
            title="Audit Follow Up Notifications",
            status="completed",
            expected_count=1,
            scanned_count=0,
            missing_count=1,
            completed_at=utc_now_naive(),
        )
        db.session.add(session)
        db.session.flush()

        entry = LibraryAuditEntry(
            session_id=session.id,
            copy_id=copy.id,
            expected_status="available",
            expected_condition="good",
            is_present=False,
        )
        db.session.add(entry)
        db.session.commit()
        entry_id = entry.id

    login(
        client,
        "librarian1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/library/audits/entries/{entry_id}/resolve",
        data={
            "discrepancy_action": "follow_up_required",
            "note": "Need manual shelf check.",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302

    client.get("/logout")
    login(client, "admin@example.com")
    feed = client.get("/notices/feed")

    assert feed.status_code == 200
    payload = feed.get_json()
    assert any(
        item["title"] == "Library audit follow-up: LB-NOTIFY-AUD-001"
        and item["target_role"] == "private"
        and item["category"] == "urgent"
        for item in payload["items"]
    )

    with app.app_context():
        notification = UserNotification.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"],
            user_id=app.config["TEST_DATA"]["admin_user_id"],
            title="Library audit follow-up: LB-NOTIFY-AUD-001",
        ).first()
        assert notification is not None


def test_student_dashboard_library_summary_counts_ready_pickup_reservations(
    app, client
):
    with app.app_context():
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert student is not None
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Ready Pickup Title",
            author="Queue Author",
            book_type="physical",
            department_id=student.department_id,
            semester=1,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        reservation = LibraryReservation(
            college_id=book.college_id,
            book_id=book.id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            status="ready_for_pickup",
            ready_at=utc_now_naive(),
            pickup_expires_at=utc_now_naive() + timedelta(days=2),
        )
        db.session.add(reservation)
        db.session.commit()

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/student/dashboard")

    assert response.status_code == 200
    assert b"Library & E-Library" in response.data
    assert b"Reservations / Pickups" in response.data


def test_parent_library_overview_shows_child_library_loans(app, client):
    with app.app_context():
        book = LibraryBook(
            college_id=app.config["TEST_DATA"]["college_id"],
            title="Computer Networks",
            author="Andrew Tanenbaum",
            book_type="physical",
            semester=1,
            is_active=True,
        )
        db.session.add(book)
        db.session.flush()

        copy = LibraryBookCopy(
            college_id=book.college_id,
            book_id=book.id,
            accession_number="LB-TEST-001",
            barcode="LB-TEST-001",
            status="issued",
            condition="good",
        )
        db.session.add(copy)
        db.session.flush()

        loan = LibraryLoan(
            college_id=book.college_id,
            book_id=book.id,
            copy_id=copy.id,
            student_id=app.config["TEST_DATA"]["student_profile_id"],
            issued_by_user_id=app.config["TEST_DATA"]["admin_user_id"],
            due_at=datetime.combine(date.today() + timedelta(days=7), time.min),
            status="active",
        )
        db.session.add(loan)
        db.session.commit()

    login(
        client,
        "parent1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/library/parent")

    assert response.status_code == 200
    assert b"Computer Networks" in response.data


def test_super_admin_can_request_forgot_password_without_college_code(app, client):
    sent_messages = []

    def _capture_message(message):
        sent_messages.append(message)

    with patch.object(mail, "send", side_effect=_capture_message):
        response = client.post(
            "/forgot-password",
            data={
                "email": "superadmin@example.com",
            },
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert sent_messages
    assert sent_messages[0].recipients == ["superadmin@example.com"]
    assert b"If we found an active account for that email" in response.data


def test_student_must_change_temporary_password_and_then_sign_in_again(app, client):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        user.set_temporary_password("TempPass@123")
        db.session.commit()

    login(
        client,
        "student1@example.com",
        password="TempPass@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/password-setup-prompt",
        data={
            "new_password": "StudentDirect@123",
            "confirm_password": "StudentDirect@123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Please sign in again with your new password" in response.data
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user.must_change_password is False
        assert user.check_password("StudentDirect@123") is True
    old_password_login = login(
        client,
        "student1@example.com",
        password="TempPass@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    assert old_password_login.status_code == 200
    assert b"Invalid email or password" in old_password_login.data
    new_password_login = login(
        client,
        "student1@example.com",
        password="StudentDirect@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    assert new_password_login.status_code == 302
    assert new_password_login.headers["Location"].endswith("/student/dashboard")


def test_student_cannot_reuse_temporary_password_as_new_password(app, client):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        user.set_temporary_password("TempPass@123")
        db.session.commit()

    login(
        client,
        "student1@example.com",
        password="TempPass@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/password-setup-prompt",
        data={
            "new_password": "TempPass@123",
            "confirm_password": "TempPass@123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"must be different from the current one" in response.data
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user.must_change_password is True
        assert user.check_password("TempPass@123") is True


def test_student_can_set_password_from_email_link(app, client):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        user.set_temporary_password("TempPass@123")
        db.session.commit()
        token = generate_password_setup_token(user)

    response = client.post(
        f"/set-password/{token}",
        data={
            "new_password": "StudentNew@123",
            "confirm_password": "StudentNew@123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Please sign in with your new password" in response.data
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user.must_change_password is False
        assert user.password_changed_at is not None
        assert user.check_password("StudentNew@123") is True


def test_password_reset_link_rejects_reusing_existing_password(app, client):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        token = generate_password_setup_token(user)

    response = client.post(
        f"/set-password/{token}?mode=reset",
        data={
            "new_password": "Password@123",
            "confirm_password": "Password@123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"must be different from the current one" in response.data


def test_change_password_rejects_reusing_existing_password(app, client):
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/change-password",
        data={
            "current_password": "Password@123",
            "new_password": "Password@123",
            "confirm_password": "Password@123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"must be different from the current one" in response.data


def test_forgot_password_email_uses_reset_mode_link(app):
    with app.app_context():
        app.config["PUBLIC_BASE_URL"] = "https://portal.smartattend.test"
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        sent_messages = []

        def _capture_message(message):
            sent_messages.append(message)

        with patch.object(mail, "send", side_effect=_capture_message):
            from utils.account_setup import send_password_reset_email

            send_password_reset_email(user)

        assert sent_messages
        assert "mode=reset" in sent_messages[0].html


def test_password_setup_email_uses_public_base_url_when_configured(app):
    with app.app_context():
        app.config["PUBLIC_BASE_URL"] = "https://portal.smartattend.test"
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        token = generate_password_setup_token(user)
        link = build_public_url("auth.set_password_from_email", token=token)

        assert link.startswith("https://portal.smartattend.test/set-password/")


def test_password_setup_link_uses_college_subdomain_when_available(app):
    with app.app_context():
        app.config["PUBLIC_BASE_URL"] = "https://portal.smartattend.test"
        app.config["MULTI_COLLEGE_ROOT_DOMAIN"] = "smartattend.test"
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user is not None
        user.college.subdomain = "alpha"
        db.session.commit()

        token = generate_password_setup_token(user)
        link = build_public_url(
            "auth.set_password_from_email", college=user.college, token=token
        )

        assert link.startswith("https://alpha.smartattend.test/set-password/")


def test_password_reset_email_uses_college_subdomain_when_available(app):
    with app.app_context():
        app.config["PUBLIC_BASE_URL"] = "https://portal.smartattend.test"
        app.config["MULTI_COLLEGE_ROOT_DOMAIN"] = "smartattend.test"
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user is not None
        user.college.subdomain = "alpha"
        db.session.commit()
        sent_messages = []

        def _capture_message(message):
            sent_messages.append(message)

        with patch.object(mail, "send", side_effect=_capture_message):
            from utils.account_setup import send_password_reset_email

            send_password_reset_email(user)

        assert sent_messages
        assert "https://alpha.smartattend.test/set-password/" in sent_messages[0].html
        assert "mode=reset" in sent_messages[0].html


def test_parent_with_temporary_password_is_prompted_on_first_login(app, client):
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["parent_user_id"])
        user.set_temporary_password("ParentTemp@123")
        db.session.commit()

    response = login(
        client,
        "parent1@example.com",
        password="ParentTemp@123",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/password-setup-prompt")


def test_admin_password_reset_creates_temporary_password_state(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/admin/users/reset-password/{app.config['TEST_DATA']['student_user_id']}",
        data={"new_password": "ResetTemp@123"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        user = db.session.get(User, app.config["TEST_DATA"]["student_user_id"])
        assert user.must_change_password is True
        assert user.password_changed_at is None
        assert user.check_password("ResetTemp@123") is True


def test_admin_can_add_parent_with_temporary_password(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/admin/parents/add",
        data={
            "name": "Parent Two",
            "email": "parent2@example.com",
            "password": "ParentTemp@123",
            "student_id": str(app.config["TEST_DATA"]["student_profile_id"]),
            "relationship": "guardian",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="parent2@example.com").first()
        assert user is not None
        assert user.role == "parent"
        assert user.must_change_password is True
        assert user.password_changed_at is None


def test_admin_can_edit_subject_credit_hours_without_500(app, client):
    from models.subject import Subject

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    with app.app_context():
        subject = db.session.get(Subject, app.config["TEST_DATA"]["own_subject_id"])
        assert subject is not None
        subject_id = subject.id
        teacher_id = subject.teacher_id
        department_id = subject.department_id

    response = client.post(
        f"/admin/subjects/edit/{subject_id}",
        data={
            "name": "Programming Fundamentals",
            "code": "CS101",
            "department_id": str(department_id),
            "teacher_id": str(teacher_id),
            "semester": "1",
            "credit_hours": "4",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Subject CS101 updated." in response.data

    with app.app_context():
        updated = db.session.get(Subject, subject_id)
        assert updated.credit_hours == 4


def test_admin_can_delete_subject_without_500(app, client):
    from models.subject import Subject

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    with app.app_context():
        base_subject = db.session.get(
            Subject, app.config["TEST_DATA"]["own_subject_id"]
        )
        subject = Subject(
            college_id=app.config["TEST_DATA"]["college_id"],
            name="Temporary Subject",
            code="TMP401",
            department_id=base_subject.department_id,
            teacher_id=base_subject.teacher_id,
            semester=1,
            credit_hours=3,
        )
        db.session.add(subject)
        db.session.commit()
        subject_id = subject.id

    response = client.post(
        f"/admin/subjects/delete/{subject_id}",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Subject deleted." in response.data

    with app.app_context():
        deleted = db.session.get(Subject, subject_id)
        assert deleted is None


def test_admin_settings_page_renders_without_500(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/admin/settings")

    assert response.status_code == 200
    assert b"collegeSettingsForm" in response.data
    assert b"Save Settings" in response.data
    assert b'name="college_logo"' in response.data


def test_admin_can_upload_college_logo_without_500(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/admin/settings/logo",
        data={
            "college_logo": (io.BytesIO(make_valid_png_bytes()), "college-logo.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"College logo updated." in response.data

    with app.app_context():
        college = db.session.get(College, app.config["TEST_DATA"]["college_id"])
        cs = CollegeSetting.get(college=college)
        assert cs.logo_path
        assert cs.logo_path.startswith("uploads/college_logos/")
        assert os.path.exists(os.path.join(app.static_folder, cs.logo_path))


def test_admin_can_save_settings_and_logo_in_single_submit(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/admin/settings/save",
        data={
            "college_name": "Updated Alpha College",
            "address": "Kathmandu",
            "latitude": "27.717200",
            "longitude": "85.324000",
            "college_logo": (
                io.BytesIO(make_valid_png_bytes()),
                "single-submit-logo.png",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"College settings and logo saved successfully." in response.data

    with app.app_context():
        college = db.session.get(College, app.config["TEST_DATA"]["college_id"])
        cs = CollegeSetting.get(college=college)
        assert college.name == "Updated Alpha College"
        assert cs.college_name == "Updated Alpha College"
        assert cs.address == "Kathmandu"
        assert cs.logo_path
        assert cs.logo_path.startswith("uploads/college_logos/")
        assert os.path.exists(os.path.join(app.static_folder, cs.logo_path))


def test_admin_logo_upload_rejects_tiny_invalid_image(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/admin/settings/save",
        data={
            "college_name": "Alpha College",
            "college_logo": (io.BytesIO(b"bad"), "tiny-logo.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200


def test_admin_teachers_page_shows_teacher_live_status(app, client):
    with app.app_context():
        subject = db.session.get(Subject, app.config["TEST_DATA"]["own_subject_id"])
        db.session.add(
            TeacherStatus(
                college_id=app.config["TEST_DATA"]["college_id"],
                teacher_id=subject.teacher_id,
                status="in_class",
                note="Teaching Lab A",
            )
        )
        db.session.commit()

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/admin/teachers")

    assert response.status_code == 200
    assert b"In Class" in response.data
    assert b"Teaching Lab A" in response.data


def test_student_dashboard_shows_teacher_status_for_todays_classes(app, client):
    with app.app_context():
        subject = db.session.get(Subject, app.config["TEST_DATA"]["own_subject_id"])
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        db.session.add(
            TeacherStatus(
                college_id=app.config["TEST_DATA"]["college_id"],
                teacher_id=subject.teacher_id,
                status="on_campus",
                note="Available before lecture",
            )
        )
        db.session.add(
            TimetableSlot(
                college_id=app.config["TEST_DATA"]["college_id"],
                department_id=student.department_id,
                semester=student.semester,
                day_of_week=date.today().weekday(),
                period_no=1,
                start_time=time(10, 0),
                end_time=time(11, 0),
                subject_id=subject.id,
                teacher_id=subject.teacher_id,
                slot_type="lecture",
            )
        )
        db.session.commit()

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/student/dashboard")

    assert response.status_code == 200
    assert b"Today's Classes" in response.data
    assert b"On Campus" in response.data
    assert b"Available before lecture" in response.data


def test_teacher_cannot_download_another_teachers_subject_report(app, client):
    login(client, "teacher1@example.com")

    other_subject_id = app.config["TEST_DATA"]["other_subject_id"]
    response = client.get(f"/teacher/reports/subject/{other_subject_id}/download")

    assert response.status_code == 403


def test_student_cannot_open_teacher_only_notice(app, client):
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    notice_id = app.config["TEST_DATA"]["teacher_notice_id"]
    response = client.get(f"/notices/{notice_id}")

    assert response.status_code == 404


def test_teacher_attachment_rejects_active_html_upload(app, client):
    login(client, "teacher1@example.com")

    subject_id = app.config["TEST_DATA"]["own_subject_id"]
    response = client.post(
        "/teacher/content/new",
        data={
            "title": "Unsafe Upload",
            "content_type": "note",
            "subject_id": str(subject_id),
            "semester": "1",
            "attachment": (
                io.BytesIO(b"<html><script>alert(1)</script></html>"),
                "unsafe.html",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Unsupported attachment type" in response.data


def test_student_can_fetch_private_note_attachment(app, client):
    content_id = app.config["TEST_DATA"]["content_id"]
    upload_dir = app.config["CONTENT_UPLOAD_FOLDER"]
    filename = "fixture-note.txt"
    abs_path = os.path.join(upload_dir, filename)

    with app.app_context():
        item = db.session.get(TeacherContent, content_id)
        item.file_path = f"uploads/content/{filename}"
        db.session.commit()

    with open(abs_path, "w", encoding="utf-8") as handle:
        handle.write("private note body")

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get(f"/student/content/{content_id}/file?download=0")

    assert response.status_code == 200
    assert response.data == b"private note body"


def test_super_admin_system_setup_page_loads(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/super-admin/system-setup")

    assert response.status_code == 200
    assert b"Platform Readiness" in response.data
    assert b"Platform Checks" in response.data


def test_admin_cannot_open_super_admin_system_setup(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/super-admin/system-setup")

    assert response.status_code == 403


def test_super_admin_can_create_college(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/super-admin/colleges/create",
        data={
            "name": "Gamma College",
            "code": "GAMMA",
            "subdomain": "gamma",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        college = College.query.filter_by(code="GAMMA").first()
        assert college is not None
        assert college.name == "Gamma College"
        assert college.subdomain == "gamma"
        assert college.plan == "free"
        assert college.plan_expires_at is not None
        feature_rows = CollegeFeatureAccess.query.filter_by(college_id=college.id).all()
        assert feature_rows
        assert all(row.enabled is True for row in feature_rows)
        log = PlatformAuditLog.query.filter_by(
            action_key="college.created", college_id=college.id
        ).first()
        assert log is not None
        assert "Created college Gamma College [GAMMA]" in log.summary


def test_super_admin_can_create_university(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/super-admin/universities/create",
        data={
            "name": "Tribhuvan University",
            "code": "TU",
            "description": "Nepal public university affiliation structure.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Tribhuvan University [TU] created successfully." in response.data

    with app.app_context():
        university = University.query.filter_by(code="TU").first()
        assert university is not None
        assert university.name == "Tribhuvan University"
        log = (
            PlatformAuditLog.query.filter_by(action_key="university.created")
            .order_by(PlatformAuditLog.created_at.desc())
            .first()
        )
        assert log is not None
        assert "Created university Tribhuvan University [TU]" in log.summary


def test_super_admin_can_create_college_with_university_affiliation(app, client):
    with app.app_context():
        university = University(name="Pokhara University", code="PU", is_active=True)
        db.session.add(university)
        db.session.commit()
        university_id = university.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/super-admin/colleges/create",
        data={
            "name": "Lambda College",
            "code": "LAMBDA",
            "subdomain": "lambda",
            "university_id": university_id,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        college = College.query.filter_by(code="LAMBDA").first()
        assert college is not None
        assert college.university_id == university_id
        log = PlatformAuditLog.query.filter_by(
            action_key="college.created", college_id=college.id
        ).first()
        assert log is not None
        assert log.get_details().get("university") == "PU"

    colleges_response = client.get("/super-admin/colleges")
    colleges_page = colleges_response.get_data(as_text=True)
    assert colleges_response.status_code == 200
    assert "Pokhara University" in colleges_page
    assert "PU" in colleges_page
    assert "Lambda College" in colleges_page


def test_super_admin_university_detail_shows_affiliated_college_summary(app, client):
    with app.app_context():
        university = University(name="Kathmandu University", code="KU", is_active=True)
        db.session.add(university)
        db.session.flush()

        college = db.session.get(College, app.config["TEST_DATA"]["college_id"])
        department = Department.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"]
        ).first()
        assert college is not None
        assert department is not None
        department_name = department.name
        department.university_id = university.id
        db.session.commit()
        university_id = university.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get(f"/super-admin/universities/{university_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Affiliated Colleges" in page
    assert "Department Summary Across Colleges" in page
    assert "Kathmandu University" in page
    assert "Alpha College" in page
    assert department_name in page


def test_admin_can_map_department_to_university(app, client):
    with app.app_context():
        university = University(name="Tribhuvan University", code="TU", is_active=True)
        db.session.add(university)
        db.session.commit()
        university_id = university.id

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/admin/departments",
        data={
            "name": "BCA",
            "code": "BCA",
            "university_id": university_id,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Department BCA added." in response.data

    with app.app_context():
        department = Department.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"], code="BCA"
        ).first()
        assert department is not None
        assert department.university_id == university_id


def test_admin_people_pages_show_department_university(app, client):
    with app.app_context():
        university = University(name="Purbanchal University", code="PU", is_active=True)
        db.session.add(university)
        db.session.flush()
        department = Department.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"]
        ).first()
        assert department is not None
        department.university_id = university.id
        db.session.commit()

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    students_response = client.get("/admin/students")
    students_page = students_response.get_data(as_text=True)
    assert students_response.status_code == 200
    assert "University" in students_page
    assert "PU" in students_page

    teachers_response = client.get("/admin/teachers")
    teachers_page = teachers_response.get_data(as_text=True)
    assert teachers_response.status_code == 200
    assert "University" in teachers_page
    assert "Purbanchal University" in teachers_page

    subjects_response = client.get("/admin/subjects")
    subjects_page = subjects_response.get_data(as_text=True)
    assert subjects_response.status_code == 200
    assert "University" in subjects_page
    assert "PU" in subjects_page


def test_student_roll_number_generation_uses_department_university(app):
    with app.app_context():
        university = University(name="Tribhuvan University", code="TU", is_active=True)
        db.session.add(university)
        db.session.flush()
        department = Department.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"]
        ).first()
        assert department is not None
        department.university_id = university.id
        db.session.commit()

        roll_number = Student.generate_roll_number(
            app.config["TEST_DATA"]["college_id"],
            department.id,
            2026,
        )

    assert roll_number.startswith("TU-")
    assert f"-{department.code}-2026-" in roll_number


def test_student_roll_preview_and_id_card_use_university_based_identifier(app, client):
    with app.app_context():
        university = University(name="Kathmandu University", code="KU", is_active=True)
        db.session.add(university)
        db.session.flush()
        department = Department.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"]
        ).first()
        student = db.session.get(Student, app.config["TEST_DATA"]["student_profile_id"])
        assert department is not None
        assert student is not None
        department.university_id = university.id
        student.roll_number = "KU-BCA-2026-001"
        student_id_card = StudentIDCard(
            college_id=app.config["TEST_DATA"]["college_id"],
            student_id=student.id,
            status="pending",
        )
        db.session.add(student_id_card)
        db.session.commit()
        department_id = department.id
        student_id_card_id = student_id_card.id

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    preview_response = client.get(
        f"/admin/students/preview-id?dept_id={department_id}&year=2026"
    )
    preview_payload = preview_response.get_json()

    assert preview_response.status_code == 200
    assert preview_payload["id"].startswith("KU-")

    approve_response = client.post(
        f"/admin/id-cards/{student_id_card_id}/approve",
        follow_redirects=True,
    )
    assert approve_response.status_code == 200

    with app.app_context():
        student_id_card = db.session.get(StudentIDCard, student_id_card_id)
        assert student_id_card is not None
        assert student_id_card.card_number == "KU-BCA-2026-001"


def test_super_admin_college_detail_shows_program_university_map(app, client):
    with app.app_context():
        university = University(name="Tribhuvan University", code="TU", is_active=True)
        db.session.add(university)
        db.session.flush()
        college = db.session.get(College, app.config["TEST_DATA"]["college_id"])
        department = Department.query.filter_by(
            college_id=app.config["TEST_DATA"]["college_id"]
        ).first()
        assert college is not None
        assert department is not None
        department_name = department.name
        department.university_id = university.id
        db.session.commit()
        college_id = college.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get(f"/super-admin/colleges/{college_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Program University Map" in page
    assert department_name in page
    assert "Tribhuvan University" in page
    assert "TU" in page


def test_super_admin_can_create_college_admin(app, client):
    with app.app_context():
        college = College(name="Beta College", code="BETA")
        db.session.add(college)
        db.session.commit()
        college_id = college.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/super-admin/colleges/{college_id}/admins/create",
        data={
            "name": "Beta Admin",
            "email": "beta.admin@example.com",
            "password": "Password@123",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(
            email="beta.admin@example.com", college_id=college_id
        ).first()
        assert user is not None
        assert user.role == "admin"


def test_super_admin_cannot_deactivate_host_college(app, client):
    with app.app_context():
        # Temporarily make super_admin a member of the college being toggled to simulate "host college" deactivation block
        super_admin = User.query.filter_by(email="superadmin@example.com").first()
        super_admin.college_id = app.config["TEST_DATA"]["college_id"]
        db.session.commit()

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    college_id = app.config["TEST_DATA"]["college_id"]

    response = client.post(
        f"/super-admin/colleges/{college_id}/toggle",
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        college = db.session.get(College, college_id)
        assert college is not None
        assert college.is_active is True

        # Restore super_admin's college_id back to None for other tests
        super_admin = User.query.filter_by(email="superadmin@example.com").first()
        super_admin.college_id = None
        db.session.commit()


def test_super_admin_can_update_college_feature_access(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    college_id = app.config["TEST_DATA"]["college_id"]

    response = client.post(
        f"/super-admin/colleges/{college_id}/features",
        data={
            "enabled_features": ["attendance", "learning_content", "notices"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Feature access updated for Alpha College." in response.data

    with app.app_context():
        fees_access = CollegeFeatureAccess.query.filter_by(
            college_id=college_id, feature_key="fees"
        ).first()
        content_access = CollegeFeatureAccess.query.filter_by(
            college_id=college_id, feature_key="learning_content"
        ).first()
        assert fees_access is not None
        assert fees_access.enabled is False
        assert content_access is not None
        assert content_access.enabled is True
        log = (
            PlatformAuditLog.query.filter_by(
                action_key="college.features_updated",
                college_id=college_id,
            )
            .order_by(PlatformAuditLog.created_at.desc())
            .first()
        )
        assert log is not None


def test_super_admin_colleges_page_shows_tier_prices(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/super-admin/colleges")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Quick Tier Presets" in page
    assert "Rs. 2,999 / month" in page
    assert "Rs. 5,999 / month" in page
    assert "Rs. 8,999 / month" in page
    assert "Custom pricing" in page


def test_super_admin_free_trial_enables_full_feature_access_and_sets_expiry(
    app, client
):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    college_id = app.config["TEST_DATA"]["college_id"]

    prime_response = client.post(
        f"/super-admin/colleges/{college_id}/features",
        data={
            "enabled_features": ["attendance", "learning_content", "library", "fees"],
        },
        follow_redirects=True,
    )
    assert prime_response.status_code == 200

    response = client.post(
        f"/super-admin/colleges/{college_id}/plan",
        data={
            "plan": "free",
            "plan_expires_at": "",
            "billing_notes": "Downgraded for evaluation only.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Plan updated to Free Trial for Alpha College." in response.data

    with app.app_context():
        college = db.session.get(College, college_id)
        assert college is not None
        assert college.plan == "free"
        assert college.plan_expires_at is not None

        feature_rows = CollegeFeatureAccess.query.filter_by(college_id=college_id).all()
        assert feature_rows
        assert all(row.enabled is True for row in feature_rows)
        feature_map = {row.feature_key: row.enabled for row in feature_rows}
        assert feature_map["attendance"] is True
        assert feature_map["library"] is True
        assert feature_map["fees"] is True

        log = (
            PlatformAuditLog.query.filter_by(
                action_key="college.plan_updated",
                college_id=college_id,
            )
            .order_by(PlatformAuditLog.created_at.desc())
            .first()
        )
        assert log is not None


def test_super_admin_tier_preset_updates_plan_and_clears_free_trial_status(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    college_id = app.config["TEST_DATA"]["college_id"]

    response = client.post(
        f"/super-admin/colleges/{college_id}/features",
        data={
            "preset": "professional",
            "enabled_features": [
                "attendance",
                "notices",
                "calendar",
                "timetable",
                "classrooms",
                "learning_content",
                "library",
                "exams",
                "leaves",
                "batch_tracker",
                "report_emails",
                "digital_id_cards",
                "fees",
                "fee_reminders",
                "parent_portal",
                "analytics",
                "ai_assistant",
            ],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"college plan was updated" in response.data

    with app.app_context():
        college = db.session.get(College, college_id)
        assert college is not None
        assert college.plan == "professional"
        assert college.plan_expires_at is None

        feature_rows = {
            row.feature_key: row.enabled
            for row in CollegeFeatureAccess.query.filter_by(college_id=college_id).all()
        }
        assert feature_rows["library"] is True
        assert feature_rows["fees"] is True
        assert feature_rows["ai_assistant"] is True
        assert feature_rows["face_biometrics"] is False

        log = (
            PlatformAuditLog.query.filter_by(
                action_key="college.plan_updated",
                college_id=college_id,
            )
            .order_by(PlatformAuditLog.created_at.desc())
            .first()
        )
        assert log is not None
        details = log.get_details()
        assert details.get("source") == "feature_preset"
        assert details.get("new_plan") == "professional"

    client.get("/logout")
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    admin_response = client.get("/admin/my-plan")
    admin_page = admin_response.get_data(as_text=True)

    assert admin_response.status_code == 200
    assert "Professional Plan" in admin_page
    assert "Free Trial Plan" not in admin_page


def test_manual_feature_mix_shows_custom_plan_instead_of_paid_tier(app, client):
    with app.app_context():
        college = db.session.get(College, app.config["TEST_DATA"]["college_id"])
        assert college is not None
        college.plan = "professional"
        college.plan_expires_at = None
        db.session.commit()

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/super-admin/colleges/{app.config['TEST_DATA']['college_id']}/features",
        data={
            "enabled_features": ["attendance", "notices", "library", "analytics"],
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Feature access updated for Alpha College." in response.data

    detail_response = client.get(
        f"/super-admin/colleges/{app.config['TEST_DATA']['college_id']}"
    )
    detail_page = detail_response.get_data(as_text=True)
    assert "Custom Plan" in detail_page
    assert "Billing tier: Professional" in detail_page

    colleges_response = client.get("/super-admin/colleges")
    colleges_page = colleges_response.get_data(as_text=True)
    assert "Custom Plan" in colleges_page
    assert "Billing: Professional" in colleges_page

    client.get("/logout")
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    admin_response = client.get("/admin/my-plan")
    admin_page = admin_response.get_data(as_text=True)

    assert admin_response.status_code == 200
    assert "Custom Plan" in admin_page
    assert "Billing tier:" in admin_page
    assert "Professional" in admin_page


def test_expired_free_trial_blocks_feature_routes(app, client):
    with app.app_context():
        college = db.session.get(College, app.config["TEST_DATA"]["college_id"])
        assert college is not None
        college.plan = "free"
        college.plan_expires_at = utc_now_naive() - timedelta(days=1)
        for row in CollegeFeatureAccess.query.filter_by(college_id=college.id).all():
            row.enabled = True
        db.session.commit()

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/library/catalog")

    assert response.status_code == 403


def test_super_admin_can_open_college_detail_with_role_activity(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    college_id = app.config["TEST_DATA"]["college_id"]

    response = client.get(f"/super-admin/colleges/{college_id}")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Role Activity Summary" in page
    assert "College Admin Accounts" in page
    assert "College Setup Status" in page
    assert "Affiliation & Feature Access" in page
    assert "Enabled Modules" in page
    assert "Free for limited trial" in page
    assert "Rs. 2,999 / month" in page
    assert "Rs. 8,999 / month" in page


def test_admin_my_plan_page_shows_plan_prices(app, client):
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/admin/my-plan")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Free for limited trial" in page
    assert "Rs. 2,999 / month" in page
    assert "Rs. 5,999 / month" in page
    assert "Rs. 8,999 / month" in page
    assert "Custom pricing" in page


def test_super_admin_can_update_plan_pricing_labels(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/super-admin/plan-pricing",
        data={
            "price_free": "Free for 21 days",
            "price_starter": "Rs. 3,499 / month",
            "price_standard": "Rs. 6,499 / month",
            "price_professional": "Rs. 9,499 / month",
            "price_enterprise": "Contact sales",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Plan pricing updated." in response.data

    with app.app_context():
        starter = PlanPricing.query.filter_by(plan_key="starter").first()
        enterprise = PlanPricing.query.filter_by(plan_key="enterprise").first()
        assert starter is not None
        assert starter.price_label == "Rs. 3,499 / month"
        assert enterprise is not None
        assert enterprise.price_label == "Contact sales"

    detail_response = client.get(
        f"/super-admin/colleges/{app.config['TEST_DATA']['college_id']}"
    )
    detail_page = detail_response.get_data(as_text=True)
    assert "Free for 21 days" in detail_page
    assert "Rs. 3,499 / month" in detail_page
    assert "Contact sales" in detail_page

    client.get("/logout")
    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    admin_plan = client.get("/admin/my-plan")
    admin_page = admin_plan.get_data(as_text=True)
    assert "Free for 21 days" in admin_page
    assert "Rs. 3,499 / month" in admin_page
    assert "Rs. 6,499 / month" in admin_page
    assert "Rs. 9,499 / month" in admin_page
    assert "Contact sales" in admin_page


def test_super_admin_can_open_audit_logs_page(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/super-admin/audit-logs")

    assert response.status_code == 200
    assert b"Platform Audit Trail" in response.data


def test_super_admin_can_delete_read_platform_notifications(app, client):
    with app.app_context():
        user = User.query.filter_by(email="superadmin@example.com").first()
        assert user is not None
        user_id = user.id

        log = PlatformAuditLog(
            actor_user_id=user_id,
            college_id=app.config["TEST_DATA"]["college_id"],
            action_key="platform.demo_notice",
            target_type="college",
            target_id=app.config["TEST_DATA"]["college_id"],
            summary="Demo platform notification",
        )
        db.session.add(log)
        db.session.flush()
        db.session.add(PlatformAuditRead(audit_log_id=log.id, user_id=user_id))
        db.session.commit()
        log_id = log.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post("/super-admin/notifications/delete-read")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload["deleted_count"] >= 1

    with app.app_context():
        receipt = PlatformAuditRead.query.filter_by(
            audit_log_id=log_id, user_id=user_id
        ).first()
        assert receipt is not None
        assert receipt.dismissed_at is not None


def test_super_admin_can_open_plan_demo_page(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/super-admin/plan-demo")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "College Pricing & Module Demo" in page
    assert "Free Trial" in page
    assert "Starter" in page
    assert "Professional" in page
    assert "Enterprise" in page
    assert "Rs. 2,999 / month" in page
    assert "Library &amp; E-Library" in page
    assert "Feature Comparison" in page


def test_super_admin_can_export_audit_logs_csv(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    client.post(
        "/super-admin/colleges/create",
        data={
            "name": "Export College",
            "code": "EXPT",
            "subdomain": "export-college",
        },
        follow_redirects=True,
    )

    response = client.get("/super-admin/audit-logs/export")

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment; filename=" in response.headers["Content-Disposition"]
    body = response.get_data(as_text=True)
    assert "action_key,summary" in body
    assert "college.created" in body
    assert "Created college Export College [EXPT]" in body


def test_super_admin_can_delete_single_audit_log(app, client):
    with app.app_context():
        log = PlatformAuditLog(
            actor_user_id=app.config["TEST_DATA"]["super_admin_user_id"],
            college_id=app.config["TEST_DATA"]["college_id"],
            action_key="audit.test_delete_single",
            summary="Delete me",
            target_type="test",
            target_id=101,
        )
        db.session.add(log)
        db.session.commit()
        log_id = log.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/super-admin/audit-logs/{log_id}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert db.session.get(PlatformAuditLog, log_id) is None


def test_super_admin_can_delete_filtered_audit_logs(app, client):
    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        target_logs = [
            PlatformAuditLog(
                actor_user_id=app.config["TEST_DATA"]["super_admin_user_id"],
                college_id=college_id,
                action_key="audit.bulk_delete_target",
                summary="Delete target A",
            ),
            PlatformAuditLog(
                actor_user_id=app.config["TEST_DATA"]["super_admin_user_id"],
                college_id=college_id,
                action_key="audit.bulk_delete_target",
                summary="Delete target B",
            ),
            PlatformAuditLog(
                actor_user_id=app.config["TEST_DATA"]["super_admin_user_id"],
                college_id=college_id,
                action_key="audit.keep_me",
                summary="Keep me",
            ),
        ]
        db.session.add_all(target_logs)
        db.session.commit()

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/super-admin/audit-logs/delete-filtered",
        data={"action": "audit.bulk_delete_target"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        assert (
            PlatformAuditLog.query.filter_by(
                action_key="audit.bulk_delete_target"
            ).count()
            == 0
        )
        assert PlatformAuditLog.query.filter_by(action_key="audit.keep_me").count() == 1


def test_super_admin_can_delete_selected_audit_logs(app, client):
    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        logs = [
            PlatformAuditLog(
                actor_user_id=app.config["TEST_DATA"]["super_admin_user_id"],
                college_id=college_id,
                action_key="audit.selected_delete_target",
                summary="Delete selected A",
            ),
            PlatformAuditLog(
                actor_user_id=app.config["TEST_DATA"]["super_admin_user_id"],
                college_id=college_id,
                action_key="audit.selected_delete_target",
                summary="Delete selected B",
            ),
            PlatformAuditLog(
                actor_user_id=app.config["TEST_DATA"]["super_admin_user_id"],
                college_id=college_id,
                action_key="audit.selected_keep",
                summary="Keep selected",
            ),
        ]
        db.session.add_all(logs)
        db.session.commit()
        delete_ids = [logs[0].id, logs[1].id]
        keep_id = logs[2].id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/super-admin/audit-logs/delete-selected",
        data={
            "college_id": app.config["TEST_DATA"]["college_id"],
            "selected_log_ids": delete_ids,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Deleted 2 selected audit log entries." in response.data

    with app.app_context():
        assert db.session.get(PlatformAuditLog, delete_ids[0]) is None
        assert db.session.get(PlatformAuditLog, delete_ids[1]) is None
        assert db.session.get(PlatformAuditLog, keep_id) is not None


def test_super_admin_can_delete_selected_audit_logs_with_read_receipts(app, client):
    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        super_admin_user_id = app.config["TEST_DATA"]["super_admin_user_id"]
        logs = [
            PlatformAuditLog(
                actor_user_id=super_admin_user_id,
                college_id=college_id,
                action_key="audit.selected_delete_with_receipts",
                summary="Delete with receipt A",
            ),
            PlatformAuditLog(
                actor_user_id=super_admin_user_id,
                college_id=college_id,
                action_key="audit.selected_delete_with_receipts",
                summary="Delete with receipt B",
            ),
        ]
        db.session.add_all(logs)
        db.session.flush()
        db.session.add_all(
            [
                PlatformAuditRead(audit_log_id=logs[0].id, user_id=super_admin_user_id),
                PlatformAuditRead(audit_log_id=logs[1].id, user_id=super_admin_user_id),
            ]
        )
        db.session.commit()
        delete_ids = [logs[0].id, logs[1].id]

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/super-admin/audit-logs/delete-selected",
        data={
            "college_id": app.config["TEST_DATA"]["college_id"],
            "selected_log_ids": delete_ids,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Deleted 2 selected audit log entries." in response.data

    with app.app_context():
        assert (
            PlatformAuditRead.query.filter(
                PlatformAuditRead.audit_log_id.in_(delete_ids)
            ).count()
            == 0
        )
        assert db.session.get(PlatformAuditLog, delete_ids[0]) is None
        assert db.session.get(PlatformAuditLog, delete_ids[1]) is None


def test_super_admin_cannot_delete_selected_audit_logs_without_selection(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/super-admin/audit-logs/delete-selected",
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Select at least one audit log entry to delete." in response.data


def test_super_admin_cannot_bulk_delete_audit_logs_without_filters(app, client):
    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        "/super-admin/audit-logs/delete-filtered",
        data={},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert (
        b"Apply at least one filter before deleting audit logs in bulk."
        in response.data
    )


def test_super_admin_topbar_uses_platform_activity_instead_of_college_notices(
    app, client
):
    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        db.session.add(
            Notice(
                college_id=college_id,
                title="College Notice For Students",
                content="This should not appear in the super admin bell.",
                category="general",
                target_role="student",
                author_id=app.config["TEST_DATA"]["teacher_user_id"],
            )
        )
        db.session.commit()

    login(client, "superadmin@example.com")
    response = client.get("/super-admin/dashboard")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Platform Activity" in page
    assert "Open Audit" in page
    assert "Open Board" not in page
    assert "College Notice For Students" not in page


def test_super_admin_notifications_feed_returns_platform_audit_entries(app, client):
    login(client, "superadmin@example.com")
    client.post(
        "/super-admin/colleges/create",
        data={
            "name": "Zeta College",
            "code": "ZETA",
            "subdomain": "zeta",
        },
        follow_redirects=True,
    )

    response = client.get("/super-admin/notifications/feed")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["items"]
    assert any(
        "Created college Zeta College [ZETA]" in item["title"]
        for item in payload["items"]
    )


def test_super_admin_can_mark_platform_notifications_as_read(app, client):
    login(client, "superadmin@example.com")
    client.post(
        "/super-admin/colleges/create",
        data={
            "name": "Eta College",
            "code": "ETA",
            "subdomain": "eta",
        },
        follow_redirects=True,
    )

    response = client.post("/super-admin/notifications/mark-all-read")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 0
    assert payload["marked_count"] >= 1
    assert payload["items"]
    assert all(item["is_read"] is True for item in payload["items"])


def test_super_admin_can_delete_read_platform_notifications_from_tray(app, client):
    login(client, "superadmin@example.com")
    client.post(
        "/super-admin/colleges/create",
        data={
            "name": "Theta College",
            "code": "THETA",
            "subdomain": "theta",
        },
        follow_redirects=True,
    )
    client.post("/super-admin/notifications/mark-all-read")

    response = client.post("/super-admin/notifications/delete-read")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["deleted_count"] >= 1


def test_super_admin_notification_dropdown_has_platform_controls_and_scroll_list(
    app, client
):
    login(client, "superadmin@example.com")
    response = client.get("/super-admin/dashboard")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Platform Activity" in page
    assert "topbarDeleteReadButton" in page
    assert "topbarMarkReadButton" in page
    assert "topbar-notice-list" in page


def test_super_admin_can_toggle_college_admin_status(app, client):
    with app.app_context():
        college = College(name="Beta College", code="BETA")
        db.session.add(college)
        db.session.flush()
        beta_admin = User(
            college_id=college.id,
            name="Beta Admin",
            email="beta.admin@example.com",
            role="admin",
            is_active=True,
        )
        beta_admin.set_password("Password@123")
        db.session.add(beta_admin)
        backup_admin = User(
            college_id=college.id,
            name="Beta Backup",
            email="beta.backup@example.com",
            role="admin",
            is_active=True,
        )
        backup_admin.set_password("Password@123")
        db.session.add(backup_admin)
        db.session.commit()
        college_id = college.id
        admin_id = beta_admin.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/super-admin/colleges/{college_id}/admins/{admin_id}/toggle",
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        beta_admin = db.session.get(User, admin_id)
        assert beta_admin is not None
        assert beta_admin.is_active is False
        log = (
            PlatformAuditLog.query.filter_by(
                action_key="college_admin.toggled",
                college_id=college_id,
                target_id=admin_id,
            )
            .order_by(PlatformAuditLog.created_at.desc())
            .first()
        )
        assert log is not None


def test_super_admin_can_reset_college_admin_password(app, client):
    with app.app_context():
        college = College(name="Gamma College", code="GAMMA")
        db.session.add(college)
        db.session.flush()
        gamma_admin = User(
            college_id=college.id,
            name="Gamma Admin",
            email="gamma.admin@example.com",
            role="admin",
            is_active=True,
        )
        gamma_admin.set_password("Password@123")
        db.session.add(gamma_admin)
        db.session.commit()
        college_id = college.id
        admin_id = gamma_admin.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/super-admin/colleges/{college_id}/admins/{admin_id}/reset-password",
        data={"new_password": "NewStrong@123"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        gamma_admin = db.session.get(User, admin_id)
        assert gamma_admin is not None
        assert gamma_admin.check_password("NewStrong@123") is True
        log = (
            PlatformAuditLog.query.filter_by(
                action_key="college_admin.password_reset",
                college_id=college_id,
                target_id=admin_id,
            )
            .order_by(PlatformAuditLog.created_at.desc())
            .first()
        )
        assert log is not None


def test_super_admin_cannot_delete_last_active_admin_of_active_college(app, client):
    with app.app_context():
        college = College(name="Delta College", code="DELTA")
        db.session.add(college)
        db.session.flush()
        delta_admin = User(
            college_id=college.id,
            name="Delta Admin",
            email="delta.admin@example.com",
            role="admin",
            is_active=True,
        )
        delta_admin.set_password("Password@123")
        db.session.add(delta_admin)
        db.session.commit()
        college_id = college.id
        admin_id = delta_admin.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/super-admin/colleges/{college_id}/admins/{admin_id}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        delta_admin = db.session.get(User, admin_id)
        assert delta_admin is not None


def test_super_admin_deleting_college_admin_creates_audit_log(app, client):
    with app.app_context():
        college = College(name="Epsilon College", code="EPSILON")
        db.session.add(college)
        db.session.flush()
        first_admin = User(
            college_id=college.id,
            name="Epsilon Admin One",
            email="epsilon.one@example.com",
            role="admin",
            is_active=True,
        )
        first_admin.set_password("Password@123")
        second_admin = User(
            college_id=college.id,
            name="Epsilon Admin Two",
            email="epsilon.two@example.com",
            role="admin",
            is_active=True,
        )
        second_admin.set_password("Password@123")
        db.session.add_all([first_admin, second_admin])
        db.session.commit()
        college_id = college.id
        admin_id = second_admin.id

    login(
        client,
        "superadmin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.post(
        f"/super-admin/colleges/{college_id}/admins/{admin_id}/delete",
        follow_redirects=True,
    )

    assert response.status_code == 200
    with app.app_context():
        deleted_admin = db.session.get(User, admin_id)
        assert deleted_admin is None
        log = (
            PlatformAuditLog.query.filter_by(
                action_key="college_admin.deleted",
                college_id=college_id,
                target_id=admin_id,
            )
            .order_by(PlatformAuditLog.created_at.desc())
            .first()
        )
        assert log is not None


def test_disabled_feature_is_hidden_and_blocked_for_admin(app, client):
    with app.app_context():
        db.session.add(
            CollegeFeatureAccess(
                college_id=app.config["TEST_DATA"]["college_id"],
                feature_key="fees",
                enabled=False,
            )
        )
        db.session.commit()

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    dashboard = client.get("/admin/dashboard")
    page = dashboard.get_data(as_text=True)

    assert dashboard.status_code == 200
    assert 'data-nav-group="more" data-nav-key="fees"' not in page

    blocked = client.get("/admin/fees")
    assert blocked.status_code == 403


def test_disabled_notices_hide_bell_and_block_notice_board(app, client):
    with app.app_context():
        db.session.add(
            CollegeFeatureAccess(
                college_id=app.config["TEST_DATA"]["college_id"],
                feature_key="notices",
                enabled=False,
            )
        )
        # Disable library feature as well, since the bell button is rendered if either notices or library is enabled
        db.session.add(
            CollegeFeatureAccess(
                college_id=app.config["TEST_DATA"]["college_id"],
                feature_key="library",
                enabled=False,
            )
        )
        db.session.commit()

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    dashboard = client.get("/student/dashboard")
    page = dashboard.get_data(as_text=True)

    assert dashboard.status_code == 200
    assert "topbarBellButton" not in page
    assert 'data-nav-group="quick" data-nav-key="notice_board"' not in page

    blocked = client.get("/notices")
    assert blocked.status_code == 403


def test_parent_can_open_linked_child_marksheet(app, client):
    login(
        client,
        "parent1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    student_id = app.config["TEST_DATA"]["student_profile_id"]

    response = client.get("/parent/marksheets")
    assert response.status_code == 200
    assert b"View Full Marksheet" in response.data

    child_response = client.get(f"/parent/marksheet/{student_id}")
    assert child_response.status_code == 200
    assert b"Child Marksheet" in child_response.data


def test_admin_id_card_list_hides_other_college_requests(app, client):
    with app.app_context():
        other_college = College(name="Beta College", code="BETA")
        db.session.add(other_college)
        db.session.flush()

        other_dept = Department(
            college_id=other_college.id, name="Management", code="BBA"
        )
        db.session.add(other_dept)
        db.session.flush()

        other_user = User(
            college_id=other_college.id,
            name="Beta Student",
            email="beta.student@example.com",
            role="student",
        )
        other_user.set_password("Password@123")
        db.session.add(other_user)
        db.session.flush()

        other_student = Student(
            college_id=other_college.id,
            user_id=other_user.id,
            roll_number="BETA-001",
            department_id=other_dept.id,
            semester=1,
        )
        db.session.add(other_student)
        db.session.flush()

        db.session.add(
            StudentIDCard(
                college_id=other_college.id,
                student_id=other_student.id,
                status="pending",
            )
        )
        db.session.commit()

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/admin/id-cards")

    assert response.status_code == 200
    assert b"Beta Student" not in response.data
    assert b"BETA-001" not in response.data


def test_admin_cannot_view_another_college_id_card(app, client):
    with app.app_context():
        other_college = College(name="Gamma College", code="GAMMA")
        db.session.add(other_college)
        db.session.flush()

        other_dept = Department(college_id=other_college.id, name="Science", code="SCI")
        db.session.add(other_dept)
        db.session.flush()

        other_user = User(
            college_id=other_college.id,
            name="Gamma Student",
            email="gamma.student@example.com",
            role="student",
        )
        other_user.set_password("Password@123")
        db.session.add(other_user)
        db.session.flush()

        other_student = Student(
            college_id=other_college.id,
            user_id=other_user.id,
            roll_number="SCI-001",
            department_id=other_dept.id,
            semester=1,
        )
        db.session.add(other_student)
        db.session.flush()

        other_card = StudentIDCard(
            college_id=other_college.id,
            student_id=other_student.id,
            status="pending",
        )
        db.session.add(other_card)
        db.session.commit()
        foreign_card_id = other_card.id

    login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get(f"/admin/id-cards/{foreign_card_id}/view")

    assert response.status_code == 404


def test_id_card_template_assets_are_saved_per_college(app, client):
    with app.app_context():
        other_college = College(name="Delta College", code="DELTA")
        db.session.add(other_college)
        db.session.flush()

        other_admin = User(
            college_id=other_college.id,
            name="Delta Admin",
            email="delta.admin@example.com",
            role="admin",
        )
        other_admin.set_password("Password@123")
        db.session.add(other_admin)
        db.session.commit()

    first_login = login(
        client,
        "admin@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    assert first_login.status_code == 302
    first_response = client.post(
        "/admin/id-card-template",
        data={
            "principal_name": "Alpha Principal",
            "principal_title": "Principal",
            "logo": (io.BytesIO(b"alpha-logo"), "alpha.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert first_response.status_code == 200

    client.get("/logout", follow_redirects=True)
    second_login = login(client, "delta.admin@example.com", college_code="DELTA")
    assert second_login.status_code == 302
    second_response = client.post(
        "/admin/id-card-template",
        data={
            "principal_name": "Delta Principal",
            "principal_title": "Principal",
            "logo": (io.BytesIO(b"delta-logo"), "delta.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert second_response.status_code == 200

    with app.app_context():
        alpha_template = (
            IDCardTemplate.query.join(College)
            .filter(College.code == app.config["TEST_DATA"]["college_code"])
            .first()
        )
        delta_template = (
            IDCardTemplate.query.join(College).filter(College.code == "DELTA").first()
        )

        assert alpha_template.logo_path != delta_template.logo_path
        assert alpha_template.logo_path.endswith("/logo.png")
        assert delta_template.logo_path.endswith("/logo.png")
        assert "/alpha/" in alpha_template.logo_path
        assert "/delta/" in delta_template.logo_path


def test_leave_reference_numbers_are_scoped_by_college_code(app):
    with app.app_context():
        alpha = db.session.get(College, app.config["TEST_DATA"]["college_id"])
        beta = College(name="Beta College", code="BETA")
        db.session.add(beta)
        db.session.commit()

        alpha_ref = LeaveRequest.generate_ref(alpha)
        beta_ref = LeaveRequest.generate_ref(beta)

        assert alpha_ref.startswith("LV-ALPHA-")
        assert beta_ref.startswith("LV-BETA-")


def test_same_id_card_number_can_exist_in_different_colleges(app):
    with app.app_context():
        alpha_student_id = app.config["TEST_DATA"]["student_profile_id"]
        alpha_college_id = app.config["TEST_DATA"]["college_id"]

        alpha_card = StudentIDCard(
            college_id=alpha_college_id,
            student_id=alpha_student_id,
            card_number="SHARED-CARD-001",
            status="approved",
        )
        db.session.add(alpha_card)
        db.session.flush()

        beta = College(name="Beta College", code="BETA")
        db.session.add(beta)
        db.session.flush()

        beta_dept = Department(college_id=beta.id, name="Business", code="BBA")
        db.session.add(beta_dept)
        db.session.flush()

        beta_user = User(
            college_id=beta.id,
            name="Beta Student",
            email="beta.card@example.com",
            role="student",
        )
        beta_user.set_password("Password@123")
        db.session.add(beta_user)
        db.session.flush()

        beta_student = Student(
            college_id=beta.id,
            user_id=beta_user.id,
            roll_number="BBA-001",
            department_id=beta_dept.id,
            semester=1,
        )
        db.session.add(beta_student)
        db.session.flush()

        beta_card = StudentIDCard(
            college_id=beta.id,
            student_id=beta_student.id,
            card_number="SHARED-CARD-001",
            status="approved",
        )
        db.session.add(beta_card)
        db.session.commit()

        assert beta_card.id is not None


def test_same_fee_receipt_number_can_exist_in_different_colleges(app):
    with app.app_context():
        alpha_student = db.session.get(
            Student, app.config["TEST_DATA"]["student_profile_id"]
        )
        alpha_structure = FeeStructure(
            college_id=alpha_student.college_id,
            title="Alpha Fee",
            department_id=alpha_student.department_id,
            semester=alpha_student.semester,
            academic_year="2026-27",
            amount=1000,
        )
        db.session.add(alpha_structure)
        db.session.flush()

        alpha_payment = FeePayment(
            college_id=alpha_student.college_id,
            student_id=alpha_student.id,
            fee_structure_id=alpha_structure.id,
            amount_paid=1000,
            receipt_no="RCT-SHARED-001",
        )
        db.session.add(alpha_payment)
        db.session.flush()

        beta = College(name="Gamma College", code="GAMMA")
        db.session.add(beta)
        db.session.flush()

        beta_dept = Department(college_id=beta.id, name="Science", code="SCI")
        db.session.add(beta_dept)
        db.session.flush()

        beta_user = User(
            college_id=beta.id,
            name="Gamma Student",
            email="gamma.fee@example.com",
            role="student",
        )
        beta_user.set_password("Password@123")
        db.session.add(beta_user)
        db.session.flush()

        beta_student = Student(
            college_id=beta.id,
            user_id=beta_user.id,
            roll_number="SCI-201",
            department_id=beta_dept.id,
            semester=1,
        )
        db.session.add(beta_student)
        db.session.flush()

        beta_structure = FeeStructure(
            college_id=beta.id,
            title="Gamma Fee",
            department_id=beta_dept.id,
            semester=1,
            academic_year="2026-27",
            amount=1200,
        )
        db.session.add(beta_structure)
        db.session.flush()

        beta_payment = FeePayment(
            college_id=beta.id,
            student_id=beta_student.id,
            fee_structure_id=beta_structure.id,
            amount_paid=1200,
            receipt_no="RCT-SHARED-001",
        )
        db.session.add(beta_payment)
        db.session.commit()

        assert beta_payment.id is not None


def test_student_sidebar_uses_quick_access_and_more_tools(app, client):
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.get("/student/dashboard")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Quick Access" in page
    assert "More Tools" in page
    assert 'data-nav-group="quick" data-nav-key="dashboard"' in page
    assert 'data-nav-group="more" data-nav-key="academic_calendar"' in page


def test_user_can_pin_optional_sidebar_tool(app, client):
    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )

    response = client.post(
        "/preferences/sidebar",
        data={"pinned_features": ["academic_calendar"]},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Quick access updated." in page
    assert 'data-nav-group="quick" data-nav-key="academic_calendar"' in page
    assert 'data-nav-group="more" data-nav-key="academic_calendar"' not in page

    with app.app_context():
        student_user = User.query.filter_by(email="student1@example.com").first()
        assert student_user.get_sidebar_pin_keys() == ["academic_calendar"]


def test_user_can_directly_unpin_sidebar_tool(app, client):
    with app.app_context():
        student_user = User.query.filter_by(email="student1@example.com").first()
        student_user.set_sidebar_pin_keys(["academic_calendar"])
        db.session.commit()

    login(client, "student1@example.com")
    response = client.post(
        "/preferences/sidebar/toggle",
        data={"feature_key": "academic_calendar"},
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'data-nav-group="quick" data-nav-key="academic_calendar"' not in page
    assert 'data-nav-group="more" data-nav-key="academic_calendar"' in page

    with app.app_context():
        student_user = User.query.filter_by(email="student1@example.com").first()
        assert student_user.get_sidebar_pin_keys() == []


def test_user_can_enable_optional_dashboard_widget(app, client):
    login(client, "student1@example.com")

    before = client.get("/student/dashboard")
    before_page = before.get_data(as_text=True)
    assert before.status_code == 200
    assert "Live Location Sharing" not in before_page

    after = client.post(
        "/preferences/dashboard",
        data={"dashboard_widgets": ["location_sharing"]},
        follow_redirects=True,
    )
    after_page = after.get_data(as_text=True)

    assert after.status_code == 200
    assert "Dashboard widgets updated." in after_page
    assert "Live Location Sharing" in after_page

    with app.app_context():
        student_user = User.query.filter_by(email="student1@example.com").first()
        assert student_user.get_dashboard_widget_keys() == ["location_sharing"]


def test_dashboard_widget_order_is_saved_in_request_order(app, client):
    login(client, "student1@example.com")

    response = client.post(
        "/preferences/dashboard",
        data={"dashboard_widgets": ["notices", "location_sharing", "fee_status"]},
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        student_user = User.query.filter_by(email="student1@example.com").first()
        assert student_user.get_dashboard_widget_keys() == [
            "notices",
            "location_sharing",
            "fee_status",
        ]


def test_student_calendar_shows_matching_semester_events_only(app, client):
    college_id = app.config["TEST_DATA"]["college_id"]
    with app.app_context():
        db.session.add_all(
            [
                AcademicCalendarEvent(
                    college_id=college_id,
                    title="Semester 1 Orientation",
                    category="event",
                    start_date=date(2026, 5, 4),
                    end_date=date(2026, 5, 4),
                    department_id=1,
                    semester=1,
                ),
                AcademicCalendarEvent(
                    college_id=college_id,
                    title="Semester 2 Only Event",
                    category="event",
                    start_date=date(2026, 5, 5),
                    end_date=date(2026, 5, 5),
                    department_id=1,
                    semester=2,
                ),
            ]
        )
        db.session.commit()

    login(client, "student1@example.com")
    response = client.get("/calendar?year=2026&month=5")

    assert response.status_code == 200
    assert b"Semester 1 Orientation" in response.data
    assert b"Semester 2 Only Event" not in response.data


def test_parent_calendar_uses_linked_child_scope(app, client):
    college_id = app.config["TEST_DATA"]["college_id"]
    with app.app_context():
        db.session.add_all(
            [
                AcademicCalendarEvent(
                    college_id=college_id,
                    title="Parent Visible Holiday",
                    category="holiday",
                    start_date=date(2026, 5, 6),
                    end_date=date(2026, 5, 6),
                    department_id=1,
                    semester=1,
                ),
                AcademicCalendarEvent(
                    college_id=college_id,
                    title="Hidden Semester Event",
                    category="event",
                    start_date=date(2026, 5, 7),
                    end_date=date(2026, 5, 7),
                    department_id=1,
                    semester=3,
                ),
            ]
        )
        db.session.commit()

    login(
        client,
        "parent1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/calendar?year=2026&month=5")

    assert response.status_code == 200
    assert b"Parent Visible Holiday" in response.data
    assert b"Hidden Semester Event" not in response.data


def test_student_can_submit_assignment(app, client):
    login(client, "student1@example.com")
    assignment_id = app.config["TEST_DATA"]["assignment_id"]

    response = client.post(
        f"/student/assignments/{assignment_id}/submit",
        data={
            "submission_text": "Completed all questions.",
            "submission_file": (io.BytesIO(b'print("done")\n'), "solution.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Assignment submitted successfully" in response.data

    with app.app_context():
        submission = AssignmentSubmission.query.filter_by(
            content_id=assignment_id
        ).first()
        assert submission is not None
        assert submission.submission_text == "Completed all questions."
        assert submission.status == "submitted"
        assert submission.file_path.endswith(".txt")


def test_teacher_can_review_assignment_submission(app, client):
    assignment_id = app.config["TEST_DATA"]["assignment_id"]
    student_id = app.config["TEST_DATA"]["student_profile_id"]

    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        submission = AssignmentSubmission(
            college_id=college_id,
            content_id=assignment_id,
            student_id=student_id,
            submission_text="My first draft",
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    login(client, "teacher1@example.com")
    response = client.post(
        f"/teacher/assignments/submissions/{submission_id}/grade",
        data={
            "marks_awarded": "18",
            "feedback": "Clear work. Improve the final explanation.",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Review saved for Student One." in response.data

    with app.app_context():
        submission = db.session.get(AssignmentSubmission, submission_id)
        assert submission.status == "reviewed"
        assert submission.marks_awarded == 18
        assert submission.feedback == "Clear work. Improve the final explanation."


def test_parent_can_view_child_assignment_results(app, client):
    assignment_id = app.config["TEST_DATA"]["assignment_id"]
    student_id = app.config["TEST_DATA"]["student_profile_id"]

    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        submission = AssignmentSubmission(
            college_id=college_id,
            content_id=assignment_id,
            student_id=student_id,
            submission_text="Submitted from test fixture",
            status="reviewed",
            marks_awarded=17,
            feedback="Good effort",
        )
        db.session.add(submission)
        db.session.commit()

    login(
        client,
        "parent1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get(f"/parent/assignments?child_id={student_id}")

    assert response.status_code == 200
    assert b"Week 1 Assignment" in response.data
    assert b"Reviewed" in response.data
    assert b"17/20" in response.data


def test_teacher_can_preview_student_submission(app, client):
    assignment_id = app.config["TEST_DATA"]["assignment_id"]
    student_id = app.config["TEST_DATA"]["student_profile_id"]

    with app.app_context():
        college_id = app.config["TEST_DATA"]["college_id"]
        submission = AssignmentSubmission(
            college_id=college_id,
            content_id=assignment_id,
            student_id=student_id,
            submission_text="Preview this submission in the app.",
            file_path="uploads/submissions/preview.txt",
        )
        db.session.add(submission)
        db.session.commit()
        submission_id = submission.id

    abs_path = os.path.join(app.config["ASSIGNMENT_UPLOAD_FOLDER"], "preview.txt")
    with open(abs_path, "w", encoding="utf-8") as handle:
        handle.write("student preview file body")

    login(client, "teacher1@example.com")
    response = client.get(f"/teacher/assignments/submissions/{submission_id}/preview")

    assert response.status_code == 200
    assert b"Student Submission Preview" in response.data
    assert b"Preview this submission in the app." in response.data
    assert b"student preview file body" in response.data


def test_teacher_can_save_and_open_next_unreviewed_submission(app, client):
    assignment_id = app.config["TEST_DATA"]["assignment_id"]
    first_student_id = app.config["TEST_DATA"]["student_profile_id"]

    with app.app_context():
        first_student = db.session.get(Student, first_student_id)
        second_user = User(
            college_id=first_student.college_id,
            name="Student Two",
            email="student2@example.com",
            role="student",
        )
        second_user.set_password("Password@123")
        db.session.add(second_user)
        db.session.flush()
        second_student = Student(
            college_id=first_student.college_id,
            user_id=second_user.id,
            roll_number="CS-002",
            department_id=first_student.department_id,
            semester=first_student.semester,
        )
        db.session.add(second_student)
        db.session.flush()

        first_submission = AssignmentSubmission(
            college_id=first_student.college_id,
            content_id=assignment_id,
            student_id=first_student_id,
            submission_text="First submission in queue",
        )
        second_submission = AssignmentSubmission(
            college_id=second_student.college_id,
            content_id=assignment_id,
            student_id=second_student.id,
            submission_text="Second submission in queue",
        )
        db.session.add_all([first_submission, second_submission])
        db.session.commit()
        first_submission_id = first_submission.id
        second_submission_id = second_submission.id

    login(client, "teacher1@example.com")
    response = client.post(
        f"/teacher/assignments/submissions/{first_submission_id}/grade",
        data={
            "return_to_preview": "1",
            "next_submission_id": str(second_submission_id),
            "go_next": "1",
            "marks_awarded": "19",
            "feedback": "Reviewed quickly",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Opening the next unreviewed submission" in response.data
    assert b"Student Two" in response.data
    assert b"Second submission in queue" in response.data

    with app.app_context():
        first_submission = db.session.get(AssignmentSubmission, first_submission_id)
        assert first_submission.status == "reviewed"
        assert first_submission.marks_awarded == 19


def test_notice_feed_returns_role_visible_items(app, client):
    college_id = app.config["TEST_DATA"]["college_id"]
    with app.app_context():
        student_notice = Notice(
            college_id=college_id,
            title="Student Alert",
            content="Visible in the live bell feed.",
            category="urgent",
            target_role="student",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        teacher_notice = Notice(
            college_id=college_id,
            title="Teacher Alert",
            content="Should stay hidden from students.",
            category="general",
            target_role="teacher",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        db.session.add_all([student_notice, teacher_notice])
        db.session.commit()

    login(client, "student1@example.com")
    response = client.get("/notices/feed")

    assert response.status_code == 200
    payload = response.get_json()
    titles = {item["title"] for item in payload["items"]}
    assert "Student Alert" in titles
    assert "Teacher Alert" not in titles


def test_opening_notice_marks_notification_as_read(app, client):
    college_id = app.config["TEST_DATA"]["college_id"]
    with app.app_context():
        notice = Notice(
            college_id=college_id,
            title="Read Me",
            content="This should be marked read after opening.",
            category="general",
            target_role="student",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        db.session.add(notice)
        db.session.commit()
        notice_id = notice.id

    login(client, "student1@example.com")

    before = client.get("/notices/feed")
    assert before.status_code == 200
    before_payload = before.get_json()
    assert any(
        item["id"] == f"notice:{notice_id}" and item["is_read"] is False
        for item in before_payload["items"]
    )
    unread_before = before_payload["count"]

    detail = client.get(f"/notices/{notice_id}")
    assert detail.status_code == 200

    after = client.get("/notices/feed")
    assert after.status_code == 200
    after_payload = after.get_json()
    assert any(
        item["id"] == f"notice:{notice_id}" and item["is_read"] is True
        for item in after_payload["items"]
    )
    assert after_payload["count"] == max(unread_before - 1, 0)

    with app.app_context():
        receipt = NoticeRead.query.filter_by(
            notice_id=notice_id,
            user_id=app.config["TEST_DATA"]["student_user_id"],
        ).first()
        assert receipt is not None


def test_mark_all_notifications_as_read_from_bell(app, client):
    college_id = app.config["TEST_DATA"]["college_id"]
    with app.app_context():
        first_notice = Notice(
            college_id=college_id,
            title="Bell First",
            content="First unread bell item.",
            category="general",
            target_role="student",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        second_notice = Notice(
            college_id=college_id,
            title="Bell Second",
            content="Second unread bell item.",
            category="urgent",
            target_role="student",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        db.session.add_all([first_notice, second_notice])
        db.session.commit()
        first_id = first_notice.id
        second_id = second_notice.id

    login(client, "student1@example.com")
    response = client.post(
        "/notices/mark-all-read",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["count"] == 0
    assert any(
        item["id"] == f"notice:{first_id}" and item["is_read"] is True
        for item in payload["items"]
    )
    assert any(
        item["id"] == f"notice:{second_id}" and item["is_read"] is True
        for item in payload["items"]
    )

    with app.app_context():
        receipts = NoticeRead.query.filter(
            NoticeRead.user_id == app.config["TEST_DATA"]["student_user_id"],
            NoticeRead.notice_id.in_([first_id, second_id]),
        ).all()
        assert len(receipts) == 2


def test_delete_read_notifications_removes_them_from_bell_only(app, client):
    college_id = app.config["TEST_DATA"]["college_id"]
    with app.app_context():
        notice = Notice(
            college_id=college_id,
            title="Delete From Tray",
            content="This read notice should disappear from the bell only.",
            category="general",
            target_role="student",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        db.session.add(notice)
        db.session.commit()
        notice_id = notice.id

    login(client, "student1@example.com")
    client.get(f"/notices/{notice_id}")

    response = client.post(
        "/notices/delete-read",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert all(item["id"] != f"notice:{notice_id}" for item in payload["items"])

    with app.app_context():
        receipt = NoticeRead.query.filter_by(
            notice_id=notice_id,
            user_id=app.config["TEST_DATA"]["student_user_id"],
        ).first()
        assert receipt is not None
        assert receipt.dismissed_at is not None

        stored_notice = db.session.get(Notice, notice_id)
        assert stored_notice is not None


def test_admin_file_manager_lists_legacy_file_and_previews_in_app(app, client):
    legacy_dir = os.path.join(app.root_path, "static", "uploads", "content")
    os.makedirs(legacy_dir, exist_ok=True)
    filename = "legacy-preview.txt"
    abs_path = os.path.join(legacy_dir, filename)

    with open(abs_path, "w", encoding="utf-8") as handle:
        handle.write("legacy file preview body")

    try:
        login(client, "admin@example.com")

        listing = client.get("/admin/files")
        assert listing.status_code == 200
        assert b"legacy-preview.txt" in listing.data

        preview = client.get(f"/admin/files/preview?rel=uploads/content/{filename}")
        assert preview.status_code == 200
        assert b"legacy file preview body" in preview.data
    finally:
        if os.path.exists(abs_path):
            os.remove(abs_path)


def test_login_requires_college_code_when_multiple_colleges_exist(app, client):
    with app.app_context():
        from models import College

        db.session.add(College(name="Beta College", code="BETA"))
        db.session.commit()

    response = client.post(
        "/login",
        data={"email": "student1@example.com", "password": "Password@123"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Enter a valid college code to continue." in response.data

    success = client.post(
        "/login",
        data={
            "college_code": app.config["TEST_DATA"]["college_code"],
            "email": "student1@example.com",
            "password": "Password@123",
        },
        follow_redirects=False,
    )

    assert success.status_code == 302
    assert "/student/dashboard" in success.headers["Location"]


def test_super_admin_can_login_without_college_code(app, client):
    response = client.post(
        "/login",
        data={
            "email": "superadmin@example.com",
            "password": "Password@123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/super-admin/dashboard" in response.headers["Location"]


def test_super_admin_account_is_not_bound_to_a_college(app):
    with app.app_context():
        user = User.query.filter_by(
            email="superadmin@example.com", role="super_admin"
        ).first()

    assert user is not None
    assert user.college_id is None


def test_super_admin_can_login_with_college_code_even_when_not_college_scoped(
    app, client
):
    response = client.post(
        "/login",
        data={
            "college_code": app.config["TEST_DATA"]["college_code"],
            "email": "superadmin@example.com",
            "password": "Password@123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/super-admin/dashboard" in response.headers["Location"]


def test_private_lan_login_page_redirects_to_public_https_url(app, client):
    with app.app_context():
        app.config["PUBLIC_BASE_URL"] = "https://portal.smartattend.test"

    response = client.get(
        "/login",
        base_url="http://192.168.1.81:8081",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "https://portal.smartattend.test/login"


def test_prepare_production_bundle_renders_real_deployment_files(app, tmp_path):
    base_dir = Path(app.root_path)
    output_dir = tmp_path / "deploy_bundle"

    written = write_deployment_bundle(
        output_dir,
        env_example_text=(base_dir / ".env.example").read_text(encoding="utf-8"),
        nginx_template_text=(base_dir / "deploy/nginx/smart_attendance.conf").read_text(
            encoding="utf-8"
        ),
        service_template_text=(
            base_dir / "deploy/systemd/smart_attendance.service"
        ).read_text(encoding="utf-8"),
        service_instance_template_text=(
            base_dir / "deploy/systemd/smart_attendance@.service"
        ).read_text(encoding="utf-8"),
        public_host="portal.smartattend.test",
        root_domain="smartattend.test",
        app_root="/srv/smart_attendance",
        service_user="smartattend",
        service_group="smartattend",
        db_name="smartattend_prod",
    )

    names = {path.name for path in written}
    assert ".env.production" in names
    assert "smart_attendance.conf" in names
    assert "smart_attendance.service" in names
    assert "smart_attendance@.service" in names
    assert "DEPLOYMENT.md" in names

    env_text = (output_dir / ".env.production").read_text(encoding="utf-8")
    assert "PUBLIC_BASE_URL=https://portal.smartattend.test" in env_text
    assert "MULTI_COLLEGE_ROOT_DOMAIN=smartattend.test" in env_text
    assert "DB_NAME=smartattend_prod" in env_text
    assert "PRIVATE_UPLOAD_FOLDER=/srv/smart_attendance/shared/uploads" in env_text

    nginx_text = (output_dir / "smart_attendance.conf").read_text(encoding="utf-8")
    assert "server_name portal.smartattend.test *.smartattend.test;" in nginx_text
    assert "alias /srv/smart_attendance/current/static/;" in nginx_text

    service_text = (output_dir / "smart_attendance.service").read_text(encoding="utf-8")
    assert "User=smartattend" in service_text
    assert "Group=smartattend" in service_text
    assert "WorkingDirectory=/srv/smart_attendance/current" in service_text

    readme_text = (output_dir / "DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "portal.smartattend.test" in readme_text
    assert "/srv/smart_attendance" in readme_text


def test_student_dashboard_hides_other_college_notice(app, client):
    with app.app_context():
        from models import College

        other_college = College(name="Beta College", code="BETA")
        db.session.add(other_college)
        db.session.flush()

        foreign_notice = Notice(
            college_id=other_college.id,
            title="Foreign College Notice",
            content="Should not appear on Alpha student dashboard.",
            category="general",
            target_role="student",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        db.session.add(foreign_notice)
        db.session.commit()

    login(
        client,
        "student1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/student/dashboard")

    assert response.status_code == 200
    assert b"Foreign College Notice" not in response.data


def test_parent_dashboard_hides_other_college_notice(app, client):
    with app.app_context():
        from models import College

        other_college = College(name="Gamma College", code="GAMMA")
        db.session.add(other_college)
        db.session.flush()

        foreign_notice = Notice(
            college_id=other_college.id,
            title="Gamma Parent Alert",
            content="Should not appear for Alpha parent users.",
            category="general",
            target_role="student",
            author_id=app.config["TEST_DATA"]["teacher_user_id"],
        )
        db.session.add(foreign_notice)
        db.session.commit()

    login(
        client,
        "parent1@example.com",
        college_code=app.config["TEST_DATA"]["college_code"],
    )
    response = client.get("/parent/dashboard")

    assert response.status_code == 200
    assert b"Gamma Parent Alert" not in response.data
