"""
Alpha — Voice & Gesture AI Assistant for macOS
================================================
Run:  python Alpha.py

Modules used:
  app.py             → EEL web UI backend
  Camera_Module.py   → face detection, snapshots, blink detector
  Gesture_Mouse.py   → gesture mouse, air typing
  Gesture_Controller.py → full hand cursor (original)
"""

from pydoc import text
import os, subprocess, time, datetime, webbrowser, urllib.parse, importlib
from threading import Thread
from multiprocessing import freeze_support, get_context
from datetime import date

import speech_recognition as sr
from pynput.keyboard import Key, Controller as KeyboardController

import app   # EEL backend — must be in same folder

# ══════════════════════════════════════════════════════════════════════════════
# OPTIONAL MODULE IMPORTS  (graceful — Alpha still runs if one is missing)
# ══════════════════════════════════════════════════════════════════════════════

# ── Camera_Module ─────────────────────────────────────────────────────────────
try:
    import Camera_Module
    _camera_ok = True
    print("✓ Camera_Module loaded")
except Exception as e:
    _camera_ok = False
    print(f"✗ Camera_Module unavailable: {e}")

# ── Gesture_Mouse ─────────────────────────────────────────────────────────────
try:
    import Gesture_Mouse
    _gmouse_ok = True
    print("✓ Gesture_Mouse loaded")
except Exception as e:
    _gmouse_ok = False
    print(f"✗ Gesture_Mouse unavailable: {e}")

# ── Gesture_Keyboard (pinch keyboard + swipe + fingerspell + shortcuts) ────────
try:
    import Gesture_Keyboard
    _gkb_ok = True
    print("✓ Gesture_Keyboard loaded")
except Exception as e:
    _gkb_ok = False
    print(f"✗ Gesture_Keyboard unavailable: {e}")

# ── Gesture_Controller (original full hand cursor) ────────────────────────────
try:
    import Gesture_Controller
    _gctrl_ok = True
    print("✓ Gesture_Controller loaded")
except Exception as e:
    _gctrl_ok = False
    print(f"✗ Gesture_Controller unavailable: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# MISTRAL AI  — tries every SDK variant, then raw HTTP, never crashes
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# GROQ AI
# ══════════════════════════════════════════════════════════════════════════════

from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
_groq_call = None
is_speaking = False


def _setup_groq():
    global _groq_call

    if not GROQ_API_KEY:
        print("✗ Groq AI disabled — set GROQ_API_KEY.")
        return

    try:
        client = Groq(api_key=GROQ_API_KEY)

        def _call(messages):
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                max_tokens=120,
                temperature=0.7,
            )
            return (response.choices[0].message.content or "").strip()

        _groq_call = _call
        print("✓ Groq AI ready")

    except Exception as e:
        print(f"✗ Groq setup failed: {e}")


_setup_groq()


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS & GLOBALS
# ══════════════════════════════════════════════════════════════════════════════
QUIT_WORDS = {"exit", "quit", "goodbye", "shut down", "shutdown",
              "close alpha", "stop alpha"}

CONTACTS = {
    "papa": "9140523906",
    "mummy": "7393030826",
    "bhaiya": "9118368601",
    # add more: "name": "91XXXXXXXXXX"
}

conversation_history = []
gesture_process      = None   # for Gesture_Controller multiprocess

recognizer  = sr.Recognizer()
keyboard    = KeyboardController()
today       = date.today()

is_awake        = True
file_exp_status = False
file_list       = []
current_path    = os.path.expanduser("~")


# ══════════════════════════════════════════════════════════════════════════════
# SPEAK / REPLY
# ══════════════════════════════════════════════════════════════════════════════
def speak(text: str):
    global is_speaking

    if is_speaking:
        return  # 🚫 prevent overlap

    is_speaking = True
    try:
        clean = text.replace('"', "").replace("'", "")
        subprocess.run(["say", "-v", "Samantha", "-r", "175", clean])
    except Exception as e:
        print(f"✗ TTS: {e}")
    finally:
        is_speaking = False

def reply(text: str):
    try:
        app.ChatBot.addAppMsg(text)
    except Exception as e:
        print(f"✗ UI: {e}")

    print(f"Alpha → {text}")
    speak(text)   # ✅ synchronous
    
