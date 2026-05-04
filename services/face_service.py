import face_recognition
import cv2
import numpy as np
import base64
import os
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)


def decode_base64_image(data_url: str) -> np.ndarray | None:
    """Decode a base64 data URL into an OpenCV BGR image."""
    try:
        if ',' in data_url:
            data_url = data_url.split(',', 1)[1]
        img_bytes = base64.b64decode(data_url)
        pil_image = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
    except Exception as e:
        logger.error(f"decode_base64_image error: {e}")
        return None


def extract_face_encoding(image: np.ndarray) -> np.ndarray | None:
    """Return the first face encoding found in an image, or None."""
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb, model='hog')
    if not locations:
        return None
    encodings = face_recognition.face_encodings(rgb, locations)
    return encodings[0] if encodings else None


def extract_face_encoding_from_path(image_path: str) -> np.ndarray | None:
    try:
        img = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(img)
        return encodings[0] if encodings else None
    except Exception as e:
        logger.error(f"extract_face_encoding_from_path error: {e}")
        return None


def average_encodings(encoding_list: list) -> np.ndarray | None:
    """Average multiple face encodings to improve robustness."""
    if not encoding_list:
        return None
    return np.mean(encoding_list, axis=0)


def recognize_faces(frame: np.ndarray, known_encodings: list, known_student_ids: list,
                    tolerance: float = 0.5) -> list[dict]:
    """
    Returns a list of dicts for each detected face:
      { 'student_id': int|None, 'confidence': float, 'location': tuple }
    """
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    locations = face_recognition.face_locations(rgb, model='hog')
    if not locations:
        return []

    encodings = face_recognition.face_encodings(rgb, locations)
    results = []

    for encoding, location in zip(encodings, locations):
        if not known_encodings:
            results.append({'student_id': None, 'confidence': 0.0, 'location': location})
            continue

        distances = face_recognition.face_distance(known_encodings, encoding)
        best_idx = int(np.argmin(distances))
        best_dist = float(distances[best_idx])
        confidence = round(1.0 - best_dist, 4)

        if best_dist <= tolerance:
            results.append({
                'student_id': known_student_ids[best_idx],
                'confidence': confidence,
                'location': location,
            })
        else:
            results.append({'student_id': None, 'confidence': confidence, 'location': location})

    return results


def save_face_image(image: np.ndarray, student_roll: str, upload_folder: str) -> str:
    """Save face image to disk; return relative path."""
    os.makedirs(upload_folder, exist_ok=True)
    filename = f"{student_roll}.jpg"
    path = os.path.join(upload_folder, filename)
    cv2.imwrite(path, image)
    return f"uploads/faces/{filename}"
