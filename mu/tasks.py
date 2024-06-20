import datetime as dt
import importlib
import inspect
import json
import logging
from os import environ

from mu.libs import auth


log = logging.getLogger(__name__)


def client():
    return auth.b3_sess().client('lambda')


def func_task_path(func):
    module_path = inspect.getmodule(func).__name__
    task_path = f'{module_path}:{func.__name__}'
    return task_path


class AsyncTask:
    def __init__(self, func, *, lambda_func=None):
        self.func = func
        self._lambda_func = lambda_func

    @property
    def lambda_func(self):
        return self._lambda_func or environ['AWS_LAMBDA_FUNCTION_NAME']

    def payload(self, args, kwargs):
        return {
            'task-path': func_task_path(self.func),
            'args': args,
            'kwargs': kwargs,
        }

    def invoke(self, *args, **kwargs):
        payload = self.payload(args, kwargs)
        task_path = payload['task-path']

        result = self.response = client().invoke(
            FunctionName=self.lambda_func,
            InvocationType='Event',
            Payload=json.dumps(payload, default=self.json_dump),
        )
        if result['StatusCode'] == 202:
            req_id = result['ResponseMetadata']['RequestId']
            log.info(
                f'Async task invoke: {self.lambda_func} -> {task_path}; Request ID: {req_id}',
            )
            return

        log.error(
            f'Invoking task {task_path} failed',
            extra={
                'FunctionError': result.get('FunctionError'),
                'LogResult': result.get('LogResult'),
            },
        )

    def json_dump(self, value):
        if isinstance(value, dt.date | dt.datetime):
            return value.isoformat()
        return json.dumps(value)


def task(func=None, **kwargs):
    def decorator(func):
        func._mu_task = at = AsyncTask(func, **kwargs)
        func.invoke = at.invoke
        return func

    # Called as @task?
    if func:
        return decorator(func)

    # Called as @task()
    def wrapper(func):
        return decorator(func)

    return wrapper


def call_task(event: dict):
    task_path: str = event['task-path']
    args: list = event['args']
    kwargs: dict = event['kwargs']

    mod_path, func_name = task_path.rsplit(':', 1)
    module = importlib.import_module(mod_path)
    function = getattr(module, func_name)

    log.info(f'Task called: {task_path}\n%s', event)

    return function(*args, **kwargs)
