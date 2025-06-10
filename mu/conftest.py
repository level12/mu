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


@pytest.fixture(scope='session')
def config(b3_sess):
    return testing.config(b3_sess)
