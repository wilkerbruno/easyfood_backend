import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import create_app
app = create_app(os.getenv('FLASK_ENV', 'production'))