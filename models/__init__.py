from extensions import db
from models.college import College
from models.college_feature import CollegeFeatureAccess
from models.user import User
from models.department import Department
from models.student import Student
from models.teacher import Teacher
from models.subject import Subject
from models.attendance import AttendanceSession, AttendanceRecord
from models.leave import LeaveRequest
from models.notice import Notice
from models.notice_read import NoticeRead
from models.timetable import TimetableSlot
from models.exam import Exam, Mark
from models.fee import FeeStructure, FeePayment
from models.parent import ParentStudent, TeacherStatus, ClassAlert
from models.location import StudentLocation
from models.setting import CollegeSetting
from models.id_card import IDCardTemplate, StudentIDCard
from models.marksheet_signature import MarksheetSignature
from models.academic_calendar import AcademicCalendarEvent
from models.assignment import AssignmentSubmission
from models.platform_audit import PlatformAuditLog
from models.platform_audit_read import PlatformAuditRead
from models.sub_admin import SubAdminPermission
from models.classroom import Classroom, ClassroomBooking
