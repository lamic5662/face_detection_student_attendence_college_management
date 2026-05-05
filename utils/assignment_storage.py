import os


ASSIGNMENT_SUBMISSION_RELATIVE_PREFIX = 'uploads/submissions/'


def build_submission_relpath(filename: str) -> str:
    return f'{ASSIGNMENT_SUBMISSION_RELATIVE_PREFIX}{filename}'


def is_valid_submission_relpath(rel_path: str | None) -> bool:
    return bool(rel_path) and '..' not in rel_path and rel_path.startswith(ASSIGNMENT_SUBMISSION_RELATIVE_PREFIX)


def resolve_submission_path(app, rel_path: str | None) -> str | None:
    if not is_valid_submission_relpath(rel_path):
        return None

    upload_dir = os.path.abspath(app.config['ASSIGNMENT_UPLOAD_FOLDER'])
    filename = os.path.basename(rel_path)
    abs_path = os.path.abspath(os.path.join(upload_dir, filename))

    if os.path.commonpath([upload_dir, abs_path]) != upload_dir:
        return None
    return abs_path
