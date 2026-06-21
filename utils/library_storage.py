import os


LIBRARY_RELATIVE_PREFIX = 'uploads/library/'


def build_library_relpath(filename: str) -> str:
    return f'{LIBRARY_RELATIVE_PREFIX}{filename}'


def is_valid_library_relpath(rel_path: str | None) -> bool:
    return bool(rel_path) and '..' not in rel_path and rel_path.startswith(LIBRARY_RELATIVE_PREFIX)


def library_storage_dirs(app) -> list[str]:
    dirs = [os.path.abspath(app.config['LIBRARY_UPLOAD_FOLDER'])]
    legacy_dir = os.path.abspath(os.path.join(app.root_path, 'static', 'uploads', 'library'))
    if legacy_dir not in dirs:
        dirs.append(legacy_dir)
    return dirs


def resolve_library_path(app, rel_path: str | None) -> str | None:
    if not is_valid_library_relpath(rel_path):
        return None

    filename = os.path.basename(rel_path)
    for library_dir in library_storage_dirs(app):
        abs_path = os.path.abspath(os.path.join(library_dir, filename))
        if os.path.commonpath([library_dir, abs_path]) != library_dir:
            continue
        if os.path.isfile(abs_path):
            return abs_path

    primary_dir = os.path.abspath(app.config['LIBRARY_UPLOAD_FOLDER'])
    abs_path = os.path.abspath(os.path.join(primary_dir, filename))
    if os.path.commonpath([primary_dir, abs_path]) != primary_dir:
        return None
    return abs_path
