# How Alpha.py Connects to Camera_Module & Gesture_Mouse
## A complete beginner's guide to module integration

---

## 📁 Your File Structure

```
Alpha/
├── Alpha.py              ← Main brain (you run this)
├── app.py                ← EEL web UI
├── Camera_Module.py      ← Camera features
├── Gesture_Mouse.py      ← Gesture mouse + air typing
├── Gesture_Controller.py ← Original hand cursor
└── web/
    └── index.html        ← UI
```

---

## 🔌 Step 1 — How to Import a Module

At the top of `Alpha.py`, every module is imported inside a `try/except`
so Alpha still runs even if a module is missing:

```python
# This is already done in Alpha.py for you:

try:
    import Camera_Module        # imports Camera_Module.py from same folder
    _camera_ok = True
    print("✓ Camera_Module loaded")
except Exception as e:
    _camera_ok = False
    print(f"✗ Camera_Module unavailable: {e}")

try:
    import Gesture_Mouse        # imports Gesture_Mouse.py from same folder
    _gmouse_ok = True
except Exception as e:
    _gmouse_ok = False
```

**Rule:** Both files must be in the **same folder** as Alpha.py.
Python finds them automatically — no path needed.

---

## 📞 Step 2 — How to Call a Function from a Module

Once imported, you call functions using `ModuleName.function_name()`.

### Camera_Module functions you can call:

```python
# Take a photo and save to Desktop
path = Camera_Module.take_snapshot()

# Open live face detection window (press ESC to close)
Camera_Module.start_face_detection()

# Count blinks in real time
Camera_Module.start_blink_detector()

# Release the camera
Camera_Module.stop_camera()
```

### Gesture_Mouse functions you can call:

```python
# Start gesture mouse control (runs in background thread)
Gesture_Mouse.start_mouse_control()

# Switch to air typing / virtual keyboard
Gesture_Mouse.start_air_typing()

# Switch mode while running
Gesture_Mouse.set_mode("mouse")    # back to mouse
Gesture_Mouse.set_mode("typing")   # switch to typing

# Get text typed via air keyboard
text = Gesture_Mouse.get_typed_text()

# Stop everything
Gesture_Mouse.stop()
```

---

## 🗣️ Step 3 — How Voice Commands Trigger Module Functions

In `Alpha.py`, the `respond()` function reads what you say and
calls the right module function:

```python
def respond(text: str):

    # When you say "take photo":
    if "take photo" in text or "take picture" in text:
        cmd_take_snapshot()          # this calls Camera_Module.take_snapshot()

    # When you say "face detection":
    elif "face detection" in text:
        cmd_face_detection()         # this calls Camera_Module.start_face_detection()

    # When you say "gesture mouse":
    elif "gesture mouse" in text:
        cmd_gesture_mouse()          # this calls Gesture_Mouse.start_mouse_control()

    # When you say "air typing":
    elif "air typing" in text:
        cmd_air_typing()             # this calls Gesture_Mouse.start_air_typing()
```

The `cmd_*` functions are **wrapper functions** that:
1. Check if the module loaded successfully (`_camera_ok`, `_gmouse_ok`)
2. Tell you if something's wrong (`reply("Camera not available")`)
3. Call the actual module function

---

## ➕ Step 4 — How to Add Your OWN Function from a Module

Say you add a new function `my_function()` to `Camera_Module.py`:

```python
# In Camera_Module.py:
def my_function():
    print("Hello from Camera_Module!")
    return "done"
```

Here's how you connect it to Alpha.py in 3 steps:

### Step A — Add a wrapper in Alpha.py

```python
# Paste this anywhere in Alpha.py after the imports:

def cmd_my_function():
    if not _camera_ok:
        reply("Camera_Module not available."); return
    Camera_Module.my_function()       # ← call your function here
    reply("My function ran!")
```

### Step B — Add a voice trigger in respond()

```python
# Inside respond() in Alpha.py, add a new elif:

elif "my command" in text:
    cmd_my_function()
```

### Step C — That's it. Say "my command" and it runs.

---

## 🧵 Step 5 — Threads vs Processes (important!)

Some functions open a camera window. If you call them directly,
they will **freeze Alpha** until the window closes.

**Solution:** Call them in a background thread:

```python
from threading import Thread

# WRONG — freezes Alpha until face detection window is closed:
Camera_Module.start_face_detection()

# RIGHT — runs in background, Alpha stays responsive:
Thread(target=Camera_Module.start_face_detection, daemon=True).start()
```

`Gesture_Mouse.start_mouse_control()` already handles its own thread internally.
`Camera_Module.start_face_detection()` needs to be wrapped in a Thread — 
Alpha.py already does this for you in `cmd_face_detection()`.

---

## 🎤 Full Voice Command List

| Say this                        | What happens                                     |
|---------------------------------|--------------------------------------------------|
| take photo / take a photo       | Saves a photo to ~/Desktop                       |
| face detection / detect face    | Opens live face+eye+smile detection window       |
| blink detector                  | Counts your blinks in real time                  |
| stop camera / close camera      | Releases camera, closes all windows              |
| gesture mouse / hand mouse      | Start gesture-based mouse control                |
| air typing / air keyboard       | Show virtual keyboard, pinch to type             |
| stop mouse                      | Stop gesture mouse                               |
| what did i type / what i typed  | Alpha reads out what you typed via air keyboard  |
| start gesture / gesture on      | Start full Gesture_Controller (original)         |
| stop gesture / gesture off      | Stop Gesture_Controller                          |
| gesture help                    | Explain all gestures                             |

---

## 🐛 Troubleshooting

| Problem                          | Fix                                                        |
|----------------------------------|------------------------------------------------------------|
| `ModuleNotFoundError: mediapipe` | `pip install mediapipe`                                    |
| `ModuleNotFoundError: pyautogui` | `pip install pyautogui`                                    |
| `ModuleNotFoundError: cv2`       | `pip install opencv-python`                                |
| Camera not opening               | System Settings → Privacy → Camera → allow Terminal/Python |
| Mouse not moving                 | System Settings → Privacy → Accessibility → allow          |
| Air keyboard not typing          | System Settings → Privacy → Accessibility → allow          |

---

## ⚡ Quick Reference Card

```
IMPORT a module:
    import Camera_Module

CALL a function:
    Camera_Module.take_snapshot()

CALL in background (so Alpha doesn't freeze):
    Thread(target=Camera_Module.start_face_detection, daemon=True).start()

ADD new voice command:
    1. Write cmd_myfunction() in Alpha.py
    2. Inside it, call YourModule.your_function()
    3. Add elif "your phrase" in text: cmd_myfunction()
       inside the respond() function
```
