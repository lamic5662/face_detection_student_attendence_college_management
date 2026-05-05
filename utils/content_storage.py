import os


CONTENT_RELATIVE_PREFIX = 'uploads/content/'


def build_content_relpath(filename: str) -> str:
    return f'{CONTENT_RELATIVE_PREFIX}{filename}'


def is_valid_content_relpath(rel_path: str | None) -> bool:
    return bool(rel_path) and '..' not in rel_path and rel_path.startswith(CONTENT_RELATIVE_PREFIX)


def content_storage_dirs(app) -> list[str]:
    dirs = [os.path.abspath(app.config['CONTENT_UPLOAD_FOLDER'])]
    legacy_dir = os.path.abspath(os.path.join(app.root_path, 'static', 'uploads', 'content'))
    if legacy_dir not in dirs:
        dirs.append(legacy_dir)
    return dirs


def resolve_content_path(app, rel_path: str | None) -> str | None:
    if not is_valid_content_relpath(rel_path):
        return None

    filename = os.path.basename(rel_path)
    for content_dir in content_storage_dirs(app):
        abs_path = os.path.abspath(os.path.join(content_dir, filename))
        if os.path.commonpath([content_dir, abs_path]) != content_dir:
            continue
        if os.path.isfile(abs_path):
            return abs_path

    primary_dir = os.path.abspath(app.config['CONTENT_UPLOAD_FOLDER'])
    abs_path = os.path.abspath(os.path.join(primary_dir, filename))
    if os.path.commonpath([primary_dir, abs_path]) != primary_dir:
        return None
    return abs_path
