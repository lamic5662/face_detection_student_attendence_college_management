import pandas as pd
import io
from models.attendance import AttendanceSession, AttendanceRecord
from models.student import Student
from models.user import User
from models.subject import Subject


def generate_session_report(session_id: int) -> pd.DataFrame:
    session = AttendanceSession.query.get_or_404(session_id)
    rows = []
    for record in session.records:
        student = record.student
        rows.append({
            'Roll Number': student.roll_number,
            'Student Name': student.user.name,
            'Status': record.status.capitalize(),
            'Liveness Verified': 'Yes' if record.liveness_verified else 'No',
            'Confidence (%)': f"{record.confidence_score * 100:.1f}" if record.confidence_score else '-',
            'Marked At': record.marked_at.strftime('%H:%M:%S') if record.marked_at else '-',
        })
    return pd.DataFrame(rows)


def generate_subject_report(subject_id: int) -> pd.DataFrame:
    subject = Subject.query.get_or_404(subject_id)
    sessions = AttendanceSession.query.filter_by(
        subject_id=subject_id, status='completed'
    ).order_by(AttendanceSession.date).all()

    session_dates = [s.date.strftime('%Y-%m-%d') for s in sessions]

    # Gather all students in the subject's semester/department
    students = Student.query.filter_by(
        department_id=subject.department_id,
        semester=subject.semester
    ).all()

    rows = []
    for student in students:
        row = {
            'Roll Number': student.roll_number,
            'Student Name': student.user.name,
        }
        present_count = 0
        for session in sessions:
            record = AttendanceRecord.query.filter_by(
                session_id=session.id, student_id=student.id
            ).first()
            status = record.status.capitalize() if record else 'Absent'
            row[session.date.strftime('%d/%m')] = status
            if status == 'Present':
                present_count += 1
        total = len(sessions)
        row['Total Present'] = present_count
        row['Total Classes'] = total
        row['Percentage (%)'] = f"{(present_count / total * 100):.1f}" if total > 0 else '0.0'
        rows.append(row)

    return pd.DataFrame(rows)


def generate_student_report(student_id: int, subject_id: int = None) -> pd.DataFrame:
    student = Student.query.get_or_404(student_id)
    query = AttendanceRecord.query.join(AttendanceSession).filter(
        AttendanceRecord.student_id == student_id,
        AttendanceSession.status == 'completed'
    )
    if subject_id:
        query = query.filter(AttendanceSession.subject_id == subject_id)
    records = query.order_by(AttendanceSession.date.desc()).all()

    rows = []
    for r in records:
        rows.append({
            'Date': r.session.date.strftime('%d %b %Y'),
            'Subject': r.session.subject.name,
            'Subject Code': r.session.subject.code,
            'Status': r.status.capitalize(),
            'Liveness Verified': 'Yes' if r.liveness_verified else 'No',
            'Marked At': r.marked_at.strftime('%H:%M:%S') if r.marked_at else '—',
        })
    return pd.DataFrame(rows)


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str = 'Attendance') -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        ws = writer.sheets[sheet_name]
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col) + 4
            ws.column_dimensions[col[0].column_letter].width = min(max_len, 30)
    return buf.getvalue()


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode('utf-8')