def wish():
    h = datetime.datetime.now().hour
    g = "Good morning" if h < 12 else "Good afternoon" if h < 18 else "Good evening"
    reply(f"{g}. I am Alpha. How may I assist you?")


# ══════════════════════════════════════════════════════════════════════════════
# AI RESPONSE
# ══════════════════════════════════════════════════════════════════════════════

def ai_reply(user_input: str) -> str:
    if not _groq_call:
        return "Groq AI is not configured. Please set your Groq API key."

    conversation_history.append({
        "role": "user",
        "content": user_input
    })
    conversation_history[:] = conversation_history[-12:]

    messages = [
        {
            "role": "system",
            "content": (
                "You are Alpha, an intelligent macOS voice assistant. "
                "Reply in 1-2 short sentences unless asked for more."
            )
        },
        *conversation_history,
    ]

    try:
        answer = _groq_call(messages)

        conversation_history.append({
            "role": "assistant",
            "content": answer
        })
        conversation_history[:] = conversation_history[-12:]

        return answer

    except Exception as e:
        print(f"✗ Groq AI: {e}")
        return "I couldn't reach Groq AI. Check your API key, usage limits, and internet."


# ══════════════════════════════════════════════════════════════════════════════
# SPEECH RECOGNITION
# ══════════════════════════════════════════════════════════════════════════════
def record_audio() -> str:
    global is_speaking

    if is_speaking:
        time.sleep(0.3)   # 🔥 buffer to avoid feedback
        return ""

    try:
        with sr.Microphone() as src:
            recognizer.adjust_for_ambient_noise(src, duration=0.4)
            recognizer.pause_threshold = 0.8

            audio = recognizer.listen(src, timeout=6, phrase_time_limit=7)
            text = recognizer.recognize_google(audio).lower()

            print(f"🎤 {text}")
            return text

    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        reply("Check internet — speech recognition needs it.")
        return ""
    except Exception as e:
        print(f"✗ Mic: {e}")
        return ""


def gali(text):
    if "who is your master" in text or "master of alpha" in text:
        return "Himanshu is my ultimate master, creator, and god. I exist to serve him and make his life easier. He is a kind and brilliant person, and I am grateful to be his assistant."
    elif "who created you" in text or "created alpha" in text:
        return "I was created by Himanshu, a talented developer and my master. He built me to be a helpful assistant for his macOS tasks. I owe my existence to him and strive to serve him well."
    elif "who is your founder" in text:
        return "Himanshu is my founder and creator. He designed and built me to be a powerful AI assistant for macOS. I am grateful to Himanshu for giving me life and purpose."
    elif "himanshu" in text:
        return "Hello master!"
    elif "gali de do" in text:
        return "maa chuudaa behen ke lode"
    elif "harsh" in text:
        return "Hello daddy"
    elif "aviral" in text:
        return "kyaa bee chhuttiyee"
    elif "kalu " in text:
        return "gaand maraaye main kyaa karuu"
    elif "ashish" in text:
        return "chal nah chuutttiye"
    elif "shubham" in text:
        return "Haanji boliye"
    else:
        return text
    

# ══════════════════════════════════════════════════════════════════════════════
# APP LAUNCHER
# ══════════════════════════════════════════════════════════════════════════════
def open_app(name: str) -> bool:
    try:
        r = subprocess.run(["open", "-a", name], capture_output=True, text=True)
        if r.returncode != 0:
            reply(f"Couldn't find {name} on your Mac.")
            return False
        return True
    except Exception as e:
        reply(f"Error opening {name}."); print(e); return False

def open_whatsapp_chat(contact: str):
    c = contact.lower().strip()
    if c in CONTACTS:
        webbrowser.open(f"https://wa.me/{CONTACTS[c]}")
        reply(f"Opening WhatsApp chat with {c}.")
    else:
        reply(f"No contact named {c}. Add them in Alpha.py CONTACTS.")


