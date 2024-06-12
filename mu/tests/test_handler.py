from pathlib import Path

from mu import ActionHandler, config
from mu.libs.testing import mock_patch_obj
from mu.tests.events.wsgi import wsgi_event


def wsgi_app(environ, start_response):
    status = '200 OK'
    output = b'Hello World!'

    response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
    start_response(status, response_headers)

    return [output]


class Handler(ActionHandler):
    wsgi_app = wsgi_app


class TestHandler:
    def test_wsgi(self):
        resp = Handler.on_event(wsgi_event, {})
        assert not resp
