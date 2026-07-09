import threading
import webview
from app import app


def start_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)


threading.Thread(target=start_flask, daemon=True).start()

webview.create_window(
    "PathPilot", "http://127.0.0.1:5000", width=1500, height=900, min_size=(1200, 700)
)

webview.start()