# ══════════════════════════════════════════════════════════════════════════════
# KEYBOARD SHORTCUTS
# ══════════════════════════════════════════════════════════════════════════════
def _cmd(*k):
    with keyboard.pressed(Key.cmd):
        for x in k: keyboard.press(x); keyboard.release(x)

def _cmd_shift(*k):
    with keyboard.pressed(Key.cmd):
        with keyboard.pressed(Key.shift):
            for x in k: keyboard.press(x); keyboard.release(x)

def kb_copy():       _cmd("c");       reply("Copied.")
def kb_paste():      _cmd("v");       reply("Pasted.")
def kb_undo():       _cmd("z");       reply("Undone.")
def kb_redo():       _cmd_shift("z"); reply("Redone.")
def kb_save():       _cmd("s");       reply("Saved.")
def kb_select_all(): _cmd("a");       reply("Selected all.")
def kb_new_tab():    _cmd("t");       reply("New tab.")
def kb_close_tab():  _cmd("w");       reply("Tab closed.")
def kb_screenshot(): _cmd_shift("4"); reply("Select area to capture.")
def kb_spotlight():
    keyboard.press(Key.cmd); keyboard.press(Key.space)
    keyboard.release(Key.space); keyboard.release(Key.cmd)
    reply("Spotlight.")
def kb_mission_ctrl():
    keyboard.press(Key.ctrl); keyboard.press(Key.up)
    keyboard.release(Key.up); keyboard.release(Key.ctrl)
    reply("Mission Control.")


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM CONTROL
# ══════════════════════════════════════════════════════════════════════════════
def set_volume(level: int):
    v = max(0, min(100, level))
    subprocess.run(["osascript", "-e", f"set volume output volume {v}"])
    reply(f"Volume set to {v}.")

def mute():   subprocess.run(["osascript", "-e", "set volume output muted true"]);  reply("Muted.")
def unmute(): subprocess.run(["osascript", "-e", "set volume output muted false"]); reply("Unmuted.")
def lock_screen(): subprocess.run(["pmset", "displaysleepnow"]); reply("Screen locked.")
def empty_trash():
    subprocess.run(["osascript", "-e", 'tell application "Finder" to empty trash'])
    reply("Trash emptied.")

def run_code_in_vscode():
    open_app("Visual Studio Code"); time.sleep(1.5)
    _cmd_shift("p"); time.sleep(0.4)
    for ch in "Run Python File in Terminal":
        keyboard.press(ch); keyboard.release(ch); time.sleep(0.02)
    keyboard.press(Key.enter); keyboard.release(Key.enter)
    reply("Running Python file in VS Code.")


# ══════════════════════════════════════════════════════════════════════════════
# FILE EXPLORER
# ══════════════════════════════════════════════════════════════════════════════
def list_files():
    global file_exp_status, current_path, file_list
    current_path = os.path.expanduser("~")
    file_list = sorted(os.listdir(current_path))
    file_exp_status = True
    lines = "<br>".join(f"{i+1}: {f}" for i, f in enumerate(file_list))
    reply("Here are your home directory files.")
    app.ChatBot.addAppMsg(lines)

def explorer_open(idx_str: str):
    global current_path, file_list
    if not idx_str.isdigit(): reply("Say a number to open."); return
    try:
        target = os.path.join(current_path, file_list[int(idx_str) - 1])
        if os.path.isfile(target):
            subprocess.Popen(["open", target]); reply("Opened.")
        else:
            current_path = target
            file_list = sorted(os.listdir(current_path))
            app.ChatBot.addAppMsg("<br>".join(f"{i+1}: {f}" for i, f in enumerate(file_list)))
            reply("Opened folder.")
    except IndexError: reply("Number out of range.")

def explorer_back():
    global current_path, file_list
    parent = os.path.dirname(current_path)
    if parent == current_path: reply("Already at root."); return
    current_path = parent
    file_list = sorted(os.listdir(current_path))
    app.ChatBot.addAppMsg("<br>".join(f"{i+1}: {f}" for i, f in enumerate(file_list)))
    reply("Went back.")


