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
    try:
        import qrcode
        card_no = (card.card_number if card and card.card_number
                   else f"{student.department.code}-{student.roll_number}")
        lines = [
            f"Name: {student.user.name}",
            f"Roll: {student.roll_number}",
            f"Dept: {student.department.name}",
            f"Card: {card_no}",
        ]
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8, border=2,
        )
        qr.add_data('\n'.join(lines))
        qr.make(fit=True)
        img = qr.make_image(fill_color='#1a1a2e', back_color='white')
        buf = io.BytesIO()
        img.save(buf, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None
