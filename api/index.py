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
        # Prefer original request path before Vercel rewrite
        uri = (
            environ.get('HTTP_X_FORWARDED_URI')
            or environ.get('HTTP_X_FORWARDED_URL')
            or environ.get('HTTP_X_MATCHED_PATH')
            or environ.get('PATH_INFO', '')
        )
        if '?' in uri:
            uri = uri.split('?', 1)[0]

        # Strip /api/index.py, /api/index, /api prefix if present
        for prefix in ('/api/index.py', '/api/index', '/api'):
            if uri.startswith(prefix):
                uri = uri[len(prefix):] or '/'
                break

        if not uri.startswith('/'):
            uri = '/' + uri

        environ['PATH_INFO'] = uri
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