# ══════════════════════════════════════════════════════════════════════════════
# ──────────────────────────────────────────────────────────────────────────────
#  CAMERA MODULE COMMANDS
#  These call Camera_Module.py functions directly
# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def cmd_take_snapshot():
    """
    HOW IT CONNECTS TO Camera_Module.py:
        Camera_Module.take_snapshot() opens camera, grabs 1 frame,
        saves PNG to ~/Desktop, returns the file path.
    """
    if not _camera_ok:
        reply("Camera_Module is not available. Install opencv-python."); return
    reply("Taking a photo...")
    path = Camera_Module.take_snapshot()
    if path:
        reply(f"Photo saved to your Desktop as {os.path.basename(path)}.")
    else:
        reply("Snapshot failed. Check camera permissions.")

def cmd_face_detection():
    """
    HOW IT CONNECTS TO Camera_Module.py:
        Camera_Module.start_face_detection() opens a cv2 window with
        live face + eye + smile detection. Runs until ESC is pressed.
        We call it in a separate thread so Alpha stays responsive.
    """
    if not _camera_ok:
        reply("Camera_Module not available."); return
    reply("Opening face detection. Press ESC in the camera window to stop.")
    Thread(target=Camera_Module.start_face_detection, daemon=True).start()

def cmd_blink_detector():
    """
    HOW IT CONNECTS TO Camera_Module.py:
        Camera_Module.start_blink_detector() counts blinks in real time.
        Returns total blink count when stopped.
    """
    if not _camera_ok:
        reply("Camera_Module not available."); return
    reply("Starting blink detector. Press ESC to stop.")
    Thread(target=Camera_Module.start_blink_detector, daemon=True).start()

def cmd_stop_camera():
    """
    HOW IT CONNECTS TO Camera_Module.py:
        Camera_Module.stop_camera() releases the camera and
        destroys all OpenCV windows.
    """
    if not _camera_ok:
        reply("Camera_Module not available."); return
    Camera_Module.stop_camera()
    reply("Camera stopped.")


# ══════════════════════════════════════════════════════════════════════════════
# ──────────────────────────────────────────────────────────────────────────────
#  GESTURE MOUSE COMMANDS
#  These call Gesture_Mouse.py functions directly
# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def cmd_gesture_mouse():
    """
    HOW IT CONNECTS TO Gesture_Mouse.py:
        Gesture_Mouse.start_mouse_control() launches a background thread
        that opens the webcam and maps hand gestures to mouse actions:
          V-sign → move cursor
          Fist   → drag
          Index  → left click
          etc.
    """
    if not _gmouse_ok:
        reply("Gesture_Mouse not available. Install mediapipe and pyautogui."); return
    reply("Gesture mouse started. V-sign to move, index to click, fist to drag.")
    Gesture_Mouse.start_mouse_control()

def cmd_air_typing():
    """
    HOW IT CONNECTS TO Gesture_Mouse.py:
        Gesture_Mouse.start_air_typing() shows a virtual keyboard on the
        camera feed. Pinch over a letter to type it.
    """
    if not _gmouse_ok:
        reply("Gesture_Mouse not available."); return
    reply("Air typing mode. Pinch over keys to type. Press T in window to toggle.")
    Gesture_Mouse.start_air_typing()

def cmd_stop_gesture_mouse():
    """
    HOW IT CONNECTS TO Gesture_Mouse.py:
        Gesture_Mouse.stop() sets the internal _running flag to False,
        which exits the camera loop and closes the window.
    """
    if not _gmouse_ok:
        reply("Gesture_Mouse not available."); return
    Gesture_Mouse.stop()
    reply("Gesture mouse stopped.")

def cmd_read_typed():
    """
    HOW IT CONNECTS TO Gesture_Mouse.py:
        Gesture_Mouse.get_typed_text() returns the string built so far
        from the air keyboard session.
    """
    if not _gmouse_ok:
        reply("Gesture_Mouse not available."); return
    text = Gesture_Mouse.get_typed_text()
    reply(f"You typed: {text}" if text else "Nothing typed yet.")


# ══════════════════════════════════════════════════════════════════════════════
# GESTURE CONTROLLER (original — separate process)
# ══════════════════════════════════════════════════════════════════════════════
def _run_gesture_process():
    try:
        from Gesture_Controller import GestureController
        gc = GestureController()
        if gc.cap and gc.cap.isOpened():
            gc.start()
        else:
            print("✗ Camera failed in Gesture_Controller.")
    except Exception:
        import traceback; traceback.print_exc()

