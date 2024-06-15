from os import environ

import pytest

from mu.libs import auth, sts, testing


@pytest.fixture(scope='session')
def b3_sess():
    sess = auth.b3_sess()
    aid = sts.account_id(sess)

    # Ensure we aren't accidently working on an unintended account.
    assert aid == environ.get('MU_TEST_ACCT_ID')

    return sess


@pytest.fixture(scope='session')
def aws_acct_id(b3_sess):
    return sts.account_id(b3_sess)


@pytest.fixture(scope='session')
def aws_region(b3_sess):
    return b3_sess.region_name


@pytest.fixture
def logs(caplog):
    return testing.Logs(caplog)
