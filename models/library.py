from extensions import db
from utils.time import utc_now_naive


LIBRARY_BOOK_TYPES = ('physical', 'digital', 'hybrid')
LIBRARY_LOCATION_TYPES = ('zone', 'department_section', 'room', 'aisle', 'rack', 'shelf', 'bin', 'cell')
LIBRARY_COPY_STATUSES = ('available', 'issued', 'held', 'maintenance', 'damaged', 'lost', 'written_off')
LIBRARY_CONDITIONS = ('new', 'good', 'fair', 'damaged')
LIBRARY_LOAN_STATUSES = ('active', 'returned', 'overdue', 'lost')
LIBRARY_EBOOK_ACCESS_LEVELS = ('preview_only', 'full_read')
LIBRARY_ACCESS_ACTIONS = ('view', 'download')
LIBRARY_RESERVATION_STATUSES = ('pending', 'ready_for_pickup', 'fulfilled', 'cancelled', 'expired')
LIBRARY_FINE_STATUSES = ('unpaid', 'partial', 'paid', 'waived')
LIBRARY_AUDIT_STATUSES = ('open', 'completed')
LIBRARY_AUDIT_DISCREPANCY_STATUSES = ('unresolved', 'follow_up_required', 'marked_lost', 'marked_damaged')
LIBRARY_RULE_DEFAULTS = {
    'student_max_active_loans': 3,
    'teacher_max_active_loans': 5,
    'student_due_days': 14,
    'teacher_due_days': 30,
    'student_max_renewals': 1,
    'teacher_max_renewals': 2,
    'student_renew_days': 7,
    'teacher_renew_days': 14,
    'student_fine_per_day': 2.00,
    'teacher_fine_per_day': 1.00,
    'grace_days': 0,
    'reservation_hold_days': 2,
}


class LibraryRule(db.Model):
    __tablename__ = 'library_rules'
    __table_args__ = (
        db.UniqueConstraint('college_id', name='uq_library_rules_college'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    student_max_active_loans = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['student_max_active_loans'])
    teacher_max_active_loans = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['teacher_max_active_loans'])
    student_due_days = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['student_due_days'])
    teacher_due_days = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['teacher_due_days'])
    student_max_renewals = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['student_max_renewals'])
    teacher_max_renewals = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['teacher_max_renewals'])
    student_renew_days = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['student_renew_days'])
    teacher_renew_days = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['teacher_renew_days'])
    student_fine_per_day = db.Column(db.Numeric(10, 2), nullable=False, default=LIBRARY_RULE_DEFAULTS['student_fine_per_day'])
    teacher_fine_per_day = db.Column(db.Numeric(10, 2), nullable=False, default=LIBRARY_RULE_DEFAULTS['teacher_fine_per_day'])
    grace_days = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['grace_days'])
    reservation_hold_days = db.Column(db.Integer, nullable=False, default=LIBRARY_RULE_DEFAULTS['reservation_hold_days'])
    regulations = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    @property
    def student_policy(self) -> dict:
        return {
            'label': 'Student',
            'max_active_loans': self.student_max_active_loans,
            'due_days': self.student_due_days,
            'max_renewals': self.student_max_renewals,
            'renew_days': self.student_renew_days,
            'fine_per_day': self.student_fine_per_day,
        }

    @property
    def teacher_policy(self) -> dict:
        return {
            'label': 'Teacher',
            'max_active_loans': self.teacher_max_active_loans,
            'due_days': self.teacher_due_days,
            'max_renewals': self.teacher_max_renewals,
            'renew_days': self.teacher_renew_days,
            'fine_per_day': self.teacher_fine_per_day,
        }

    def __repr__(self):
        return f'<LibraryRule college={self.college_id}>'


class LibraryCategory(db.Model):
    __tablename__ = 'library_categories'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'name', name='uq_library_categories_college_name'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    books = db.relationship('LibraryBook', backref='category', lazy=True)

    def __repr__(self):
        return f'<LibraryCategory {self.name}>'


