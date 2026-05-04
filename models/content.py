from extensions import db
from utils.time import utc_now_naive

CONTENT_TYPES = ('note', 'assignment', 'lab', 'question')
CONTENT_ALLOWED_EXTENSIONS = frozenset({
    'csv', 'doc', 'docx', 'gif', 'jpeg', 'jpg',
    'pdf', 'png', 'pptx', 'txt', 'webp', 'xls', 'xlsx',
})
CONTENT_PREVIEWABLE_EXTENSIONS = frozenset({
    'doc', 'docx', 'gif', 'jpeg', 'jpg',
    'pdf', 'png', 'pptx', 'webp',
})


def content_extension(filename: str | None) -> str:
    if not filename or '.' not in filename:
        return ''
    return filename.rsplit('.', 1)[-1].lower()


def is_allowed_content_upload(filename: str | None) -> bool:
    return content_extension(filename) in CONTENT_ALLOWED_EXTENSIONS


def is_previewable_content(filename: str | None) -> bool:
    return content_extension(filename) in CONTENT_PREVIEWABLE_EXTENSIONS


class TeacherContent(db.Model):
    __tablename__ = 'teacher_contents'

    id            = db.Column(db.Integer, primary_key=True)
    teacher_id    = db.Column(db.Integer, db.ForeignKey('teachers.id'),    nullable=False)
    subject_id    = db.Column(db.Integer, db.ForeignKey('subjects.id'),    nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    semester      = db.Column(db.Integer, nullable=False)
    content_type  = db.Column(db.Enum(*CONTENT_TYPES), nullable=False, default='note')
    title         = db.Column(db.String(200), nullable=False)
    body          = db.Column(db.Text, nullable=True)
    file_path     = db.Column(db.String(255), nullable=True)
    due_date      = db.Column(db.Date, nullable=True)
    marks         = db.Column(db.Integer, nullable=True)
    is_published  = db.Column(db.Boolean, default=False, nullable=False)
    created_at    = db.Column(db.DateTime, default=utc_now_naive)
    updated_at    = db.Column(db.DateTime, default=utc_now_naive,
                              onupdate=utc_now_naive)

    teacher    = db.relationship('Teacher',    backref='contents')
    subject    = db.relationship('Subject',    backref='contents')
    department = db.relationship('Department', backref='tc_contents')
