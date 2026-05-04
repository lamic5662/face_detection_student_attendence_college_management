import os


CONTENT_RELATIVE_PREFIX = 'uploads/content/'


def build_content_relpath(filename: str) -> str:
    return f'{CONTENT_RELATIVE_PREFIX}{filename}'


def is_valid_content_relpath(rel_path: str | None) -> bool:
    return bool(rel_path) and '..' not in rel_path and rel_path.startswith(CONTENT_RELATIVE_PREFIX)


def resolve_content_path(app, rel_path: str | None) -> str | None:
    if not is_valid_content_relpath(rel_path):
        return None

    content_dir = os.path.abspath(app.config['CONTENT_UPLOAD_FOLDER'])
    filename = os.path.basename(rel_path)
    abs_path = os.path.abspath(os.path.join(content_dir, filename))

    if os.path.commonpath([content_dir, abs_path]) != content_dir:
        return None
    return abs_path
