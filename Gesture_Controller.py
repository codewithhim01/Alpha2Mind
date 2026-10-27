"""
Gesture_Controller.py — Alpha Full Gesture Mouse Controller
Compatible with MediaPipe 0.10+ (mp.tasks API)

Gestures:
  ✌️  V-sign (index+middle)     → Move cursor
  ✊  Fist                       → Click + Drag
  ☝️  Index only                 → Left click
  🤘  Index + Pinky              → Right click
  🤙  Thumb + Pinky              → Double click
  🖐  All fingers open           → Scroll
  Pinch (thumb+index close)     → Volume control

Call from Alpha.py:
    import Gesture_Controller
    gc = Gesture_Controller.GestureController()
    gc.start()                  # blocks — run in a process
"""

import cv2, math, time, os, urllib.request, pyautogui
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

pyautogui.FAILSAFE = False

# ── Model ─────────────────────────────────────────────────────────────────────
MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
MODEL_PATH = os.path.expanduser("~/.alpha_hand_landmarker.task")

def _get_model():
    if not os.path.exists(MODEL_PATH):
        print("Downloading hand model (~8MB)…")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("✓ Model ready")

# ── Landmark IDs ──────────────────────────────────────────────────────────────
T_TIP,T_IP   = 4,3
I_TIP,I_PIP  = 8,6
M_TIP,M_PIP  = 12,10
R_TIP,R_PIP  = 16,14
P_TIP,P_PIP  = 20,18
WRIST        = 0

CLICK_CD    = 0.4
SMOOTH      = 0.25
px_,py_     = 0,0
dragging_   = False
last_click_ = 0

def _up(lms):
    return (
        lms[T_TIP].x < lms[T_IP].x,
        lms[I_TIP].y < lms[I_PIP].y,
        lms[M_TIP].y < lms[M_PIP].y,
        lms[R_TIP].y < lms[R_PIP].y,
        lms[P_TIP].y < lms[P_PIP].y,
    )

def _sm(p,c): return int(p*(1-SMOOTH)+c*SMOOTH)
def _d(a,b):  return math.hypot(a.x-b.x, a.y-b.y)

def _act(lms):
    global px_,py_,dragging_,last_click_
    th,ix,mx,rx,px = _up(lms)
    now = time.time()
    sw,sh = pyautogui.size()
    nx = _sm(px_, int(lms[I_TIP].x*sw))
    ny = _sm(py_, int(lms[I_TIP].y*sh))
    px_,py_ = nx,ny

    if ix and mx and not rx and not px:        # V → move
        pyautogui.moveTo(nx,ny,duration=0)
        return "MOVE",(0,210,180)
    if not any((ix,mx,rx,px)):                 # fist → drag
        if not dragging_: pyautogui.mouseDown(); dragging_=True
        pyautogui.moveTo(nx,ny,duration=0)
        return "DRAG",(0,80,255)
    if ix and not mx and not rx and not px:    # index → click
        if dragging_: pyautogui.mouseUp(); dragging_=False
        if now-last_click_>CLICK_CD: pyautogui.click(); last_click_=now
        return "L-CLICK",(0,255,120)
    if ix and px and not mx and not rx:        # index+pinky → right
        if now-last_click_>CLICK_CD: pyautogui.rightClick(); last_click_=now
        return "R-CLICK",(255,100,0)
    if th and px and not ix and not mx and not rx:  # thumb+pinky → dbl
        if now-last_click_>CLICK_CD: pyautogui.doubleClick(); last_click_=now
        return "DBL",(200,0,200)
    if all((th,ix,mx,rx,px)):                  # open palm → scroll
        pyautogui.scroll(15 if lms[WRIST].y<0.45 else -15)
        return "SCROLL",(255,200,0)
    if dragging_: pyautogui.mouseUp(); dragging_=False
    return "—",(80,80,80)


class GestureController:
    def __init__(self):
        _get_model()
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self.cap.isOpened():
            print("✗ Cannot open camera")

    def start(self):
        opts = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
            num_hands=2,
            min_hand_detection_confidence=0.6,
            min_tracking_confidence=0.5,
            running_mode=mp_vision.RunningMode.VIDEO,
        )
        with mp_vision.HandLandmarker.create_from_options(opts) as det:
            print("✓ Gesture Controller live — ESC to stop")
            ts = 0
            while self.cap.isOpened():
                ok,frame = self.cap.read()
                if not ok: continue
                frame = cv2.flip(frame,1); ts+=33
                img = mp.Image(image_format=mp.ImageFormat.SRGB,
                               data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
                res = det.detect_for_video(img,ts)
                if res.hand_landmarks:
                    lms = res.hand_landmarks[0]
                    lbl,col = _act(lms)
                    for l in lms:
                        cv2.circle(frame,(int(l.x*640),int(l.y*480)),4,(0,210,180),-1)
                    cv2.putText(frame,lbl,(10,60),cv2.FONT_HERSHEY_SIMPLEX,0.9,col,2)
                cv2.putText(frame,"ALPHA Gesture",(10,28),cv2.FONT_HERSHEY_SIMPLEX,0.6,(0,210,180),2)
                cv2.imshow("Alpha - Gesture Controller",frame)
                if cv2.waitKey(1)&0xFF==27: break
        self.cap.release(); cv2.destroyAllWindows()

if __name__=="__main__":
    GestureController().start()
