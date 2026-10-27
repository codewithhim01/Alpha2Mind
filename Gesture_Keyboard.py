"""
Gesture_Keyboard.py — Alpha Gesture Keyboard System
Compatible with MediaPipe 0.10+ (mp.tasks API)

MODES (press M in camera window to cycle):
  1. keyboard    — pinch over QWERTY key to type
  2. swipe       — swipe index finger to type by direction+zone
  3. fingerspell — hold finger combo (ASL-inspired) = letter
  4. shortcut    — hand poses fire macOS keyboard shortcuts

Call from Alpha.py:
    import Gesture_Keyboard
    Gesture_Keyboard.start_keyboard()
    Gesture_Keyboard.start_swipe_mode()
    Gesture_Keyboard.start_fingerspell_mode()
    Gesture_Keyboard.start_shortcut_mode()
    Gesture_Keyboard.stop()
    Gesture_Keyboard.get_text()
    Gesture_Keyboard.set_mode("swipe")
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

# ── Config ────────────────────────────────────────────────────────────────────
CAM_W,CAM_H  = 960,540
PINCH_D      = 0.06
HOLD_FRAMES  = 8
KEY_CD       = 0.35
SWIPE_MIN    = 70

C_TEAL  = (0,210,180)
C_BLUE  = (0,119,255)
C_WHITE = (230,230,230)
C_DARK  = (18,22,36)
C_GREEN = (50,220,80)
C_GREY  = (80,80,80)
C_RED   = (60,60,255)
C_YEL   = (0,200,255)

# ── Keyboard ──────────────────────────────────────────────────────────────────
KB = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
    ["SPACE","BACK","ENTER","CLEAR"],
]
KW,KH,KX0,KY0 = 76,62,22,44

# ── Finger spell map ──────────────────────────────────────────────────────────
SPELL = {
    (0,1,0,0,0):"A",(0,1,1,0,0):"B",(0,1,1,1,0):"C",(0,1,1,1,1):"D",
    (0,0,0,0,0):"E",(0,1,0,0,1):"F",(1,0,0,0,1):"G",(1,1,0,0,0):"H",
    (0,0,0,0,1):"I",(1,0,0,0,0):"J",(1,1,1,0,0):"K",(1,1,1,1,0):"L",
    (1,1,1,1,1):"M",(0,0,1,0,0):"N",(0,0,1,1,0):"O",(0,0,1,1,1):"P",
    (1,0,1,0,0):"Q",(1,0,1,1,0):"R",(1,0,1,1,1):"S",(0,1,0,1,0):"T",
    (0,1,0,1,1):"U",(0,0,0,1,0):"Y",(0,0,0,1,1):"Z",
}

# ── Shortcut map ──────────────────────────────────────────────────────────────
SHORTCUTS = {
    (0,0,0,0,0):(["command","c"],  "COPY"),
    (1,1,1,1,1):(["command","v"],  "PASTE"),
    (0,1,1,0,0):(["command","z"],  "UNDO"),
    (0,1,1,1,0):(["command","s"],  "SAVE"),
    (0,1,1,1,1):(["command","a"],  "SELECT ALL"),
    (1,0,0,0,0):(["command","t"],  "NEW TAB"),
    (0,0,0,0,1):(["command","w"],  "CLOSE TAB"),
    (0,1,0,0,0):(["command","x"],  "CUT"),
}

# ── State ─────────────────────────────────────────────────────────────────────
_running   = False
_mode      = "keyboard"
_buf       = ""
_caps      = False
_out       = True        # type into active app
_lkt       = 0
_lfk       = None
_MODES     = ["keyboard","swipe","fingerspell","shortcut"]


def _up(lms):
    return (int(lms[T_TIP].x<lms[T_IP].x),
            int(lms[I_TIP].y<lms[I_PIP].y),
            int(lms[M_TIP].y<lms[M_PIP].y),
            int(lms[R_TIP].y<lms[R_PIP].y),
            int(lms[P_TIP].y<lms[P_PIP].y))

def _d(a,b): return math.hypot(a.x-b.x,a.y-b.y)
def _pinch(lms): return _d(lms[T_TIP],lms[I_TIP])<PINCH_D
def _coord(lm,W=CAM_W,H=CAM_H): return int(lm.x*W),int(lm.y*H)

def _type(ch):
    global _buf
    _buf+=ch
    if _out:
        try: pyautogui.typewrite(ch,interval=0.01)
        except: pass

def _press(k):
    if _out:
        try: pyautogui.press(k)
        except: pass

def _hotkey(*k):
    if _out:
        try: pyautogui.hotkey(*k)
        except: pass


# ── KEY RECT ──────────────────────────────────────────────────────────────────
def _krect(r,c,key):
    w = KW*2+4 if key in("SPACE","BACK","ENTER","CLEAR") else KW
    return KX0+c*(KW+4),KY0+r*(KH+4),KX0+c*(KW+4)+w,KY0+r*(KH+4)+KH

def _hov(px,py):
    for r,row in enumerate(KB):
        for c,key in enumerate(row):
            x1,y1,x2,y2=_krect(r,c,key)
            if x1<=px<=x2 and y1<=py<=y2: return r,c,key
    return None

def _draw_kb(frame,hov,pinching):
    ov=frame.copy()
    for r,row in enumerate(KB):
        for c,key in enumerate(row):
            x1,y1,x2,y2=_krect(r,c,key)
            is_h=hov and hov[2]==key
            sp=key in("SPACE","BACK","ENTER","CLEAR")
            bg=(50,120,80) if(is_h and pinching) else(40,80,80) if is_h else(25,30,50) if sp else C_DARK
            cv2.rectangle(ov,(x1,y1),(x2,y2),bg,-1)
            cv2.rectangle(ov,(x1,y1),(x2,y2),C_TEAL if is_h else(50,60,90),1)
            lbl=key if sp else (key.upper() if _caps else key.lower())
            fs=0.38 if sp else 0.52
            tw,th=cv2.getTextSize(lbl,cv2.FONT_HERSHEY_SIMPLEX,fs,1)[0]
            cv2.putText(ov,lbl,(x1+(x2-x1-tw)//2,y1+(y2-y1+th)//2),
                        cv2.FONT_HERSHEY_SIMPLEX,fs,C_TEAL if is_h else C_WHITE,1)
    cv2.addWeighted(ov,0.82,frame,0.18,0,frame)

def _draw_text(frame):
    cv2.rectangle(frame,(0,CAM_H-56),(CAM_W,CAM_H),(10,12,22),-1)
    cv2.line(frame,(0,CAM_H-56),(CAM_W,CAM_H-56),C_TEAL,1)
    disp=(_buf[-90:] if len(_buf)>90 else _buf)+"|"
    cv2.putText(frame,disp,(12,CAM_H-22),cv2.FONT_HERSHEY_SIMPLEX,0.6,C_WHITE,1)
    if _caps: cv2.putText(frame,"CAPS",(CAM_W-70,CAM_H-22),cv2.FONT_HERSHEY_SIMPLEX,0.45,C_YEL,1)


# ── KEYBOARD MODE ─────────────────────────────────────────────────────────────
def _handle_keyboard(lms,frame):
    global _buf,_caps,_lkt,_lfk
    now=time.time()
    pinching=_pinch(lms)
    mx,my=_coord(lms[I_TIP])
    # average thumb+index for pinch midpoint
    tx,ty=_coord(lms[T_TIP])
    pmx,pmy=(mx+tx)//2,(my+ty)//2
    hov=_hov(pmx,pmy)
    _draw_kb(frame,hov,pinching)
    col=C_GREEN if pinching else C_BLUE
    cv2.circle(frame,(pmx,pmy),11,col,-1)
    cv2.circle(frame,(pmx,pmy),11,C_WHITE,1)

    if pinching and hov and hov[2]!=_lfk and now-_lkt>KEY_CD:
        key=hov[2]
        _lfk=key; _lkt=now
        if key=="BACK":
            if _buf: _buf=_buf[:-1]
            _press("backspace")
        elif key=="CLEAR":
            _buf=""; _hotkey("command","a"); time.sleep(0.04); _press("delete")
        elif key=="ENTER":
            _buf+="\n"; _press("enter")
        elif key=="SPACE":
            _type(" ")
        else:
            _type(key.upper() if _caps else key.lower())
        print(f"⌨  {key}")
    elif not pinching: _lfk=None

    # Fist = backspace
    if _up(lms)==(0,0,0,0,0) and now-_lkt>KEY_CD:
        if _buf: _buf=_buf[:-1]
        _press("backspace"); _lkt=now
    # 3 fingers = enter
    if _up(lms)==(0,1,1,1,0) and now-_lkt>KEY_CD:
        _buf+="\n"; _press("enter"); _lkt=now
    # 4 fingers = caps toggle
    if _up(lms)==(0,1,1,1,1) and now-_lkt>KEY_CD*3:
        _caps=not _caps; _lkt=now
    _draw_text(frame)


# ── SWIPE MODE ────────────────────────────────────────────────────────────────
SWIPE_MAP={
    ("right","top"):"e",("right","mid"):"n",("right","bot"):"s",
    ("left","top"):"t", ("left","mid"):"a", ("left","bot"):"i",
    ("up","left"):"o",  ("up","right"):"h", ("up","mid"):"r",
    ("down","left"):"l",("down","right"):"d",("down","mid"):"c",
}
_sw={"start":None,"last":None,"trail":[]}

def _handle_swipe(lms,frame):
    global _lkt
    now=time.time()
    ix,iy=_coord(lms[I_TIP])
    f=_up(lms)
    _sw["trail"].append((ix,iy))
    _sw["trail"]=_sw["trail"][-40:]
    pts=np.array(_sw["trail"],np.int32)
    if len(pts)>1:
        for i in range(1,len(pts)):
            a=int(255*i/len(pts))
            cv2.line(frame,tuple(pts[i-1]),tuple(pts[i]),(0,a,180),2)
    cv2.circle(frame,(ix,iy),10,C_TEAL,-1)

    # draw zone grid
    for x in[CAM_W//3,2*CAM_W//3]:
        cv2.line(frame,(x,40),(x,CAM_H-60),(40,50,70),1)
    for y in[CAM_H//3,2*CAM_H//3]:
        cv2.line(frame,(0,y),(CAM_W,y),(40,50,70),1)
    hints=[("← T","← A","← I"),("↑ R","center","↓ C"),("→ E","→ N","→ S")]
    for ri in range(3):
        for ci in range(3):
            cv2.putText(frame,hints[ci][ri],(ci*CAM_W//3+8,ri*CAM_H//3+56),
                        cv2.FONT_HERSHEY_SIMPLEX,0.38,C_GREY,1)

    if f[1]==1 and f[2]==0:          # index up = swiping
        if _sw["start"] is None: _sw["start"]=(ix,iy)
        _sw["last"]=(ix,iy)
        cv2.circle(frame,_sw["start"],8,C_YEL,2)
    elif _sw["start"] and now-_lkt>KEY_CD:
        sx,sy=_sw["start"]; ex,ey=_sw["last"] or (ix,iy)
        dx,dy=ex-sx,ey-sy
        if abs(dx)>SWIPE_MIN or abs(dy)>SWIPE_MIN:
            if abs(dx)>abs(dy): direction="right" if dx>0 else "left"
            else:               direction="down"  if dy>0 else "up"
            hz="left" if sx<CAM_W//3 else "right" if sx>2*CAM_W//3 else "mid"
            vz="top"  if sy<CAM_H//3 else "bot"   if sy>2*CAM_H//3 else "mid"
            ch=SWIPE_MAP.get((direction,vz),SWIPE_MAP.get((direction,hz)))
            if ch:
                _type(ch.upper() if _caps else ch); _lkt=now
                cv2.putText(frame,f"→ {ch.upper()}",(CAM_W//2-30,CAM_H//2),
                            cv2.FONT_HERSHEY_SIMPLEX,3,C_GREEN,4)
        _sw["start"]=None; _sw["last"]=None; _sw["trail"]=[]

    if f==(0,0,0,0,0) and now-_lkt>KEY_CD*2:
        _type(" "); _lkt=now
    _draw_text(frame)


# ── FINGER SPELL MODE ─────────────────────────────────────────────────────────
_sp={"pose":None,"cnt":0,"last":None,"lt":0}

def _handle_spell(lms,frame):
    global _lkt
    now=time.time()
    f=_up(lms)
    letter=SPELL.get(f)
    names=["Th","Ix","Md","Rg","Pk"]
    for i,(n,u) in enumerate(zip(names,f)):
        col=C_GREEN if u else C_RED
        cv2.circle(frame,(30+i*46,CAM_H-100),13,col,-1)
        cv2.putText(frame,n,(22+i*46,CAM_H-95),cv2.FONT_HERSHEY_SIMPLEX,0.38,C_WHITE,1)
    if letter:
        cv2.putText(frame,f"→ {letter}",(CAM_W//2-40,110),
                    cv2.FONT_HERSHEY_SIMPLEX,3,C_TEAL,5)
    if f==_sp["pose"]: _sp["cnt"]+=1
    else: _sp["pose"]=f; _sp["cnt"]=1
    if(_sp["cnt"]==HOLD_FRAMES and letter and
       letter!=_sp["last"] and now-_sp["lt"]>KEY_CD):
        _type(letter.upper() if _caps else letter.lower())
        _sp["last"]=letter; _sp["lt"]=now; _lkt=now
    if f!=_sp.get("_p"): _sp["last"]=None
    _sp["_p"]=f
    if _pinch(lms) and now-_lkt>KEY_CD*2: _type(" "); _lkt=now
    _draw_text(frame)


# ── SHORTCUT MODE ─────────────────────────────────────────────────────────────
_sc={"pose":None,"cnt":0,"last":""}

def _handle_sc(lms,frame):
    f=_up(lms)
    if f==_sc["pose"]: _sc["cnt"]+=1
    else: _sc["pose"]=f; _sc["cnt"]=1
    sc=SHORTCUTS.get(f)
    names=["Thumb","Index","Mid","Ring","Pinky"]
    for i,(n,u) in enumerate(zip(names,f)):
        col=C_GREEN if u else(40,40,60)
        cv2.rectangle(frame,(28+i*82,CAM_H//2-70),(28+i*82+70,CAM_H//2+70),col,-1)
        cv2.rectangle(frame,(28+i*82,CAM_H//2-70),(28+i*82+70,CAM_H//2+70),C_TEAL,1)
        cv2.putText(frame,n[:3],(28+i*82+5,CAM_H//2-48),cv2.FONT_HERSHEY_SIMPLEX,0.38,C_WHITE,1)
    if sc:
        keys,label=sc
        prog=min(_sc["cnt"]/HOLD_FRAMES,1.0)
        bw=int(260*prog)
        cv2.rectangle(frame,(CAM_W//2-130,65),(CAM_W//2-130+260,82),(30,30,50),-1)
        cv2.rectangle(frame,(CAM_W//2-130,65),(CAM_W//2-130+bw,82),C_TEAL,-1)
        cv2.putText(frame,f"Hold: {label}",(CAM_W//2-60,60),cv2.FONT_HERSHEY_SIMPLEX,0.55,C_YEL,1)
        if _sc["cnt"]>=HOLD_FRAMES:
            _hotkey(*keys); _sc["last"]=label; _sc["cnt"]=0
            print(f"⚡ {label} → {keys}")
    if _sc["last"]:
        cv2.putText(frame,f"✓ {_sc['last']}",(CAM_W//2-60,CAM_H//2+120),
                    cv2.FONT_HERSHEY_SIMPLEX,0.9,C_GREEN,2)


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
def _loop():
    global _running, _mode
    _get_model()
    cap=cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT,CAM_H)
    cap.set(cv2.CAP_PROP_FPS,30)
    if not cap.isOpened():
        print("✗ Gesture_Keyboard: cannot open camera"); _running=False; return

    opts=mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        num_hands=1,
        min_hand_detection_confidence=0.75,
        min_tracking_confidence=0.7,
        running_mode=mp_vision.RunningMode.VIDEO,
    )
    print("✓ Gesture Keyboard live — M=cycle mode, C=clear, ESC=stop")
    ts=0
    with mp_vision.HandLandmarker.create_from_options(opts) as det:
        while _running:
            ok,frame=cap.read()
            if not ok: continue
            frame=cv2.flip(frame,1); ts+=33
            tint=np.zeros_like(frame)
            frame=cv2.addWeighted(frame,0.78,tint,0.22,0)
            img=mp.Image(image_format=mp.ImageFormat.SRGB,
                         data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            res=det.detect_for_video(img,ts)
            if res.hand_landmarks:
                lms=res.hand_landmarks[0]
                conns=[(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
                       (0,9),(9,10),(10,11),(11,12),(0,13),(13,14),(14,15),(15,16),
                       (0,17),(17,18),(18,19),(19,20),(5,9),(9,13),(13,17)]
                for a,b in conns:
                    ax,ay=_coord(lms[a]); bx,by=_coord(lms[b])
                    cv2.line(frame,(ax,ay),(bx,by),C_BLUE,1)
                for l in lms:
                    cv2.circle(frame,_coord(l),3,C_TEAL,-1)
                if   _mode=="keyboard":    _handle_keyboard(lms,frame)
                elif _mode=="swipe":       _handle_swipe(lms,frame)
                elif _mode=="fingerspell": _handle_spell(lms,frame)
                elif _mode=="shortcut":    _handle_sc(lms,frame)
            else:
                if _mode=="keyboard": _draw_kb(frame,None,False); _draw_text(frame)

            mc=(0,210,180) if _mode=="keyboard" else(255,180,0) if _mode=="swipe" else(180,100,255) if _mode=="fingerspell" else(0,200,255)
            cv2.rectangle(frame,(0,0),(CAM_W,38),(10,12,22),-1)
            cv2.putText(frame,f"ALPHA [{_mode.upper()}]  M=mode  C=clear  ESC=stop",
                        (8,25),cv2.FONT_HERSHEY_SIMPLEX,0.46,mc,1)
            cv2.imshow("Alpha — Gesture Keyboard",frame)
            k=cv2.waitKey(1)&0xFF
            if k==27: break
            if k in(ord("m"),ord("M")):
                idx=_MODES.index(_mode); _mode=_MODES[(idx+1)%len(_MODES)]
            if k in(ord("c"),ord("C")):
                globals()["_buf"]=""

    _running=False
    cap.release(); cv2.destroyAllWindows()
    print("✓ Gesture_Keyboard stopped.")


# ── PUBLIC API ────────────────────────────────────────────────────────────────
def start_keyboard():
    global _running,_mode
    if _running: _mode="keyboard"; return
    _mode="keyboard"; _running=True
    threading.Thread(target=_loop,daemon=True).start()

def start_swipe_mode():
    global _running,_mode
    if _running: _mode="swipe"; return
    _mode="swipe"; _running=True
    threading.Thread(target=_loop,daemon=True).start()

def start_fingerspell_mode():
    global _running,_mode
    if _running: _mode="fingerspell"; return
    _mode="fingerspell"; _running=True
    threading.Thread(target=_loop,daemon=True).start()

def start_shortcut_mode():
    global _running,_mode
    if _running: _mode="shortcut"; return
    _mode="shortcut"; _running=True
    threading.Thread(target=_loop,daemon=True).start()

def stop():
    global _running; _running=False; time.sleep(0.3)

def get_text(): return _buf
def clear_text():
    global _buf; _buf=""

def set_mode(m):
    global _mode
    if m in _MODES: _mode=m

def set_output_app(v):
    global _out; _out=v

if __name__=="__main__":
    start_keyboard()
    try:
        while _running: time.sleep(0.5)
    except KeyboardInterrupt:
        stop()
    print("Typed:",get_text())
