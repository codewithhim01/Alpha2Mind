"""
Gesture_Mouse.py — Alpha Gesture Mouse + Air Typing
Compatible with MediaPipe 0.10+ (mp.tasks API)

MOUSE GESTURES:
  ✌️  V-sign              → Move cursor
  ✊  Fist                 → Drag
  ☝️  Index only           → Left click
  🤘  Index + Pinky        → Right click
  🤙  Thumb + Pinky        → Double click
  🖐  Open palm            → Scroll
  Pinch                   → Scroll wheel

AIR TYPING:
  Virtual QWERTY keyboard overlaid on camera feed.
  Pinch (thumb+index) over a key → types that letter.
  Press T in the camera window to switch modes.

Call from Alpha.py:
    import Gesture_Mouse
    Gesture_Mouse.start_mouse_control()   # background thread
    Gesture_Mouse.start_air_typing()      # background thread
    Gesture_Mouse.stop()
    text = Gesture_Mouse.get_typed_text()
"""

import cv2, math, time, os, threading, urllib.request
import numpy as np
import pyautogui
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

# ── Indices ───────────────────────────────────────────────────────────────────
T_TIP,T_IP  = 4,3
I_TIP,I_PIP = 8,6
M_TIP,M_PIP = 12,10
R_TIP,R_PIP = 16,14
P_TIP,P_PIP = 20,18
WRIST       = 0

# ── Config ────────────────────────────────────────────────────────────────────
CAM_W,CAM_H   = 640,480
SMOOTH        = 0.25
PINCH_D       = 0.06
CLICK_CD      = 0.38
KEY_CD        = 0.35

# ── Keyboard layout ───────────────────────────────────────────────────────────
KB = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM") + ["SPC","⌫"],
]
KW,KH,KX0,KY0 = 56,52,8,50

# ── State ─────────────────────────────────────────────────────────────────────
_running      = False
_mode         = "mouse"
_text         = ""
_px,_py       = 0,0
_drag         = False
_lct          = 0           # last click time
_lkt          = 0           # last key time
_lfk          = None        # last fired key


def _up(lms):
    return (lms[T_TIP].x<lms[T_IP].x,
            lms[I_TIP].y<lms[I_PIP].y,
            lms[M_TIP].y<lms[M_PIP].y,
            lms[R_TIP].y<lms[R_PIP].y,
            lms[P_TIP].y<lms[P_PIP].y)

def _d(a,b): return math.hypot(a.x-b.x,a.y-b.y)
def _sm(p,c): return int(p*(1-SMOOTH)+c*SMOOTH)
def _pinch(lms): return _d(lms[T_TIP],lms[I_TIP])<PINCH_D
def _px_coord(lm,W=CAM_W,H=CAM_H): return int(lm.x*W),int(lm.y*H)


# ── MOUSE handler ─────────────────────────────────────────────────────────────
def _mouse(lms,frame):
    global _px,_py,_drag,_lct
    th,ix,mx,rx,px = _up(lms)
    now = time.time()
    sw,sh = pyautogui.size()
    nx = _sm(_px,int(lms[I_TIP].x*sw))
    ny = _sm(_py,int(lms[I_TIP].y*sh))
    _px,_py = nx,ny
    fx,fy = _px_coord(lms[I_TIP])

    if ix and mx and not rx and not px:
        pyautogui.moveTo(nx,ny,duration=0)
        lbl,col = "MOVE",(0,210,180)
    elif not any((ix,mx,rx,px)):
        if not _drag: pyautogui.mouseDown(); _drag=True
        pyautogui.moveTo(nx,ny,duration=0)
        lbl,col = "DRAG",(0,80,255)
    elif ix and not mx and not rx and not px:
        if _drag: pyautogui.mouseUp(); _drag=False
        if now-_lct>CLICK_CD: pyautogui.click(); _lct=now
        lbl,col = "CLICK",(0,255,120)
    elif ix and px and not mx and not rx:
        if now-_lct>CLICK_CD: pyautogui.rightClick(); _lct=now
        lbl,col = "R-CLICK",(255,100,0)
    elif th and px and not ix and not mx:
        if now-_lct>CLICK_CD: pyautogui.doubleClick(); _lct=now
        lbl,col = "DBL",(200,0,200)
    elif all((th,ix,mx,rx,px)):
        pyautogui.scroll(15 if lms[WRIST].y<0.45 else -15)
        lbl,col = "SCROLL",(255,200,0)
    elif _pinch(lms):
        mid_y=(lms[T_TIP].y+lms[I_TIP].y)/2
        pyautogui.scroll(12 if mid_y<0.5 else -12)
        lbl,col = "P-SCROLL",(0,180,255)
    else:
        if _drag: pyautogui.mouseUp(); _drag=False
        lbl,col = "—",(60,60,60)

    cv2.circle(frame,(fx,fy),11,col,-1)
    cv2.putText(frame,lbl,(fx+14,fy),cv2.FONT_HERSHEY_SIMPLEX,0.5,col,2)


# ── KEYBOARD handler ──────────────────────────────────────────────────────────
def _key_rect(r,c,key):
    w = KW*2+4 if key in("SPC","⌫") else KW
    return KX0+c*(KW+4), KY0+r*(KH+4), KX0+c*(KW+4)+w, KY0+r*(KH+4)+KH

def _hovered(px,py):
    for r,row in enumerate(KB):
        for c,key in enumerate(row):
            x1,y1,x2,y2 = _key_rect(r,c,key)
            if x1<=px<=x2 and y1<=py<=y2: return r,c,key
    return None

