"""
AI Context Builder
Fetches real system data from the database and injects it into the AI prompt
based on who is asking and what they're asking about.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.user import User

# ── Intent detection ──────────────────────────────────────────────────────────
_INTENTS = {
    "attendance": [
        "absent",
        "attendance",
        "present",
        "miss",
        "low attendance",
        "who absent",
        "attendance record",
        "bunk",
        "attandance",
    ],
    "marks": [
        "mark",
        "grade",
        "score",
        "exam",
        "result",
        "fail",
        "pass",
        "percentage",
        "topper",
        "rank",
        "gpa",
        "merit",
        "highest",
        "lowest",
    ],
    "fee": [
        "fee",
        "payment",
        "paid",
        "due",
        "pending",
        "outstanding",
        "receipt",
        "balance",
        "unpaid",
    ],
    "notes": [
        "note",
        "notes",
        "material",
        "content",
        "lesson",
        "chapter",
        "topic",
        "summarize",
        "summary",
        "explain",
        "study",
        "resource",
    ],
    "assignment": [
        "assignment",
        "homework",
        "submit",
        "submission",
        "task",
        "pending assignment",
        "due",
        "lab",
    ],
    "students": [
        "student",
        "students",
        "enrolled",
        "roll number",
        "classmate",
        "how many student",
        "list of student",
    ],
    "teachers": [
        "teacher",
        "faculty",
        "instructor",
        "lecturer",
        "professor",
        "how many teacher",
    ],
    "notice": [
        "notice",
        "announcement",
        "notification",
        "circular",
        "bulletin",
    ],
    "timetable": [
        "timetable",
        "schedule",
        "class time",
        "period",
        "when is class",
        "which class",
        "today class",
    ],
    "leave": [
        "leave",
        "sick leave",
        "leave request",
        "leave application",
        "approved leave",
    ],
}


def detect_intents(query: str) -> set[str]:
    q = query.lower()
    found = set()
    for intent, keywords in _INTENTS.items():
        if any(kw in q for kw in keywords):
            found.add(intent)
    if not found:
        found.add("general")
    return found


# ── Formatters ────────────────────────────────────────────────────────────────


def _pct(present: int, total: int) -> str:
    if not total:
        return "0%"
    return f"{present / total * 100:.1f}%"


# ── Role-specific context builders ────────────────────────────────────────────


def _ctx_admin(user: "User", college_id: int, intents: set[str], query: str) -> str:
    from models.assignment import AssignmentSubmission
    from models.attendance import AttendanceRecord, AttendanceSession
    from models.content import TeacherContent
    from models.department import Department
    from models.exam import Exam, Mark
    from models.fee import FeePayment, FeeStructure
    from models.leave import LeaveRequest
    from models.notice import Notice
    from models.student import Student
    from models.subject import Subject
    from models.teacher import Teacher

    parts = []

    # College overview (always)
    students = Student.query.filter_by(college_id=college_id).all()
    teachers = Teacher.query.filter_by(college_id=college_id).all()
    depts = Department.query.filter_by(college_id=college_id).all()
    parts.append(
        f"COLLEGE OVERVIEW:\n"
        f"  Total students: {len(students)}\n"
        f"  Total teachers: {len(teachers)}\n"
        f"  Departments: {', '.join(d.name for d in depts) or 'none'}"
    )

    if "students" in intents or "attendance" in intents:
        # Student list with dept
        lines = []
        for s in students[:50]:
            dept = next((d.name for d in depts if d.id == s.department_id), "?")
            lines.append(
                f"  - {s.user.full_name} | Roll:{s.roll_number} | Dept:{dept} | Sem:{s.semester}"
            )
        parts.append("STUDENT LIST:\n" + "\n".join(lines))

    if "teachers" in intents:
        lines = []
        for t in teachers:
            dept = next((d.name for d in depts if d.id == t.department_id), "?")
            lines.append(
                f"  - {t.user.full_name} | {t.designation or 'Teacher'} | Dept:{dept}"
            )
        parts.append("TEACHER LIST:\n" + "\n".join(lines))

    if "attendance" in intents:
        records = AttendanceRecord.query.filter_by(college_id=college_id).all()
        subjects = Subject.query.filter_by(college_id=college_id).all()
        subj_map = {s.id: s.name for s in subjects}

        # Per-student absent count
        student_absent: dict[int, int] = defaultdict(int)
        student_total: dict[int, int] = defaultdict(int)
        subj_absent: dict[int, int] = defaultdict(int)

        sessions = AttendanceSession.query.filter_by(college_id=college_id).all()
        sess_subj = {s.id: s.subject_id for s in sessions}

        for r in records:
            student_total[r.student_id] += 1
            if r.status == "absent":
                student_absent[r.student_id] += 1
                sid = sess_subj.get(r.session_id)
                if sid:
                    subj_absent[sid] += 1

        stu_map = {s.id: s for s in students}
        ranked = sorted(student_absent.items(), key=lambda x: x[1], reverse=True)[:15]
        lines = []
        for stu_id, abs_cnt in ranked:
            s = stu_map.get(stu_id)
            if not s:
                continue
            tot = student_total[stu_id]
            dept = next((d.name for d in depts if d.id == s.department_id), "?")
            lines.append(
                f"  - {s.user.full_name} | Roll:{s.roll_number} | Dept:{dept} | "
                f"Absent:{abs_cnt}/{tot} sessions | Present:{_pct(tot - abs_cnt, tot)}"
            )
        parts.append(
            "MOST ABSENT STUDENTS (top 15):\n"
            + ("\n".join(lines) or "  No records yet.")
        )

        subj_ranked = sorted(subj_absent.items(), key=lambda x: x[1], reverse=True)
        subj_lines = [
            f"  - {subj_map.get(sid, 'Unknown')}: {cnt} total absences"
            for sid, cnt in subj_ranked[:10]
        ]
        parts.append(
            "SUBJECT-WISE TOTAL ABSENCES:\n"
            + ("\n".join(subj_lines) or "  No records yet.")
        )

    if "marks" in intents:
        marks = Mark.query.filter_by(college_id=college_id).all()
        exams = Exam.query.filter_by(college_id=college_id).all()
        exam_map = {e.id: e for e in exams}
        subjects = Subject.query.filter_by(college_id=college_id).all()
        subj_map = {s.id: s.name for s in subjects}
        stu_map = {s.id: s for s in students}

        # Per-student average
        stu_scores: dict[int, list[float]] = defaultdict(list)
        for m in marks:
            if m.marks_obtained is not None and not m.is_absent:
                ex = exam_map.get(m.exam_id)
                if ex and ex.total_marks:
                    stu_scores[m.student_id].append(
                        m.marks_obtained / ex.total_marks * 100
                    )

        lines = []
        for stu_id, scores in sorted(
            stu_scores.items(), key=lambda x: -sum(x[1]) / len(x[1])
        )[:10]:
            s = stu_map.get(stu_id)
            if not s:
                continue
            avg = sum(scores) / len(scores)
            lines.append(
                f"  - {s.user.full_name} | Roll:{s.roll_number} | Avg:{avg:.1f}%"
            )
        parts.append(
            "TOP PERFORMERS (by average %):\n" + ("\n".join(lines) or "  No marks yet.")
        )

        # Bottom performers
        bottom = []
        for stu_id, scores in sorted(
            stu_scores.items(), key=lambda x: sum(x[1]) / len(x[1])
        )[:10]:
            s = stu_map.get(stu_id)
            if not s:
                continue
            avg = sum(scores) / len(scores)
            bottom.append(
                f"  - {s.user.full_name} | Roll:{s.roll_number} | Avg:{avg:.1f}%"
            )
        parts.append("LOWEST PERFORMERS:\n" + ("\n".join(bottom) or "  No marks yet."))

    if "fee" in intents:
        structures = FeeStructure.query.filter_by(
            college_id=college_id, is_active=True
        ).all()
        payments = FeePayment.query.filter_by(college_id=college_id).all()
        stu_map = {s.id: s for s in students}

        paid_set: dict[int, set[int]] = defaultdict(set)
        for p in payments:
            paid_set[p.student_id].add(p.fee_structure_id)

        lines = [
            f"  - {fs.title} | Amount:Rs.{fs.amount} | Due:{fs.due_date or 'N/A'}"
            for fs in structures
        ]
        parts.append("ACTIVE FEE STRUCTURES:\n" + ("\n".join(lines) or "  None."))

        unpaid = []
        for fs in structures:
            for s in students:
                if fs.id not in paid_set[s.id]:
                    unpaid.append(
                        f"  - {s.user.full_name} | Roll:{s.roll_number} | Unpaid: {fs.title}"
                    )
        parts.append(
            "UNPAID FEES (first 20):\n" + ("\n".join(unpaid[:20]) or "  All paid.")
        )

    if "notice" in intents:
        from models.notice import Notice

        notices = (
            Notice.query.filter_by(college_id=college_id)
            .order_by(Notice.created_at.desc())
            .limit(10)
            .all()
        )
        lines = [
            f"  - [{n.category.upper()}] {n.title} (posted {n.created_at.strftime('%Y-%m-%d')})"
            for n in notices
        ]
        parts.append("RECENT NOTICES:\n" + ("\n".join(lines) or "  No notices."))

    if "leave" in intents:
        from models.leave import LeaveRequest

        leaves = (
            LeaveRequest.query.filter_by(college_id=college_id)
            .order_by(LeaveRequest.created_at.desc())
            .limit(20)
            .all()
        )
        stu_map = {s.id: s for s in students}
        lines = []
        for lv in leaves:
            s = stu_map.get(lv.student_id)
            name = s.user.full_name if s else "Unknown"
            lines.append(
                f"  - {name} | {lv.from_date} to {lv.to_date} | Status:{lv.status} | Reason:{lv.reason[:60]}"
            )
        parts.append("LEAVE REQUESTS (recent 20):\n" + ("\n".join(lines) or "  None."))

    if "assignment" in intents:
        from models.assignment import AssignmentSubmission
        from models.content import TeacherContent

        assignments = (
            TeacherContent.query.filter_by(
                college_id=college_id, content_type="assignment", is_published=True
            )
            .order_by(TeacherContent.created_at.desc())
            .limit(10)
            .all()
        )
        lines = []
        for a in assignments:
            subs = AssignmentSubmission.query.filter_by(content_id=a.id).count()
            lines.append(
                f"  - {a.title} | Due:{a.due_date or 'N/A'} | Submissions:{subs}"
            )
        parts.append("RECENT ASSIGNMENTS:\n" + ("\n".join(lines) or "  None."))

    return "\n\n".join(parts)


def _ctx_teacher(user: "User", college_id: int, intents: set[str], query: str) -> str:
    from models.assignment import AssignmentSubmission
    from models.attendance import AttendanceRecord, AttendanceSession
    from models.content import TeacherContent
    from models.exam import Exam, Mark
    from models.student import Student
    from models.subject import Subject
    from models.teacher import Teacher

    teacher = Teacher.query.filter_by(user_id=user.id, college_id=college_id).first()
    if not teacher:
        return "Teacher profile not found."

    parts = [
        f"YOUR PROFILE: {user.full_name} | {teacher.designation or 'Teacher'} | Employee ID: {teacher.employee_id}"
    ]

    subjects = Subject.query.filter_by(
        teacher_id=teacher.id, college_id=college_id
    ).all()
    subj_lines = [f"  - {s.name} ({s.code}) | Sem:{s.semester}" for s in subjects]
    parts.append("YOUR SUBJECTS:\n" + ("\n".join(subj_lines) or "  None assigned."))

    if "attendance" in intents:
        sessions = AttendanceSession.query.filter_by(
            teacher_id=teacher.id, college_id=college_id
        ).all()
        records = []
        for sess in sessions:
            recs = AttendanceRecord.query.filter_by(session_id=sess.id).all()
            records.extend(recs)

        student_abs: dict[int, int] = defaultdict(int)
        student_tot: dict[int, int] = defaultdict(int)
        for r in records:
            student_tot[r.student_id] += 1
            if r.status == "absent":
                student_abs[r.student_id] += 1

        students = Student.query.filter_by(college_id=college_id).all()
        stu_map = {s.id: s for s in students}
        ranked = sorted(student_abs.items(), key=lambda x: x[1], reverse=True)[:10]
        lines = []
        for stu_id, abs_cnt in ranked:
            s = stu_map.get(stu_id)
            if s:
                tot = student_tot[stu_id]
                lines.append(
                    f"  - {s.user.full_name} | Roll:{s.roll_number} | "
                    f"Absent:{abs_cnt}/{tot} | Present:{_pct(tot - abs_cnt, tot)}"
                )
        parts.append(
            "MOST ABSENT IN YOUR CLASSES:\n" + ("\n".join(lines) or "  No records yet.")
        )

    if "notes" in intents or "assignment" in intents:
        contents = (
            TeacherContent.query.filter_by(
                teacher_id=teacher.id, college_id=college_id, is_published=True
            )
            .order_by(TeacherContent.created_at.desc())
            .limit(15)
            .all()
        )

        notes = [c for c in contents if c.content_type in ("note", "lab")]
        asgns = [c for c in contents if c.content_type == "assignment"]

        if notes and "notes" in intents:
            note_q = query.lower()
            matched = [
                n
                for n in notes
                if any(
                    w in (n.title + " " + (n.body or "")).lower()
                    for w in note_q.split()
                    if len(w) > 3
                )
            ]
            show = matched[:3] if matched else notes[:3]
            lines = []
            for n in show:
                body_preview = (n.body or "")[:500]
                lines.append(
                    f"  TITLE: {n.title}\n  TYPE: {n.content_type}\n  CONTENT:\n{body_preview}"
                )
            parts.append("RELEVANT NOTES/LABS:\n" + "\n---\n".join(lines))

        if asgns and "assignment" in intents:
            a_lines = []
            for a in asgns[:5]:
                subs = AssignmentSubmission.query.filter_by(content_id=a.id).count()
                a_lines.append(
                    f"  - {a.title} | Due:{a.due_date or 'N/A'} | Submissions:{subs} | Marks:{a.marks}"
                )
            parts.append("YOUR ASSIGNMENTS:\n" + "\n".join(a_lines))

    if "marks" in intents:
        exams = Exam.query.filter_by(college_id=college_id, created_by=teacher.id).all()
        exam_map = {e.id: e for e in exams}
        marks = (
            Mark.query.filter(Mark.exam_id.in_([e.id for e in exams])).all()
            if exams
            else []
        )
        stu_scores: dict[int, list] = defaultdict(list)
        for m in marks:
            if m.marks_obtained is not None:
                ex = exam_map.get(m.exam_id)
                if ex:
                    stu_scores[m.student_id].append(
                        (ex.title, m.marks_obtained, ex.total_marks)
                    )
        students = Student.query.filter_by(college_id=college_id).all()
        stu_map = {s.id: s for s in students}
        lines = []
        for stu_id, entries in list(stu_scores.items())[:15]:
            s = stu_map.get(stu_id)
            if s:
                details = ", ".join(f"{t}:{o}/{tot}" for t, o, tot in entries)
                lines.append(f"  - {s.user.full_name}: {details}")
        parts.append(
            "MARKS ENTERED BY YOU:\n" + ("\n".join(lines) or "  No marks entered.")
        )

    return "\n\n".join(parts)


def _ctx_student(user: "User", college_id: int, intents: set[str], query: str) -> str:
    from models.assignment import AssignmentSubmission
    from models.attendance import AttendanceRecord, AttendanceSession
    from models.content import TeacherContent
    from models.department import Department
    from models.exam import Exam, Mark
    from models.fee import FeePayment, FeeStructure
    from models.leave import LeaveRequest
    from models.notice import Notice
    from models.student import Student
    from models.subject import Subject
    from models.timetable import TimetableSlot

    student = Student.query.filter_by(user_id=user.id, college_id=college_id).first()
    if not student:
        return "Student profile not found."

    dept = Department.query.get(student.department_id)
    parts = [
        f"YOUR PROFILE: {user.full_name} | Roll:{student.roll_number} | "
        f"Dept:{dept.name if dept else '?'} | Semester:{student.semester}"
    ]

    if "attendance" in intents:
        records = AttendanceRecord.query.filter_by(
            student_id=student.id, college_id=college_id
        ).all()
        sessions = AttendanceSession.query.filter_by(college_id=college_id).all()
        sess_subj = {s.id: s.subject_id for s in sessions}
        subjects = Subject.query.filter_by(
            college_id=college_id, department_id=student.department_id
        ).all()
        subj_map = {s.id: s.name for s in subjects}

        subj_present: dict[int, int] = defaultdict(int)
        subj_total: dict[int, int] = defaultdict(int)
        for r in records:
            sid = sess_subj.get(r.session_id)
            if sid:
                subj_total[sid] += 1
                if r.status == "present":
                    subj_present[sid] += 1

        overall_present = sum(1 for r in records if r.status == "present")
        lines = [
            f"  Overall: {overall_present}/{len(records)} | {_pct(overall_present, len(records))}"
        ]
        for sid, tot in sorted(subj_total.items()):
            p = subj_present[sid]
            lines.append(
                f"  - {subj_map.get(sid, 'Unknown')}: {p}/{tot} ({_pct(p, tot)})"
            )
        parts.append("YOUR ATTENDANCE:\n" + "\n".join(lines))

    if "marks" in intents:
        marks = Mark.query.filter_by(student_id=student.id, college_id=college_id).all()
        exams = {e.id: e for e in Exam.query.filter_by(college_id=college_id).all()}
        subjects = {
            s.id: s.name for s in Subject.query.filter_by(college_id=college_id).all()
        }
        lines = []
        for m in marks:
            ex = exams.get(m.exam_id)
            if ex:
                subj = subjects.get(ex.subject_id, "Unknown")
                if m.is_absent:
                    lines.append(f"  - {ex.title} ({subj}): Absent")
                elif m.marks_obtained is not None:
                    pct = m.marks_obtained / ex.total_marks * 100
                    lines.append(
                        f"  - {ex.title} ({subj}): {m.marks_obtained}/{ex.total_marks} ({pct:.1f}%)"
                    )
        parts.append("YOUR MARKS:\n" + ("\n".join(lines) or "  No marks recorded yet."))

    if "fee" in intents:
        structures = FeeStructure.query.filter_by(
            college_id=college_id, is_active=True
        ).all()
        payments = FeePayment.query.filter_by(
            student_id=student.id, college_id=college_id
        ).all()
        paid_ids = {p.fee_structure_id for p in payments}
        lines = []
        for fs in structures:
            status = "PAID" if fs.id in paid_ids else "UNPAID"
            lines.append(
                f"  - {fs.title}: Rs.{fs.amount} | {status} | Due:{fs.due_date or 'N/A'}"
            )
        parts.append("YOUR FEES:\n" + ("\n".join(lines) or "  No fee structures set."))

    if "notes" in intents:
        notes = (
            TeacherContent.query.filter_by(
                college_id=college_id,
                department_id=student.department_id,
                semester=student.semester,
                is_published=True,
            )
            .filter(TeacherContent.content_type.in_(["note", "lab"]))
            .order_by(TeacherContent.created_at.desc())
            .limit(50)
            .all()
        )

        # Score notes by keyword relevance to the query
        q_words = [w for w in query.lower().split() if len(w) > 2]
        scored = []
        for n in notes:
            text = (n.title + " " + (n.body or "")).lower()
            score = sum(1 for w in q_words if w in text)
            scored.append((score, n))
        scored.sort(key=lambda x: -x[0])

        # List all note titles so AI can tell student what's available
        all_titles = []
        for _, n in scored:
            has_text = bool((n.body or "").strip())
            icon = "[TEXT]" if has_text else "[FILE]"
            all_titles.append(f"  {icon} [{n.content_type.upper()}] {n.title}")
        parts.append(
            "ALL AVAILABLE NOTES/LABS (TEXT=can summarize, FILE=uploaded file only):\n"
            + ("\n".join(all_titles) or "  None.")
        )

        # If query has specific keywords, inject full body of best text-match
        best_score, best_note = scored[0] if scored else (0, None)
        has_specific_topic = bool(
            best_score > 0 and best_note is not None and (best_note.body or "").strip()
        )

        if has_specific_topic and best_note is not None:
            body = (best_note.body or "").strip()
            # Give the AI the full body (up to 3000 chars) of the best match
            parts.append(
                f"BEST MATCHING NOTE TO SUMMARIZE:\n"
                f"  TITLE: {best_note.title}\n"
                f"  TYPE: {best_note.content_type.upper()}\n"
                f"  FULL CONTENT:\n{body[:3000]}"
                + ("\n  [Note: content truncated]" if len(body) > 3000 else "")
            )
        elif not q_words or all(
            w in ("note", "notes", "summarize", "summary", "show", "list")
            for w in q_words
        ):
            # Student asked generically — tell AI to ask which note they want
            parts.append(
                "INSTRUCTION: The student asked about notes without specifying a topic. "
                "List the available TEXT notes above and ask which one they want you to summarize or explain."
            )

    if "assignment" in intents:
        assignments = (
            TeacherContent.query.filter_by(
                college_id=college_id,
                department_id=student.department_id,
                semester=student.semester,
                content_type="assignment",
                is_published=True,
            )
            .order_by(TeacherContent.created_at.desc())
            .limit(10)
            .all()
        )

        subs = {
            s.content_id: s
            for s in AssignmentSubmission.query.filter_by(student_id=student.id).all()
        }
        lines = []
        for a in assignments:
            sub = subs.get(a.id)
            status = "SUBMITTED" if sub else "PENDING"
            grade = f" | Grade:{sub.marks_awarded}" if sub and sub.marks_awarded else ""
            lines.append(f"  - {a.title} | Due:{a.due_date or 'N/A'} | {status}{grade}")
        parts.append(
            "YOUR ASSIGNMENTS:\n" + ("\n".join(lines) or "  No assignments yet.")
        )

    if "timetable" in intents:
        tt = (
            TimetableSlot.query.filter_by(
                college_id=college_id,
                department_id=student.department_id,
                semester=student.semester,
            )
            .order_by(TimetableSlot.day_of_week, TimetableSlot.start_time)
            .all()
        )
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
        subjects = {
            s.id: s.name for s in Subject.query.filter_by(college_id=college_id).all()
        }
        lines = []
        for entry in tt:
            day = (
                days[entry.day_of_week]
                if 0 <= entry.day_of_week < len(days)
                else str(entry.day_of_week)
            )
            lines.append(
                f"  {day}: {entry.start_time.strftime('%H:%M')}-{entry.end_time.strftime('%H:%M')} | {subjects.get(entry.subject_id, 'Unknown')}"
            )
        parts.append("YOUR TIMETABLE:\n" + ("\n".join(lines) or "  No timetable set."))

    if "leave" in intents:
        leaves = (
            LeaveRequest.query.filter_by(student_id=student.id, college_id=college_id)
            .order_by(LeaveRequest.created_at.desc())
            .limit(10)
            .all()
        )
        lines = [
            f"  - {lv.from_date} to {lv.to_date} | Status:{lv.status} | Reason:{lv.reason[:60]}"
            for lv in leaves
        ]
        parts.append(
            "YOUR LEAVE REQUESTS:\n" + ("\n".join(lines) or "  No leaves requested.")
        )

    if "notice" in intents:
        notices = (
            Notice.query.filter_by(college_id=college_id)
            .filter((Notice.target_role == "all") | (Notice.target_role == "student"))
            .order_by(Notice.created_at.desc())
            .limit(8)
            .all()
        )
        lines = [f"  - [{n.category.upper()}] {n.title}" for n in notices]
        parts.append("RECENT NOTICES:\n" + ("\n".join(lines) or "  No notices."))

    return "\n\n".join(parts)


def _ctx_parent(user: "User", college_id: int, intents: set[str], query: str) -> str:
    from models.attendance import AttendanceRecord
    from models.exam import Exam, Mark
    from models.fee import FeePayment, FeeStructure
    from models.notice import Notice
    from models.parent import ParentStudent
    from models.student import Student
    from models.subject import Subject

    parent_links = ParentStudent.query.filter_by(
        parent_id=user.id,
        college_id=college_id,
    ).all()
    child_ids = [link.student_id for link in parent_links]

    children = (
        Student.query.filter_by(college_id=college_id)
        .filter(Student.id.in_(child_ids))
        .all()
        if child_ids
        else []
    )

    if not children:
        return "No linked students found for your account."

    parts = [f"LINKED CHILDREN: {', '.join(c.user.full_name for c in children)}"]

    for child in children:
        child_parts = [f"\n=== {child.user.full_name} | Roll:{child.roll_number} ==="]

        if "attendance" in intents:
            records = AttendanceRecord.query.filter_by(
                student_id=child.id, college_id=college_id
            ).all()
            present = sum(1 for r in records if r.status == "present")
            child_parts.append(
                f"Attendance: {present}/{len(records)} sessions ({_pct(present, len(records))})"
            )

        if "marks" in intents:
            marks = Mark.query.filter_by(
                student_id=child.id, college_id=college_id
            ).all()
            exams = {e.id: e for e in Exam.query.filter_by(college_id=college_id).all()}
            subjects = {
                s.id: s.name
                for s in Subject.query.filter_by(college_id=college_id).all()
            }
            for m in marks[:10]:
                ex = exams.get(m.exam_id)
                if ex and m.marks_obtained is not None:
                    child_parts.append(
                        f"  {subjects.get(ex.subject_id, '?')} - {ex.title}: "
                        f"{m.marks_obtained}/{ex.total_marks} ({m.marks_obtained / ex.total_marks * 100:.1f}%)"
                    )

        if "fee" in intents:
            structs = FeeStructure.query.filter_by(
                college_id=college_id, is_active=True
            ).all()
            paid_ids = {
                p.fee_structure_id
                for p in FeePayment.query.filter_by(student_id=child.id).all()
            }
            for fs in structs:
                status = "PAID" if fs.id in paid_ids else "UNPAID"
                child_parts.append(f"  Fee - {fs.title}: Rs.{fs.amount} [{status}]")

        parts.extend(child_parts)

    if "notice" in intents:
        notices = (
            Notice.query.filter_by(college_id=college_id)
            .order_by(Notice.created_at.desc())
            .limit(8)
            .all()
        )
        lines = [f"  - [{n.category.upper()}] {n.title}" for n in notices]
        parts.append("RECENT NOTICES:\n" + "\n".join(lines))

    return "\n\n".join(parts)


# ── Public API ────────────────────────────────────────────────────────────────


def build_context(user: "User", college_id: int, query: str) -> str:
    """Return a structured context string of real DB data relevant to the query."""
    intents = detect_intents(query)

    try:
        if user.role == "admin":
            data = _ctx_admin(user, college_id, intents, query)
        elif user.role == "teacher":
            data = _ctx_teacher(user, college_id, intents, query)
        elif user.role == "student":
            data = _ctx_student(user, college_id, intents, query)
        elif user.role == "parent":
            data = _ctx_parent(user, college_id, intents, query)
        elif user.role == "super_admin":
            from models.college import College

            colleges = College.query.filter_by(is_active=True).all()
            data = f"PLATFORM OVERVIEW:\n  Active colleges: {len(colleges)}\n"
            data += "\n".join(f"  - {c.name} (code:{c.code})" for c in colleges)
        else:
            data = ""
    except Exception as e:
        data = f"(Context fetch error: {e})"

    if not data.strip():
        return ""

    return (
        "=== LIVE SYSTEM DATA ===\n"
        "(Use this real data to answer accurately. Do not make up numbers.)\n\n"
        + data
        + "\n=== END SYSTEM DATA ===\n"
    )
