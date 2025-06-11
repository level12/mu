import datetime as dt

import pytest

from mu.libs import utils
from mu.libs.sqs import SQS, Queue


@pytest.fixture(scope='module')
def sqs(b3_sess):
    return SQS(b3_sess)


def with_ms(value: str):
    """When you delete a queue, you must wait at least 60 seconds
    before creating a queue with the same name.
    """
    now = dt.datetime.now()
    return f'{value}-{now.microsecond}'


@pytest.fixture(autouse=True, scope='module')
def cleanup(sqs):
    sqs.delete('test-')
    yield
    sqs.delete('test-')


class TestSQS:
    def test_sync_config(self, sqs: SQS):
        func_name = with_ms('test-sync-config')
        sqs_config = {'celery': {}, 'nacel': {}}

        queues = sqs.sync_config(func_name, sqs_config)
        assert len(queues) == 2

        celery: Queue = queues[f'{func_name}-celery']
        nacel: Queue = queues[f'{func_name}-nacel']

        assert celery.exists()
        assert nacel.exists()
        assert nacel.attrs['VisibilityTimeout'] == '30'

        sqs_config['nacel'] = {'VisibilityTimeout': '10'}
        queues = sqs.sync_config(func_name, sqs_config)

        def check_vis():
            del nacel.attrs
            return nacel.attrs['VisibilityTimeout'] == '10'

        assert utils.retry(
            check_vis,
            waiting_for='nacel attrs to be updated',
        )

    def test_sync_config_del(self, sqs: SQS):
        func_name = with_ms('test-sync-config')
        sqs_config = {'celery': {}, 'nacel': {}}

        queues = sqs.sync_config(func_name, sqs_config)
        assert len(sqs.list(func_name)) == 2

        del sqs_config['nacel']

        queues = sqs.sync_config(func_name, sqs_config)

        # make sure the right queue is returned
        assert len(queues) == 1
        assert queues[f'{func_name}-celery']

        # make sure the queue was actually deleted from aws
        def check_list():
            queues = sqs.list(func_name)
            return len(queues) == 1

        assert utils.retry(
            check_list,
            waiting_for='nacel to be deleted',
            secs=2,
        )

        assert queues[f'{func_name}-celery']
