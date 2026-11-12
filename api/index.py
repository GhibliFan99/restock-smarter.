import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app

class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        matched = environ.get('HTTP_X_MATCHED_PATH')
        if matched:
            environ['PATH_INFO'] = matched
        else:
            path = environ.get('PATH_INFO', '')
            for prefix in ('/api/index.py', '/api/index', '/api'):
                if path.startswith(prefix):
                    remainder = path[len(prefix):]
                    environ['PATH_INFO'] = remainder if remainder.startswith('/') else ('/' + remainder if remainder else '/')
                    break
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
