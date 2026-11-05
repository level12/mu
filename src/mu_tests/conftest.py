import os
from unittest import mock

import boto3
from moto import mock_aws
import pytest

from mu.libs import sts, testing


def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'integration: use live AWS apis (use -m "not integration" to skip)',
    )


@pytest.fixture(scope='session')
def b3_sess():
    return testing.b3_sess(kind='mu-testing-live')


@pytest.fixture(scope='session')
def aws_acct_id(b3_sess):
    return sts.account_id(b3_sess)


@pytest.fixture(scope='session')
def aws_region(b3_sess):
    return b3_sess.region_name


@pytest.fixture
def logs(caplog):
    return testing.Logs(caplog)


@pytest.fixture
def config(b3_sess):
    return testing.config(b3_sess)


@pytest.fixture()
def moto():
    with mock_aws():
        yield


@pytest.fixture
def moto_sess(moto):
    with mock.patch.dict(os.environ):
        os.environ.pop('AWS_PROFILE', None)
        os.environ.pop('AWS_DEFAULT_PROFILE', None)
        yield boto3.Session(
            aws_access_key_id='testing',
            aws_secret_access_key='testing',
            region_name='us-east-1',
        )
