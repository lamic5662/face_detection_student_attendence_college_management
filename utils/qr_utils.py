import io, base64, math, functools


@functools.lru_cache(maxsize=32)
def _fetch_tile_cached(z, x, y):
    """Fetch one OSM tile and cache it in memory as a base64 data URI."""
    try:
        import requests as req
        url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        r = req.get(url, timeout=6,
                    headers={'User-Agent': 'SmartAttendance/1.0 (educational)'})
        if r.status_code == 200:
            return 'data:image/png;base64,' + base64.b64encode(r.content).decode()
    except Exception:
        pass
    return None


def get_map_tile_b64(lat, lng, zoom=16):
    """Return an OSM map tile as a base64 PNG data URI (server-side, cached)."""
    try:
        n = 2 ** zoom
        x = int((lng + 180) / 360 * n)
        lat_rad = math.radians(lat)
        y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
        return _fetch_tile_cached(zoom, x, y)
    except Exception:
        return None


def make_id_card_qr(student, card):
    """Return a base64 PNG data URI for the student's ID card QR code."""
    card_no = (card.card_number if card and card.card_number
               else f"{student.department.code}-{student.roll_number}")
    lines = [
        f"Name: {student.user.name}",
        f"Roll: {student.roll_number}",
        f"Dept: {student.department.name}",
        f"Card: {card_no}",
    ]
    return make_qr_data_uri(lines)


def make_qr_data_uri(lines, *, fill_color='#1a1a2e', back_color='white', box_size=8, border=2):
    """Return a base64 PNG data URI for generic QR payload lines."""
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size, border=border,
        )
        qr.add_data('\n'.join(lines))
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill_color, back_color=back_color)
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def make_library_copy_qr(copy):
    """QR payload for a physical library copy label."""
    lines = [
        f"Type: Library Copy",
        f"Title: {copy.book.title}",
        f"Accession: {copy.accession_number}",
        f"Barcode: {copy.barcode or copy.accession_number}",
        f"Location: {copy.location_label}",
    ]
    return make_qr_data_uri(lines, fill_color='#0d6efd')


def make_library_borrower_qr(*, name, scan_value, borrower_type, department=None, semester=None):
    """QR payload for a borrower card used at the library circulation desk."""
    lines = [
        "Type: Library Borrower",
        f"Name: {name}",
        f"Role: {borrower_type.title()}",
        f"Scan: {scan_value}",
    ]
    if department:
        lines.append(f"Department: {department}")
    if semester:
        lines.append(f"Semester: {semester}")
    return make_qr_data_uri(lines, fill_color='#198754')
