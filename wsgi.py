import os, sys, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from http.server import HTTPServer, BaseHTTPRequestHandler

class QuickHealth(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')
    def log_message(self, *args): pass

quick = HTTPServer(("0.0.0.0", 5000), QuickHealth)
threading.Thread(target=quick.serve_forever, daemon=True).start()

from backend import create_app
app = create_app(os.getenv("FLASK_ENV", "production"))
quick.shutdown()