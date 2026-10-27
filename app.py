import eel
from threading import Lock

eel.init("web")

UI_WINDOW_WIDTH = 960
UI_WINDOW_HEIGHT = 720
UI_PORT = 5501
UI_FILE = "index.html"


# ==================== CHATBOT ====================
class ChatBot:
    started = False
    user_input_queue = []
    lock = Lock()

    @staticmethod
    def start():
        eel.start(
            UI_FILE,
            size=(UI_WINDOW_WIDTH, UI_WINDOW_HEIGHT),
            port=UI_PORT,
            block=True,
        )

    @staticmethod
    def is_user_input():
        with ChatBot.lock:
            return len(ChatBot.user_input_queue) > 0

    @staticmethod
    def pop_user_input():
        with ChatBot.lock:
            return ChatBot.user_input_queue.pop(0)

    @staticmethod
    def add_app_msg(msg: str):
        try:
            eel.addAppMsg(msg)   # ✅ FIXED
        except Exception as e:
            print("UI ERROR:", e)

    @staticmethod
    def close():
        print("UI will close when window is closed manually")


# ==================== FRONTEND CALLS ====================
@eel.expose
def addUserMsg(msg: str):
    with ChatBot.lock:
        ChatBot.user_input_queue.append(msg.lower())


@eel.expose
def notifyStarted():
    print("UI READY")
    ChatBot.started = True


# aliases
ChatBot.isUserInput = ChatBot.is_user_input
ChatBot.popUserInput = ChatBot.pop_user_input
ChatBot.addAppMsg = ChatBot.add_app_msg


# ==================== RUN ====================
if __name__ == "__main__":
    ChatBot.start()