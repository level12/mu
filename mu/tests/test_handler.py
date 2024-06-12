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

    @staticmethod
    def hello(event, context):
        return 'world'


class TestHandler:
    def test_wsgi(self):
        resp = Handler.on_event(wsgi_event, {})
        assert resp == {
            'body': 'Hello World!',
            'headers': {'Content-Length': '12', 'Content-type': 'text/plain'},
            'isBase64Encoded': False,
            'statusCode': '200',
        }

    def test_action(self):
        event = {'do-action': 'hello'}
        resp = Handler.on_event(event, {})
        assert resp == 'world'
