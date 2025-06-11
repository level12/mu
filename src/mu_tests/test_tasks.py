import datetime as dt
from os import environ
from unittest import mock

import pytest

from mu import tasks
from mu.libs.testing import mock_patch_obj
from mu.tasks import AsyncTask


@pytest.fixture
def m_invoke():
    with (
        mock_patch_obj(tasks, 'client') as m_client,
        mock.patch.dict(environ, AWS_LAMBDA_FUNCTION_NAME='mu-task-func'),
    ):
        yield m_client.return_value.invoke


def enterprise_d(arg1, *, arg2):
    return ('ncc-1701-d', arg1, arg2)


@tasks.task
def enterprise_e(arg1, *, arg2):
    return ('ncc-1701-e', arg1, arg2)


@tasks.task(lambda_func='mr-crusher-engage')
def enterprise_f(arg1, *, arg2):
    return ('ncc-1701-f', arg1, arg2)


def invoke_resp():
    return {
        'StatusCode': 202,
        'ResponseMetadata': {'RequestId': 'abc-123'},
    }


class TestAsyncTask:
    @mock.patch.dict(environ, AWS_LAMBDA_FUNCTION_NAME='phasers')
    def test_lamba_name(self):
        task = AsyncTask(enterprise_d)
        assert task.lambda_func == 'phasers'

    def test_invoke(self, m_invoke, logs):
        m_invoke.return_value = invoke_resp()

        task = AsyncTask(enterprise_d)
        task.invoke(1, 2, foo='bar', now=dt.date(2026, 5, 19))

        assert logs.messages == [
            'Async task invoke: mu-task-func -> mu_tests.test_tasks:enterprise_d;'
            ' Request ID: abc-123',
        ]

        payload = (
            '{"task-path": "mu_tests.test_tasks:enterprise_d", "args": [1, 2],'
            ' "kwargs": {"foo": "bar", "now": "2026-05-19"}}'
        )
        m_invoke.assert_called_once_with(
            FunctionName='mu-task-func',
            InvocationType='Event',
            Payload=payload,
        )


def test_call_task():
    result = tasks.call_task(
        {
            'task-path': 'mu_tests.test_tasks:enterprise_d',
            'args': ['a'],
            'kwargs': {'arg2': 'b'},
        },
    )
    assert result == ('ncc-1701-d', 'a', 'b')


class TestTask:
    def test_decorator_plain(self, m_invoke):
        m_invoke.return_value = invoke_resp()

        enterprise_e.invoke('a', arg2='b')

        payload = (
            '{"task-path": "mu_tests.test_tasks:enterprise_e", "args": ["a"],'
            ' "kwargs": {"arg2": "b"}}'
        )
        m_invoke.assert_called_once_with(
            FunctionName='mu-task-func',
            InvocationType='Event',
            Payload=payload,
        )

    def test_decorator_args(self, m_invoke):
        m_invoke.return_value = invoke_resp()

        enterprise_f.invoke('a', arg2='b')

        payload = (
            '{"task-path": "mu_tests.test_tasks:enterprise_f", "args": ["a"],'
            ' "kwargs": {"arg2": "b"}}'
        )
        m_invoke.assert_called_once_with(
            FunctionName='mr-crusher-engage',
            InvocationType='Event',
            Payload=payload,
        )
