import os
import sys
from urllib.parse import parse_qs, urlencode

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import app

class VercelPathMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        qs = parse_qs(environ.get('QUERY_STRING', ''), keep_blank_values=True)
        if '__path' in qs:
            raw = qs.pop('__path')[0]
            environ['QUERY_STRING'] = urlencode([(k, v) for k, vs in qs.items() for v in vs])
            environ['PATH_INFO'] = '/' + raw.lstrip('/')
        else:
            path = environ.get('PATH_INFO', '')
            for prefix in ('/api/index.py', '/api/index', '/api'):
                if path.startswith(prefix):
                    remainder = path[len(prefix):]
                    environ['PATH_INFO'] = '/' + remainder.lstrip('/')
                    break
        if not environ.get('PATH_INFO'):
            environ['PATH_INFO'] = '/'
        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)
