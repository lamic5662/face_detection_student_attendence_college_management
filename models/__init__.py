# ruff: noqa: F401

from extensions import db
from models.academic_calendar import AcademicCalendarEvent
from models.assignment import AssignmentSubmission
from models.attendance import AttendanceRecord, AttendanceSession
from models.classroom import Classroom, ClassroomBooking
from models.college import College
from models.college_feature import CollegeFeatureAccess
from models.department import Department
from models.exam import Exam, Mark
from models.fee import FeePayment, FeeStructure
from models.id_card import IDCardTemplate, StudentIDCard
from models.leave import LeaveRequest
from models.library import (
    LibraryAccessLog,
    LibraryBook,
    LibraryBookCopy,
    LibraryCategory,
    LibraryFine,
    LibraryLoan,
    LibraryLocation,
    LibraryReadingProgress,
    LibraryReservation,
    LibraryRule,
)
from models.location import StudentLocation
from models.marksheet_signature import MarksheetSignature
from models.notice import Notice
from models.notice_read import NoticeRead
from models.parent import ClassAlert, ParentStudent, TeacherStatus
from models.plan_pricing import PlanPricing
from models.platform_audit import PlatformAuditLog
from models.platform_audit_read import PlatformAuditRead
from models.setting import CollegeSetting
from models.student import Student
from models.sub_admin import SubAdminPermission
from models.subject import Subject
from models.teacher import Teacher
from models.timetable import TimetableSlot
from models.university import University
from models.user import User
from models.user_notification import UserNotification
