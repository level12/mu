from mu import ActionHandler
from mu.libs.testing import Logs
from mu.tests.data.event_wsgi import wsgi_event


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

    def test_unhandled_exception(self, logs: Logs, caplog):
        event = {'do-action': 'error'}
        resp = Handler.on_event(event, {})
        assert resp == 'Internal Server Error'

        assert logs.messages == [
            'ActionHandler invoked with action: error',
            """ActionHandler.on_event() caught an unhandled exception
Event: {'do-action': 'error'}
Context: {}""",
        ]

        assert caplog.records[1].exc_info