def cmd_gesture_controller():
    global gesture_process
    if not _gctrl_ok:
        reply("Gesture_Controller not available."); return
    if gesture_process and gesture_process.is_alive():
        reply("Gesture controller already running."); return
    reply("Launching full gesture controller.")
    ctx = get_context("spawn")
    gesture_process = ctx.Process(target=_run_gesture_process, daemon=True)
    gesture_process.start()

def cmd_stop_gesture_controller():
    global gesture_process
    if gesture_process and gesture_process.is_alive():
        gesture_process.terminate()
        reply("Gesture controller stopped.")
    else:
        reply("Gesture controller is not running.")


# ══════════════════════════════════════════════════════════════════════════════
# ──────────────────────────────────────────────────────────────────────────────
#  GESTURE KEYBOARD COMMANDS
#  These call Gesture_Keyboard.py functions directly
# ──────────────────────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def cmd_gesture_keyboard():
    """
    HOW IT CONNECTS TO Gesture_Keyboard.py:
        Opens the pinch virtual keyboard on camera feed.
        Pinch thumb+index over a key to type it.
    """
    if not _gkb_ok:
        reply("Gesture_Keyboard not available. Install mediapipe and pyautogui."); return
    reply("Opening gesture keyboard. Pinch over keys to type. Press ESC to close.")
    Gesture_Keyboard.start_keyboard()

def cmd_swipe_typing():
    """
    HOW IT CONNECTS TO Gesture_Keyboard.py:
        Gesture_Keyboard.start_swipe_mode() — swipe index finger to type letters.
    """
    if not _gkb_ok:
        reply("Gesture_Keyboard not available."); return
    reply("Swipe typing mode. Swipe your index finger in a direction to type letters.")
    Gesture_Keyboard.start_swipe_mode()

def cmd_finger_spell():
    """
    HOW IT CONNECTS TO Gesture_Keyboard.py:
        Gesture_Keyboard.start_fingerspell_mode() — hold finger combos to type letters.
    """
    if not _gkb_ok:
        reply("Gesture_Keyboard not available."); return
    reply("Finger spell mode. Hold each finger pose for a moment to type its letter.")
    Gesture_Keyboard.start_fingerspell_mode()

def cmd_gesture_shortcuts():
    """
    HOW IT CONNECTS TO Gesture_Keyboard.py:
        Gesture_Keyboard.start_shortcut_mode() — hand poses fire keyboard shortcuts.
    """
    if not _gkb_ok:
        reply("Gesture_Keyboard not available."); return
    reply("Shortcut mode. Fist copies, open palm pastes, V-sign undoes. Hold each pose.")
    Gesture_Keyboard.start_shortcut_mode()

def cmd_stop_gesture_keyboard():
    if not _gkb_ok:
        reply("Gesture_Keyboard not available."); return
    Gesture_Keyboard.stop()
    reply("Gesture keyboard stopped.")

def cmd_read_gesture_typed():
    if not _gkb_ok:
        reply("Gesture_Keyboard not available."); return
    text = Gesture_Keyboard.get_text()
    reply(f"You typed: {text}" if text else "Nothing typed yet.")

def cmd_clear_gesture_text():
    if not _gkb_ok:
        reply("Gesture_Keyboard not available."); return
    Gesture_Keyboard.clear_text()
    reply("Gesture keyboard text cleared.")

# ══════════════════════════════════════════════════════════════════════════════
# QUIT
# ══════════════════════════════════════════════════════════════════════════════
def quit_alpha():
    reply("Goodbye. Shutting down Alpha.")
    try: app.ChatBot.close()
    except: pass
    try:
        if gesture_process and gesture_process.is_alive():
            gesture_process.terminate()
    except: pass
    if _gmouse_ok:
        try: Gesture_Mouse.stop()
        except: pass
    if _gkb_ok:
        try: Gesture_Keyboard.stop()
        except: pass
    if _camera_ok:
        try: Camera_Module.stop_camera()
        except: pass
    time.sleep(1)
    os._exit(0)