class LibraryLocation(db.Model):
    __tablename__ = 'library_locations'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'parent_id', 'name', name='uq_library_locations_college_parent_name'),
        db.UniqueConstraint('college_id', 'code', name='uq_library_locations_college_code'),
        db.Index('ix_library_locations_college_parent_active', 'college_id', 'parent_id', 'is_active'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('library_locations.id'), nullable=True, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(50), nullable=True)
    location_type = db.Column(
        db.Enum(*LIBRARY_LOCATION_TYPES, name='library_location_type'),
        nullable=False,
        default='rack',
    )
    semester = db.Column(db.Integer, nullable=True)
    row_count = db.Column(db.Integer, nullable=True)
    column_count = db.Column(db.Integer, nullable=True)
    row_label = db.Column(db.String(30), nullable=True)
    column_label = db.Column(db.String(30), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    parent = db.relationship('LibraryLocation', remote_side=[id], backref=db.backref('children', lazy=True))
    department = db.relationship('Department', lazy=True)
    subject = db.relationship('Subject', lazy=True)

    @property
    def type_label(self) -> str:
        return self.location_type.replace('_', ' ').title()

    @property
    def path_segments(self) -> list[str]:
        segments: list[str] = []
        node = self
        while node is not None:
            segments.append(node.name)
            node = node.parent
        segments.reverse()
        if self.department and (not segments or segments[0] != self.department.name):
            segments.insert(0, self.department.name)
        return segments

    @property
    def full_label(self) -> str:
        base = ' / '.join(self.path_segments)
        if self.coordinate_label:
            base = f'{base} [{self.coordinate_label}]'
        if self.code:
            return f'{base} ({self.code})'
        return base

    @property
    def coordinate_label(self) -> str:
        parts: list[str] = []
        if self.row_label:
            parts.append(f'Row {self.row_label}')
        if self.column_label:
            parts.append(f'Column {self.column_label}')
        return ' / '.join(parts)

    @property
    def grid_label(self) -> str:
        if self.location_type != 'rack' or not self.row_count or not self.column_count:
            return ''
        return f'{self.row_count} row(s) x {self.column_count} column(s)'

    @property
    def academic_scope_label(self) -> str:
        parts: list[str] = []
        if self.department:
            parts.append(self.department.name)
        if self.semester:
            parts.append(f'Semester {self.semester}')
        if self.subject:
            parts.append(self.subject.name)
        return ' / '.join(parts) or 'General library'

    @property
    def active_book_count(self) -> int:
        return len([book for book in self.books if book.is_active])

    @property
    def child_count(self) -> int:
        return len(self.children)

    def is_descendant_of(self, other: 'LibraryLocation') -> bool:
        node = self.parent
        while node is not None:
            if node.id == other.id:
                return True
            node = node.parent
        return False

    def __repr__(self):
        return f'<LibraryLocation {self.full_label}>'


class LibraryBook(db.Model):
    __tablename__ = 'library_books'
    __table_args__ = (
        db.Index('ix_library_books_college_type_active', 'college_id', 'book_type', 'is_active'),
        db.Index('ix_library_books_college_department_semester', 'college_id', 'department_id', 'semester'),
        db.UniqueConstraint('college_id', 'isbn', name='uq_library_books_college_isbn'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('library_categories.id'), nullable=True, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, index=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=True, index=True)
    default_location_id = db.Column(db.Integer, db.ForeignKey('library_locations.id'), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(200), nullable=False)
    isbn = db.Column(db.String(32), nullable=True)
    publisher = db.Column(db.String(200), nullable=True)
    edition = db.Column(db.String(100), nullable=True)
    language = db.Column(db.String(50), nullable=True)
    semester = db.Column(db.Integer, nullable=True)
    book_type = db.Column(db.Enum(*LIBRARY_BOOK_TYPES, name='library_book_type'), nullable=False, default='physical')
    description = db.Column(db.Text, nullable=True)
    tags = db.Column(db.String(255), nullable=True)
    shelf_code = db.Column(db.String(100), nullable=True)
    ebook_file_path = db.Column(db.String(255), nullable=True)
    ebook_filename = db.Column(db.String(255), nullable=True)
    ebook_access_level = db.Column(
        db.Enum(*LIBRARY_EBOOK_ACCESS_LEVELS, name='library_ebook_access_level'),
        nullable=False,
        default='full_read',
    )
    ebook_download_allowed = db.Column(db.Boolean, nullable=False, default=True)
    ebook_preview_page_limit = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    department = db.relationship('Department', lazy=True)
    subject = db.relationship('Subject', lazy=True)
    default_location = db.relationship(
        'LibraryLocation',
        backref=db.backref('books', lazy=True),
        foreign_keys=[default_location_id],
        lazy=True,
    )
    copies = db.relationship('LibraryBookCopy', backref='book', lazy=True, cascade='all, delete-orphan')
    loans = db.relationship('LibraryLoan', backref='book', lazy=True, cascade='all, delete-orphan')
    reservations = db.relationship('LibraryReservation', backref='book', lazy=True, cascade='all, delete-orphan')
    access_logs = db.relationship('LibraryAccessLog', backref='book', lazy=True, cascade='all, delete-orphan')
    reading_progress = db.relationship('LibraryReadingProgress', backref='book', lazy=True, cascade='all, delete-orphan')

    @property
    def physical_enabled(self) -> bool:
        return self.book_type in {'physical', 'hybrid'}

    @property
    def digital_enabled(self) -> bool:
        return self.book_type in {'digital', 'hybrid'} and bool(self.ebook_file_path)

    @property
    def total_copies(self) -> int:
        return len(self.copies)

    @property
    def available_copies(self) -> int:
        return sum(1 for copy in self.copies if copy.status == 'available')

    @property
    def active_loans(self) -> int:
        return sum(1 for loan in self.loans if loan.status in {'active', 'overdue'})

    @property
    def pending_reservations(self) -> int:
        return sum(1 for reservation in self.reservations if reservation.status in {'pending', 'ready_for_pickup'})

    @property
    def ebook_access_label(self) -> str:
        return 'Preview Only' if self.ebook_access_level == 'preview_only' else 'Full Read'

    @property
    def location_label(self) -> str:
        if self.default_location:
            return self.default_location.full_label
        if self.shelf_code:
            return self.shelf_code
        return 'Not assigned'

    def __repr__(self):
        return f'<LibraryBook {self.title}>'


class LibraryBookCopy(db.Model):
    __tablename__ = 'library_book_copies'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'accession_number', name='uq_library_copies_college_accession'),
        db.Index('ix_library_copies_college_status', 'college_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    location_id = db.Column(db.Integer, db.ForeignKey('library_locations.id'), nullable=True, index=True)
    replacement_of_copy_id = db.Column(db.Integer, db.ForeignKey('library_book_copies.id'), nullable=True, index=True)
    accession_number = db.Column(db.String(50), nullable=False)
    barcode = db.Column(db.String(100), nullable=True)
    rack_location = db.Column(db.String(100), nullable=True)
    condition = db.Column(db.Enum(*LIBRARY_CONDITIONS, name='library_copy_condition'), nullable=False, default='good')
    status = db.Column(db.Enum(*LIBRARY_COPY_STATUSES, name='library_copy_status'), nullable=False, default='available')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    loans = db.relationship('LibraryLoan', backref='copy', lazy=True)
    location = db.relationship(
        'LibraryLocation',
        backref=db.backref('copies', lazy=True),
        foreign_keys=[location_id],
        lazy=True,
    )
    replacement_of = db.relationship(
        'LibraryBookCopy',
        remote_side=[id],
        foreign_keys=[replacement_of_copy_id],
        backref=db.backref('replacement_copies', lazy=True),
        lazy=True,
    )
    inventory_events = db.relationship('LibraryCopyEvent', backref='copy', lazy=True, cascade='all, delete-orphan')

    @property
    def location_label(self) -> str:
        if self.location:
            return self.location.full_label
        if self.rack_location:
            return self.rack_location
        return self.book.location_label

    def __repr__(self):
        return f'<LibraryBookCopy {self.accession_number}>'


class LibraryCopyEvent(db.Model):
    __tablename__ = 'library_copy_events'
    __table_args__ = (
        db.Index('ix_library_copy_events_college_created', 'college_id', 'created_at'),
        db.Index('ix_library_copy_events_copy_created', 'copy_id', 'created_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    copy_id = db.Column(db.Integer, db.ForeignKey('library_book_copies.id'), nullable=False, index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('library_loans.id'), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)
    previous_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=True)
    previous_condition = db.Column(db.String(50), nullable=True)
    new_condition = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    book = db.relationship('LibraryBook', lazy=True)
    loan = db.relationship('LibraryLoan', lazy=True)
    created_by = db.relationship('User', lazy=True)

    @property
    def action_label(self) -> str:
        return self.action.replace('_', ' ').title()

    def __repr__(self):
        return f'<LibraryCopyEvent {self.action} copy={self.copy_id}>'


class LibraryAuditSession(db.Model):
    __tablename__ = 'library_audit_sessions'
    __table_args__ = (
        db.Index('ix_library_audit_sessions_college_status_started', 'college_id', 'status', 'started_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    rack_id = db.Column(db.Integer, db.ForeignKey('library_locations.id'), nullable=True, index=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    completed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    title = db.Column(db.String(150), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum(*LIBRARY_AUDIT_STATUSES, name='library_audit_status'), nullable=False, default='open')
    expected_count = db.Column(db.Integer, nullable=False, default=0)
    scanned_count = db.Column(db.Integer, nullable=False, default=0)
    missing_count = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    completed_at = db.Column(db.DateTime, nullable=True)

    rack = db.relationship('LibraryLocation', lazy=True)
    created_by = db.relationship('User', foreign_keys=[created_by_user_id], lazy=True)
    completed_by = db.relationship('User', foreign_keys=[completed_by_user_id], lazy=True)
    entries = db.relationship('LibraryAuditEntry', backref='session', lazy=True, cascade='all, delete-orphan')

    @property
    def progress_percent(self) -> int:
        if self.expected_count <= 0:
            return 0
        return int(round((self.scanned_count / self.expected_count) * 100))

    def __repr__(self):
        return f'<LibraryAuditSession {self.id}>'


class LibraryAuditEntry(db.Model):
    __tablename__ = 'library_audit_entries'
    __table_args__ = (
        db.UniqueConstraint('session_id', 'copy_id', name='uq_library_audit_entries_session_copy'),
        db.Index('ix_library_audit_entries_session_present', 'session_id', 'is_present'),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('library_audit_sessions.id'), nullable=False, index=True)
    copy_id = db.Column(db.Integer, db.ForeignKey('library_book_copies.id'), nullable=False, index=True)
    expected_status = db.Column(db.String(50), nullable=False)
    expected_condition = db.Column(db.String(50), nullable=True)
    is_present = db.Column(db.Boolean, nullable=False, default=False)
    scanned_at = db.Column(db.DateTime, nullable=True)
    scanned_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    discrepancy_status = db.Column(
        db.Enum(*LIBRARY_AUDIT_DISCREPANCY_STATUSES, name='library_audit_discrepancy_status'),
        nullable=False,
        default='unresolved',
    )
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    notes = db.Column(db.Text, nullable=True)

    copy = db.relationship('LibraryBookCopy', lazy=True)
    scanned_by = db.relationship('User', foreign_keys=[scanned_by_user_id], lazy=True)
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_user_id], lazy=True)

    @property
    def discrepancy_label(self) -> str:
        return self.discrepancy_status.replace('_', ' ').title()

    def __repr__(self):
        return f'<LibraryAuditEntry session={self.session_id} copy={self.copy_id}>'


class LibraryLoan(db.Model):
    __tablename__ = 'library_loans'
    __table_args__ = (
        db.Index('ix_library_loans_college_status_due', 'college_id', 'status', 'due_at'),
        db.Index('ix_library_loans_college_student_status', 'college_id', 'student_id', 'status'),
        db.Index('ix_library_loans_college_teacher_status', 'college_id', 'teacher_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    copy_id = db.Column(db.Integer, db.ForeignKey('library_book_copies.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True, index=True)
    issued_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    returned_to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    issued_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    due_at = db.Column(db.DateTime, nullable=False)
    returned_at = db.Column(db.DateTime, nullable=True)
    renewed_count = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.Enum(*LIBRARY_LOAN_STATUSES, name='library_loan_status'), nullable=False, default='active')
    notes = db.Column(db.Text, nullable=True)
    fine_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    student = db.relationship('Student', backref='library_loans', lazy=True)
    teacher = db.relationship('Teacher', backref='library_loans', lazy=True)
    issued_by = db.relationship('User', foreign_keys=[issued_by_user_id], lazy=True)
    returned_to = db.relationship('User', foreign_keys=[returned_to_user_id], lazy=True)
    fine_records = db.relationship('LibraryFine', backref='loan', lazy=True, cascade='all, delete-orphan')

    @property
    def borrower_label(self) -> str:
        if self.student:
            return self.student.user.name
        if self.teacher:
            return self.teacher.user.name
        return 'Unknown borrower'

    @property
    def borrower_role(self) -> str:
        if self.student_id:
            return 'student'
        if self.teacher_id:
            return 'teacher'
        return 'unknown'

    @property
    def is_active(self) -> bool:
        return self.status in {'active', 'overdue'}

    @property
    def outstanding_fine_amount(self):
        return sum(record.outstanding_amount for record in self.fine_records if record.status in {'unpaid', 'partial'})

    def __repr__(self):
        return f'<LibraryLoan {self.id}>'


class LibraryReservation(db.Model):
    __tablename__ = 'library_reservations'
    __table_args__ = (
        db.Index('ix_library_reservations_college_status_created', 'college_id', 'status', 'created_at'),
        db.Index('ix_library_reservations_college_book_status', 'college_id', 'book_id', 'status'),
        db.Index('ix_library_reservations_college_student_status', 'college_id', 'student_id', 'status'),
        db.Index('ix_library_reservations_college_teacher_status', 'college_id', 'teacher_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True, index=True)
    held_copy_id = db.Column(db.Integer, db.ForeignKey('library_book_copies.id'), nullable=True, index=True)
    status = db.Column(db.Enum(*LIBRARY_RESERVATION_STATUSES, name='library_reservation_status'), nullable=False, default='pending')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    ready_at = db.Column(db.DateTime, nullable=True)
    pickup_expires_at = db.Column(db.DateTime, nullable=True)
    fulfilled_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    expired_at = db.Column(db.DateTime, nullable=True)

    student = db.relationship('Student', backref='library_reservations', lazy=True)
    teacher = db.relationship('Teacher', backref='library_reservations', lazy=True)
    held_copy = db.relationship('LibraryBookCopy', foreign_keys=[held_copy_id], lazy=True)

    @property
    def borrower_label(self) -> str:
        if self.student:
            return self.student.user.name
        if self.teacher:
            return self.teacher.user.name
        return 'Unknown borrower'

    @property
    def borrower_role(self) -> str:
        if self.student_id:
            return 'student'
        if self.teacher_id:
            return 'teacher'
        return 'unknown'

    @property
    def is_pending(self) -> bool:
        return self.status == 'pending'

    @property
    def is_active(self) -> bool:
        return self.status in {'pending', 'ready_for_pickup'}

    @property
    def is_ready_for_pickup(self) -> bool:
        return self.status == 'ready_for_pickup'

    def matches_borrower(self, *, student_id: int | None = None, teacher_id: int | None = None) -> bool:
        return bool(
            (student_id and self.student_id == student_id)
            or (teacher_id and self.teacher_id == teacher_id)
        )

    def __repr__(self):
        return f'<LibraryReservation {self.id}>'


class LibraryFine(db.Model):
    __tablename__ = 'library_fines'
    __table_args__ = (
        db.Index('ix_library_fines_college_status_created', 'college_id', 'status', 'created_at'),
        db.Index('ix_library_fines_college_student_status', 'college_id', 'student_id', 'status'),
        db.Index('ix_library_fines_college_teacher_status', 'college_id', 'teacher_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    loan_id = db.Column(db.Integer, db.ForeignKey('library_loans.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True, index=True)
    status = db.Column(db.Enum(*LIBRARY_FINE_STATUSES, name='library_fine_status'), nullable=False, default='unpaid')
    reason = db.Column(db.String(100), nullable=False, default='overdue')
    amount_assessed = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    amount_waived = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)
    settled_at = db.Column(db.DateTime, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    settled_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)

    student = db.relationship('Student', backref='library_fines', lazy=True)
    teacher = db.relationship('Teacher', backref='library_fines', lazy=True)
    book = db.relationship('LibraryBook', lazy=True)
    created_by = db.relationship('User', foreign_keys=[created_by_user_id], lazy=True)
    settled_by = db.relationship('User', foreign_keys=[settled_by_user_id], lazy=True)

    @property
    def borrower_label(self) -> str:
        if self.student:
            return self.student.user.name
        if self.teacher:
            return self.teacher.user.name
        return 'Unknown borrower'

    @property
    def borrower_role(self) -> str:
        if self.student_id:
            return 'student'
        if self.teacher_id:
            return 'teacher'
        return 'unknown'

    @property
    def outstanding_amount(self):
        assessed = self.amount_assessed or 0
        paid = self.amount_paid or 0
        waived = self.amount_waived or 0
        return max(assessed - paid - waived, 0)

    def __repr__(self):
        return f'<LibraryFine {self.id}>'


class LibraryReadingProgress(db.Model):
    __tablename__ = 'library_reading_progress'
    __table_args__ = (
        db.UniqueConstraint('college_id', 'book_id', 'user_id', name='uq_library_reading_progress_user_book'),
        db.Index('ix_library_reading_progress_college_user', 'college_id', 'user_id'),
        db.Index('ix_library_reading_progress_college_book', 'college_id', 'book_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    last_page = db.Column(db.Integer, nullable=True)
    progress_percent = db.Column(db.Numeric(5, 2), nullable=True)
    last_position = db.Column(db.String(255), nullable=True)
    total_pages = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_read_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    user = db.relationship('User', lazy=True)

    def __repr__(self):
        return f'<LibraryReadingProgress user={self.user_id} book={self.book_id}>'


class LibraryAccessLog(db.Model):
    __tablename__ = 'library_access_logs'
    __table_args__ = (
        db.Index('ix_library_access_logs_college_book_action', 'college_id', 'book_id', 'action'),
    )

    id = db.Column(db.Integer, primary_key=True)
    college_id = db.Column(db.Integer, db.ForeignKey('colleges.id'), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey('library_books.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=True, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True, index=True)
    action = db.Column(db.Enum(*LIBRARY_ACCESS_ACTIONS, name='library_access_action'), nullable=False, default='download')
    accessed_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    student = db.relationship('Student', backref='library_access_logs', lazy=True)
    teacher = db.relationship('Teacher', backref='library_access_logs', lazy=True)

    def __repr__(self):
        return f'<LibraryAccessLog {self.book_id}:{self.action}>'