def _draw_kb(frame,hov,pinching):
    ov = frame.copy()
    for r,row in enumerate(KB):
        for c,key in enumerate(row):
            x1,y1,x2,y2 = _key_rect(r,c,key)
            is_h = hov and hov[2]==key
            bg = (50,120,80) if (is_h and pinching) else (40,80,80) if is_h else (18,22,36)
            cv2.rectangle(ov,(x1,y1),(x2,y2),bg,-1)
            cv2.rectangle(ov,(x1,y1),(x2,y2),(0,210,180) if is_h else (50,60,90),1)
            lbl = key if key in("SPC","⌫") else key.lower()
            fs = 0.38 if key in("SPC","⌫") else 0.52
            tw,th2 = cv2.getTextSize(lbl,cv2.FONT_HERSHEY_SIMPLEX,fs,1)[0]
            cv2.putText(ov,lbl,(x1+(x2-x1-tw)//2,y1+(y2-y1+th2)//2),
                        cv2.FONT_HERSHEY_SIMPLEX,fs,(0,210,180) if is_h else (200,200,200),1)
    cv2.addWeighted(ov,0.82,frame,0.18,0,frame)

def _typing(lms,frame):
    global _text,_lkt,_lfk
    now = time.time()
    pinching = _pinch(lms)
    mx,my = _px_coord(lms[I_TIP])
    hov = _hovered(mx,my)
    _draw_kb(frame,hov,pinching)
    cv2.circle(frame,(mx,my),10,(0,255,100) if pinching else (0,180,255),-1)

    if pinching and hov and (hov[2]!=_lfk or now-_lkt>0.55) and now-_lkt>KEY_CD:
        key = hov[2]
        if key=="⌫":
            _text=_text[:-1]; pyautogui.press("backspace")
        elif key=="SPC":
            _text+=" "; pyautogui.press("space")
        else:
            _text+=key.lower(); pyautogui.typewrite(key.lower(),interval=0.01)
        _lfk=key; _lkt=now
    elif not pinching: _lfk=None

    cv2.rectangle(frame,(0,CAM_H-55),(CAM_W,CAM_H-55+40),(12,14,24),-1)
    cv2.putText(frame,f"> {_text[-60:]}|",(8,CAM_H-28),
                cv2.FONT_HERSHEY_SIMPLEX,0.55,(0,210,180),1)


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def _loop():
    global _running, _mode, _drag

    _get_model()
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,CAM_H)
    cap.set(cv2.CAP_PROP_FPS,30)
    if not cap.isOpened():
        print("✗ Gesture_Mouse: cannot open camera"); _running=False; return

    opts = mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_tracking_confidence=0.6,
        running_mode=mp_vision.RunningMode.VIDEO,
    )
    print("✓ Gesture Mouse live — ESC=stop, T=toggle mode")
    ts = 0
    with mp_vision.HandLandmarker.create_from_options(opts) as det:
        while _running:
            ok,frame = cap.read()
            if not ok: continue
            frame = cv2.flip(frame,1); ts+=33
            img = mp.Image(image_format=mp.ImageFormat.SRGB,
                           data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            res = det.detect_for_video(img,ts)

            if res.hand_landmarks:
                lms = res.hand_landmarks[0]
                # draw skeleton
                conns = [(0,1),(1,2),(2,3),(3,4),
                         (0,5),(5,6),(6,7),(7,8),
                         (0,9),(9,10),(10,11),(11,12),
                         (0,13),(13,14),(14,15),(15,16),
                         (0,17),(17,18),(18,19),(19,20),
                         (5,9),(9,13),(13,17)]
                for a,b in conns:
                    ax,ay=_px_coord(lms[a]); bx,by=_px_coord(lms[b])
                    cv2.line(frame,(ax,ay),(bx,by),(0,119,255),1)
                for l in lms:
                    cv2.circle(frame,_px_coord(l),4,(0,210,180),-1)

                if _mode=="mouse":   _mouse(lms,frame)
                else:                _typing(lms,frame)

            mc = (0,210,180) if _mode=="mouse" else (255,180,0)
            cv2.putText(frame,f"ALPHA [{_mode.upper()}]  T=toggle ESC=stop",
                        (8,26),cv2.FONT_HERSHEY_SIMPLEX,0.48,mc,1)
            cv2.imshow("Alpha - Gesture Mouse",frame)

            k = cv2.waitKey(1)&0xFF
            if k==27: break
            if k in(ord("t"),ord("T")):
                _mode = "typing" if _mode=="mouse" else "mouse"

    _running=False
    if _drag: pyautogui.mouseUp()
    cap.release(); cv2.destroyAllWindows()
    print("✓ Gesture_Mouse stopped.")


# ── PUBLIC API ────────────────────────────────────────────────────────────────
def start_mouse_control():
    global _running,_mode
    if _running: _mode="mouse"; return
    _mode="mouse"; _running=True
    threading.Thread(target=_loop,daemon=True).start()
    print("✓ Gesture mouse started.")

def start_air_typing():
    global _running,_mode,_text
    if _running: _mode="typing"; _text=""; return
    _mode="typing"; _text=""; _running=True
    threading.Thread(target=_loop,daemon=True).start()
    print("✓ Air typing started.")

def set_mode(m):
    global _mode
    if m in("mouse","typing"): _mode=m

def stop():
    global _running
    _running=False; time.sleep(0.3)
    print("✓ Gesture_Mouse stopped.")

def get_typed_text(): return _text
def clear_typed_text():
    global _text; _text=""

if __name__=="__main__":
    start_mouse_control()
    try:
        while _running: time.sleep(0.5)
    except KeyboardInterrupt:
        stop()
