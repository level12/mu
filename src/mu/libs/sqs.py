from dataclasses import dataclass
import functools
import logging

import boto3

from . import sts, utils
from .utils import B3DataClass


log = logging.getLogger(__name__)


@dataclass
class Queue(B3DataClass):
    name: str

    @classmethod
    def from_url(cls, b3_sess: boto3.Session, url: str):
        name = url.split('/')[-1]
        return cls(b3_sess, name)

    @functools.cached_property
    def sqs(self):
        return self._b3_sess.client('sqs')

    @functools.cached_property
    def url(self):
        acct_id = sts.account_id(self._b3_sess)
        region = self._b3_sess.region_name
        return f'https://sqs.{region}.amazonaws.com/{acct_id}/{self.name}'

    @functools.cached_property
    def attrs(self):
        resp = self.sqs.get_queue_attributes(QueueUrl=self.url, AttributeNames=('All',))
        return resp['Attributes']

    def exists(self):
        try:
            # Due to the exception being raised in attrs, exists() will continue to issue API
            # requests every time its called until it succeeds. Helpful when retrying until
            # it exists.  Potentially performance reducing though, so FYI.
            return bool(self.attrs)
        except self.sqs.exceptions.QueueDoesNotExist:
            return False

    def delete(self):
        try:
            self.sqs.delete_queue(QueueUrl=self.url)
            log.info('Queue deleted: %s', self.name)
        except self.sqs.exceptions.QueueDoesNotExist:
            log.info('Queue not found: %s', self.name)


class SQS:
    def __init__(self, b3_sess: boto3.Session):
        self.b3_sess = b3_sess
        self.sqs = b3_sess.client('sqs')

    def get(self, name: str):
        queue = Queue(self.b3_sess, name)
        return queue if queue.exists() else None

    def list(self, name_prefix: str | None = None) -> dict[str, Queue]:
        resp = self.sqs.list_queues(QueueNamePrefix=name_prefix)
        queues = [Queue.from_url(self.b3_sess, url) for url in resp.get('QueueUrls', ())]
        return {q.name: q for q in queues}

    def delete(self, name_prefix: str):
        for queue in self.list(name_prefix).values():
            queue.delete()

    def ensure(self, name: str, attrs: dict) -> Queue:
        queue = self.get(name)
        if queue:
            log.info('SQS queue existed: %s', name)
            return queue

        return self.get(name)

    def sync_config(self, func_name: str, aws_config: dict) -> dict[str:Queue]:
        retval = {}
        last_created = None

        for name, attrs in aws_config.items():
            full_name = f'{func_name}-{name}'
            retval[full_name] = queue = Queue(self.b3_sess, full_name)

            if queue.exists():
                if attrs:
                    log.info('SQS queue attrs updated: %s', name)
                    self.sqs.set_queue_attributes(QueueUrl=queue.url, Attributes=attrs)

                # clear the cache
                del queue.attrs

                log.info('SQS queue existed: %s', name)
                continue

            self.sqs.create_queue(
                QueueName=full_name,
                Attributes=attrs,
            )
            log.info('SQS queue created: %s', name)
            last_created = queue

        if last_created:
            utils.retry(queue.exists, waiting_for=f'Queue to be ready: {last_created.name}')

        # Not using existing due to lag time between creation and being ready that plays havoc
        # with our tests. If/when we move to mocked API calls, it would be better to use existing
        # instead of queue.exists() above.
        existing = self.list(func_name)
        aws_full_names = {f'{func_name}-{qname}' for qname in aws_config}
        for queue in existing.values():
            if queue.name not in aws_full_names:
                queue.delete()
                short_name = queue.name.replace(func_name, '', 1).lstrip('-')
                log.info('SQS queue deleted: %s', short_name)

        return retval
