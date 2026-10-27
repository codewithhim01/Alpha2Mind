"""
Camera_Module.py — Alpha Camera Features
==========================================
Features:
  • take_snapshot()          → saves a photo to ~/Desktop
  • start_face_detection()   → live face + eye detection overlay
  • start_emotion_detect()   → basic emotion estimation (happy/neutral/etc)
  • get_camera_feed()        → returns raw frame for other modules to use
  • stop_camera()            → release camera

How to call from Alpha.py:
    import Camera_Module
    Camera_Module.take_snapshot()
    Camera_Module.start_face_detection()
    Camera_Module.stop_camera()
"""

import cv2
import os
import time
import threading
from datetime import datetime

# ── Paths ─────────────────────────────────────────────────────────────────────
SNAPSHOT_DIR = os.path.expanduser("~/Desktop")
HAAR_DIR = cv2.data.haarcascades  # built-in OpenCV cascade folder

# ── Haar Cascades ──────────────────────────────────────────────────────────────
_face_cascade = cv2.CascadeClassifier(HAAR_DIR + "haarcascade_frontalface_default.xml")
_eye_cascade  = cv2.CascadeClassifier(HAAR_DIR + "haarcascade_eye.xml")
_smile_cascade = cv2.CascadeClassifier(HAAR_DIR + "haarcascade_smile.xml")

# ── Shared state ───────────────────────────────────────────────────────────────
_cap        = None
_running    = False
_last_frame = None
_lock       = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _open_camera(index: int = None) -> bool:
    """Open webcam (auto-detect if index not given)."""
    global _cap

    if _cap and _cap.isOpened():
        return True

    # 🔍 If no index given → auto-detect working camera
    if index is None:
        for i in range(5):  # try first 5 indexes
            cap = cv2.VideoCapture(i)
            if cap.read()[0]:
                print(f"✓ Camera found at index {i}")
                _cap = cap
                break
            cap.release()
        else:
            print("✗ No working camera found.")
            return False
    else:
        _cap = cv2.VideoCapture(index)

    # ⚙️ Optimize performance
    _cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    _cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    _cap.set(cv2.CAP_PROP_FPS, 30)

    if not _cap.isOpened():
        print("✗ Camera_Module: could not open camera.")
        return False

    return True


def _read_frame():
    """Read one frame safely."""
    global _last_frame
    if not _cap or not _cap.isOpened():
        return None
    ok, frame = _cap.read()
    if ok:
        frame = cv2.flip(frame, 1)   # mirror
        with _lock:
            _last_frame = frame.copy()
    return frame if ok else None


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def take_snapshot(prefix: str = "alpha_snap") -> str:
    """
    Capture one frame and save it to ~/Desktop.
    Returns the saved file path.

    Call from Alpha.py:
        path = Camera_Module.take_snapshot()
        reply(f"Photo saved to {path}")
    """
    if not _open_camera():
        return ""
    time.sleep(0.5)          # let camera warm up
    frame = _read_frame()
    if frame is None:
        return ""
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(SNAPSHOT_DIR, f"{prefix}_{ts}.png")
    cv2.imwrite(path, frame)
    print(f"✓ Snapshot saved: {path}")
    return path


def start_face_detection(duration: int = 0):
    """
    Open camera window with real-time face + eye + smile detection overlay.
    duration=0 → runs until user presses ESC.
    duration=N → runs for N seconds then auto-closes.

    Call from Alpha.py:
        Camera_Module.start_face_detection()
    """
    global _running
    if not _open_camera():
        return

    _running = True
    start = time.time()
    print("✓ Face detection started. Press ESC to stop.")

    while _running:
        frame = _read_frame()
        if frame is None:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # ── Face ──────────────────────────────────────────────────────────────
        faces = _face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 210, 180), 2)
            cv2.putText(frame, "Face", (x, y - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 210, 180), 2)

            roi_gray  = gray[y:y+h, x:x+w]
            roi_color = frame[y:y+h, x:x+w]

            # ── Eyes ──────────────────────────────────────────────────────────
            eyes = _eye_cascade.detectMultiScale(roi_gray, 1.1, 6, minSize=(20, 20))
            for (ex, ey, ew, eh) in eyes:
                cv2.rectangle(roi_color, (ex, ey), (ex+ew, ey+eh), (0, 119, 255), 1)

            # ── Smile ─────────────────────────────────────────────────────────
            smiles = _smile_cascade.detectMultiScale(
                roi_gray, 1.7, 20, minSize=(25, 25))
            if len(smiles) > 0:
                cv2.putText(frame, "😊 Smiling", (x, y + h + 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 100), 2)

        # ── HUD ───────────────────────────────────────────────────────────────
        cv2.putText(frame, f"ALPHA  Faces: {len(faces)}", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 210, 180), 2)
        cv2.putText(frame, "ESC to stop", (10, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)

        cv2.imshow("Alpha - Face Detection", frame)

        if cv2.waitKey(1) & 0xFF == 27:   # ESC
            break
        if duration and (time.time() - start) > duration:
            break

    _running = False
    cv2.destroyWindow("Alpha - Face Detection")
    print("✓ Face detection stopped.")


def start_blink_detector():
    """
    Detect eye blinks in real time and print/count them.
    Useful for accessibility — blink to trigger actions.

    Call from Alpha.py:
        Camera_Module.start_blink_detector()
    """
    global _running
    if not _open_camera():
        return

    _running = True
    blink_count   = 0
    eyes_was_open = True
    print("✓ Blink detector started. Press ESC to stop.")

    while _running:
        frame = _read_frame()
        if frame is None:
            break

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = _face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(80, 80))

        eyes_visible = False
        for (x, y, w, h) in faces:
            roi = gray[y:y+h, x:x+w]
            eyes = _eye_cascade.detectMultiScale(roi, 1.1, 6, minSize=(20, 20))
            if len(eyes) >= 2:
                eyes_visible = True

        if eyes_was_open and not eyes_visible:
            blink_count += 1
            print(f"👁 Blink #{blink_count}")
        eyes_was_open = eyes_visible

        cv2.putText(frame, f"Blinks: {blink_count}", (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 210, 180), 2)
        cv2.putText(frame, "ESC to stop", (10, 62),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 80, 80), 1)
        cv2.imshow("Alpha - Blink Detector", frame)

        if cv2.waitKey(1) & 0xFF == 27:
            break

    _running = False
    cv2.destroyWindow("Alpha - Blink Detector")
    print(f"✓ Blink detector stopped. Total blinks: {blink_count}")
    return blink_count


def get_last_frame():
    """
    Return the most recent camera frame (numpy array).
    Other modules (e.g. Gesture_Mouse.py) can call this
    instead of opening the camera a second time.

    Call from Alpha.py or any module:
        frame = Camera_Module.get_last_frame()
    """
    with _lock:
        return _last_frame.copy() if _last_frame is not None else None


def stop_camera():
    """
    Release the camera and close all windows.

    Call from Alpha.py:
        Camera_Module.stop_camera()
    """
    global _running, _cap
    _running = False
    time.sleep(0.2)
    if _cap:
        _cap.release()
        _cap = None
    cv2.destroyAllWindows()
    print("✓ Camera released.")


# ── Run standalone for testing ────────────────────────────────────────────────
if __name__ == "__main__":
    print("Testing Camera_Module...")
    start_face_detection()
