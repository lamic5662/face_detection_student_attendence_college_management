"""
Eye-blink liveness detection using dlib 68-point facial landmarks.
EAR (Eye Aspect Ratio) drops sharply during a blink.
"""
import dlib
import cv2
import numpy as np
from scipy.spatial import distance as dist
import os
import logging
import threading
import time

logger = logging.getLogger(__name__)

# dlib landmark indices for each eye
LEFT_EYE_IDX  = list(range(36, 42))
RIGHT_EYE_IDX = list(range(42, 48))

EAR_BLINK_THRESHOLD = 0.25   # EAR below this = eye closed
EAR_CONSEC_FRAMES   = 2      # frames eye must stay closed to count as blink

_detector = None
_predictor = None

PREDICTOR_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'models_data', 'shape_predictor_68_face_landmarks.dat'
)


def _load_models():
    global _detector, _predictor
    if _detector is None:
        _detector = dlib.get_frontal_face_detector()
    if _predictor is None:
        if not os.path.exists(PREDICTOR_PATH):
            raise FileNotFoundError(
                f"dlib predictor not found at {PREDICTOR_PATH}.\n"
                "Download from: http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2\n"
                "Extract and place in models_data/ folder."
            )
        _predictor = dlib.shape_predictor(PREDICTOR_PATH)


def _eye_aspect_ratio(eye_points: np.ndarray) -> float:
    A = dist.euclidean(eye_points[1], eye_points[5])
    B = dist.euclidean(eye_points[2], eye_points[4])
    C = dist.euclidean(eye_points[0], eye_points[3])
    return (A + B) / (2.0 * C)


def _shape_to_np(shape, dtype='int') -> np.ndarray:
    coords = np.zeros((68, 2), dtype=dtype)
    for i in range(68):
        coords[i] = (shape.part(i).x, shape.part(i).y)
    return coords


def process_frame_for_liveness(
    frame: np.ndarray,
    session_state: dict,
    face_location: tuple | None = None
) -> dict:
    """
    Analyse a single frame for eye blinks.

    session_state keys maintained across calls per face:
        ear_counter  – consecutive frames with closed eye
        blink_count  – total blinks detected
        verified     – True once REQUIRED_BLINKS achieved

    Returns:
        { 'ear': float, 'blink_count': int, 'verified': bool, 'error': str|None }
    """
    result = {
        'ear': 0.0,
        'blink_count': session_state.get('blink_count', 0),
        'verified': session_state.get('verified', False),
        'error': None,
    }

    if result['verified']:
        return result

    try:
        _load_models()
    except FileNotFoundError as e:
        result['error'] = str(e)
        return result

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if face_location:
        top, right, bottom, left = face_location
        dlib_rect = dlib.rectangle(left, top, right, bottom)
        faces = [dlib_rect]
    else:
        faces = _detector(gray, 0)

    if not faces:
        return result

    shape = _predictor(gray, faces[0])
    coords = _shape_to_np(shape)

    left_eye  = coords[LEFT_EYE_IDX]
    right_eye = coords[RIGHT_EYE_IDX]
    ear = (_eye_aspect_ratio(left_eye) + _eye_aspect_ratio(right_eye)) / 2.0

    result['ear'] = round(float(ear), 4)

    ear_counter = session_state.get('ear_counter', 0)

    if ear < EAR_BLINK_THRESHOLD:
        ear_counter += 1
    else:
        if ear_counter >= EAR_CONSEC_FRAMES:
            result['blink_count'] += 1
        ear_counter = 0

    session_state['ear_counter'] = ear_counter
    session_state['blink_count'] = result['blink_count']

    if result['blink_count'] >= 1:
        result['verified'] = True
        session_state['verified'] = True

    return result


class LivenessSessionManager:
    """Thread-safe in-memory state for liveness sessions."""

    def __init__(self, ttl_seconds: int = 600):
        self._sessions: dict[str, dict] = {}
        self._ttl_seconds = max(int(ttl_seconds), 60)
        self._lock = threading.Lock()

    def configure(self, ttl_seconds: int):
        with self._lock:
            self._ttl_seconds = max(int(ttl_seconds), 60)

    def _prune_expired_locked(self):
        now = time.monotonic()
        expired = [
            key for key, state in self._sessions.items()
            if now - state.get('_touched_at', now) > self._ttl_seconds
        ]
        for key in expired:
            self._sessions.pop(key, None)

    def get_state(self, key: str) -> dict:
        with self._lock:
            self._prune_expired_locked()
            if key not in self._sessions:
                self._sessions[key] = {
                    'ear_counter': 0,
                    'blink_count': 0,
                    'verified': False,
                }
            self._sessions[key]['_touched_at'] = time.monotonic()
            return self._sessions[key]

    def reset(self, key: str):
        with self._lock:
            self._sessions.pop(key, None)

    def is_verified(self, key: str) -> bool:
        with self._lock:
            self._prune_expired_locked()
            state = self._sessions.get(key)
            if state:
                state['_touched_at'] = time.monotonic()
                return state.get('verified', False)
            return False

    def cleanup_session(self, session_id: int):
        with self._lock:
            keys = [k for k in self._sessions if k.startswith(f"{session_id}_")]
            for key in keys:
                self._sessions.pop(key, None)


liveness_manager = LivenessSessionManager()
