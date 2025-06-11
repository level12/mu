from mu import ActionHandler
from mu.libs.testing import Logs
from mu_tests.data.event_wsgi import wsgi_event


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


class SaveArgsTracker:
    args = None
    kwargs = None


def save_args(*args, **kwargs):
    """Used by test_task_event()"""
    SaveArgsTracker.args = args
    SaveArgsTracker.kwargs = kwargs


class FakeContext:
    aws_request_id = None
    log_group_name = None
    log_stream_name = None
    function_name = None
    memory_limit_in_mb = None
    function_version = None
    invoked_function_arn = None
    remaining_time = None
    get_remaining_time_in_millis = lambda: None


class TestHandler:
    def test_wsgi(self):
        resp = Handler.on_event(wsgi_event, {})
        assert resp == {
            'body': 'Hello World!',
            'headers': {'Content-Length': '12', 'Content-type': 'text/plain'},
            'isBase64Encoded': False,
            'statusCode': 200,
        }

    def test_action(self):
        event = {'do-action': 'hello'}
        resp = Handler.on_event(event, {})
        assert resp == 'world'

    def test_unhandled_exception(self, logs: Logs, caplog):
        event = {'do-action': 'error'}
        resp = Handler.on_event(event, FakeContext)
        assert resp == 'Internal Server Error'

        assert logs.messages == [
            'ActionHandler invoked with action: error',
            'ActionHandler.on_event() caught an unhandled exception',
        ]

        assert caplog.records[1].exc_info

    def test_task_event(self):
        event = {
            'task-path': 'mu_tests.test_handler:save_args',
            'args': ['a'],
            'kwargs': {'arg2': 'b'},
        }

        assert Handler.on_event(event, FakeContext) == 'Called task'

        assert SaveArgsTracker.args == ('a',)
        assert SaveArgsTracker.kwargs == {'arg2': 'b'}