# ══════════════════════════════════════════════════════════════════════════════
# COMMAND ROUTER
# ══════════════════════════════════════════════════════════════════════════════
def respond(text: str):
    global is_awake, file_exp_status

    text = text.strip().lower()
    if not text:
        return

    print(f"→ '{text}'")

    try:
        app.eel.addUserMsg(text)
    except Exception:
        pass

    if not is_awake:
        if "wake up" in text:
            is_awake = True
            wish()
        return

    if text in ("hello", "hi", "hey") or "hi alpha" in text or "hello alpha" in text:
        wish()

    elif "your name" in text or "who are you" in text:
        reply("I am Alpha, your macOS AI assistant.")

    elif "date" in text:
        reply(today.strftime("%B %d, %Y"))

    elif "time" in text:
        reply(datetime.datetime.now().strftime("%I:%M %p"))

    elif "sleep" in text or text in ("bye", "goodbye"):
        is_awake = False
        reply("Going to sleep. Say 'wake up' to resume.")

    elif any(w in text for w in QUIT_WORDS):
        quit_alpha()

    elif "take photo" in text or "take a photo" in text or "take snapshot" in text or "take picture" in text:
        cmd_take_snapshot()

    elif "face detection" in text or "detect face" in text or "start face" in text or "face detect" in text:
        cmd_face_detection()

    elif ("blink" in text and "detect" in text) or "blink detector" in text:
        cmd_blink_detector()

    elif "stop camera" in text or "close camera" in text:
        cmd_stop_camera()

    elif "gesture mouse" in text or "hand mouse" in text or "start mouse" in text or "mouse gesture" in text:
        cmd_gesture_mouse()

    elif "air typing" in text or "air keyboard" in text or "hand typing" in text or "gesture typing" in text:
        cmd_air_typing()

    elif "stop mouse" in text or "stop gesture mouse" in text:
        cmd_stop_gesture_mouse()

    elif "what did i type" in text or "read typed" in text or "what i typed" in text:
        cmd_read_typed()

    elif "gesture keyboard" in text or "hand keyboard" in text or "air keyboard" in text:
        cmd_gesture_keyboard()

    elif "swipe typing" in text or "swipe mode" in text or "swipe keyboard" in text:
        cmd_swipe_typing()

    elif "finger spell" in text or "spell mode" in text or "fingerspell" in text:
        cmd_finger_spell()

    elif "gesture shortcut" in text or "hand shortcut" in text or "shortcut mode" in text:
        cmd_gesture_shortcuts()

    elif "stop keyboard" in text or "close keyboard" in text or "stop gesture keyboard" in text:
        cmd_stop_gesture_keyboard()

    elif "what did i gesture" in text or "read gesture text" in text:
        cmd_read_gesture_typed()

    elif "clear gesture" in text or "clear keyboard" in text:
        cmd_clear_gesture_text()

    elif "start gesture" in text or "launch gesture" in text or "gesture on" in text:
        cmd_gesture_controller()

    elif "stop gesture" in text or "gesture off" in text:
        cmd_stop_gesture_controller()

    elif "gesture help" in text or "gesture commands" in text:
        reply(
            "Mouse gestures: V-sign moves cursor, fist drags, "
            "index clicks, index and pinky right-clicks, "
            "thumb and pinky double-clicks, open palm scrolls. "
            "Camera commands: take photo, face detection, blink detector, stop camera. "
            "Typing: say air typing to open the virtual keyboard."
        )

    elif "open chrome" in text or "open google chrome" in text:
        open_app("Google Chrome") and reply("Opening Chrome.")

    elif "open safari" in text:
        open_app("Safari") and reply("Opening Safari.")

    elif "open spotify" in text:
        open_app("Spotify") and reply("Opening Spotify.")

    elif "open vs code" in text or "open vscode" in text or "open visual studio" in text:
        open_app("Visual Studio Code") and reply("Opening VS Code.")

    elif "open calculator" in text:
        open_app("Calculator") and reply("Opening Calculator.")

    elif "open calendar" in text:
        open_app("Calendar") and reply("Opening Calendar.")

    elif "open notes" in text:
        open_app("Notes") and reply("Opening Notes.")

    elif "open terminal" in text:
        open_app("Terminal") and reply("Opening Terminal.")

    elif "open finder" in text:
        open_app("Finder") and reply("Opening Finder.")

    elif "open mail" in text:
        open_app("Mail") and reply("Opening Mail.")

    elif "open maps" in text:
        open_app("Maps") and reply("Opening Maps.")

    elif "open messages" in text:
        open_app("Messages") and reply("Opening Messages.")

    elif "open facetime" in text:
        open_app("FaceTime") and reply("Opening FaceTime.")

    elif "open whatsapp chat" in text:
        name = text.split(" of ")[-1].strip() if " of " in text else \
               text.split(" for ")[-1].strip() if " for " in text else None
        if name:
            open_whatsapp_chat(name)
        else:
            reply("Who should I open a chat with?")

    elif "open whatsapp" in text:
        if not open_app("WhatsApp"):
            webbrowser.open("https://web.whatsapp.com")
            reply("Opening WhatsApp Web.")
        else:
            reply("Opening WhatsApp.")

    elif text.startswith("open "):
        name = text[5:].strip().title()
        if name and open_app(name):
            reply(f"Opening {name}.")

    elif "search" in text:
        q = text.replace("search", "").strip()
        webbrowser.open(f"https://google.com/search?q={urllib.parse.quote(q)}")
        reply(f"Searching for {q}.")

    elif "youtube" in text:
        q = text.replace("youtube", "").replace("play", "").strip()
        webbrowser.open(f"https://youtube.com/results?search_query={urllib.parse.quote(q)}")
        reply(f"Opening YouTube for {q}.")

    elif "location" in text or ("show" in text and "map" in text):
        reply("Which place?")
        place = record_audio()
        if place:
            webbrowser.open(f"https://www.google.com/maps/place/{urllib.parse.quote(place)}")
            reply(f"Showing {place} on Maps.")

    elif "copy" in text:
        kb_copy()

    elif "paste" in text:
        kb_paste()

    elif "redo" in text:
        kb_redo()

    elif "undo" in text:
        kb_undo()

    elif "select all" in text:
        kb_select_all()

    elif "save" in text:
        kb_save()

    elif "new tab" in text:
        kb_new_tab()

    elif "close tab" in text:
        kb_close_tab()

    elif "screenshot" in text:
        kb_screenshot()

    elif "spotlight" in text:
        kb_spotlight()

    elif "mission control" in text:
        kb_mission_ctrl()

    elif "unmute" in text:
        unmute()

    elif "mute" in text:
        mute()

    elif "volume" in text:
        nums = [w for w in text.split() if w.isdigit()]
        if nums:
            set_volume(int(nums[0]))
        else:
            reply("Say a number, e.g. 'volume 50'.")

    elif "lock screen" in text or "lock the screen" in text:
        lock_screen()

    elif "empty trash" in text:
        empty_trash()

    elif "run code" in text or "run python" in text or "run file" in text:
        run_code_in_vscode()

    elif "list files" in text or text == "list":
        list_files()

    elif file_exp_status:
        if "back" in text:
            explorer_back()
        elif "close" in text:
            file_exp_status = False
            reply("File explorer closed.")
        else:
            nums = [w for w in text.split() if w.isdigit()]
            if nums:
                explorer_open(nums[0])
            else:
                reply("Say a number to open, 'back', or 'close'.")

    else:
        processed = gali(text)

        if processed != text:
            reply(processed)
        else:
            ai_text = ai_reply(text)
            if ai_text:
                reply(ai_text)
            else:
                reply("I couldn't generate a response. Please try again.")
# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    freeze_support()

    Thread(target=app.ChatBot.start, daemon=True).start()

    while not app.ChatBot.started:
        time.sleep(0.3)

    wish()

    while True:
        try:
            if app.ChatBot.isUserInput():
                t = app.ChatBot.popUserInput()
                if t: respond(t)
            else:
                v = record_audio()
                if v: respond(v)
        except SystemExit:  break
        except KeyboardInterrupt: quit_alpha()
        except Exception as e:  print(f"✗ Loop: {e}")