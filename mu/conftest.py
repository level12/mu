from os import environ

import pytest

from mu.libs import auth, sts


@pytest.fixture(scope='session')
def b3_sess():
    return auth.b3_sess()


@pytest.fixture(autouse=True, scope='session')
def aws_acct_id(b3_sess):
    """autouse=True so that the check below is always ran before any destructive calls made."""
    aid = sts.account_id(b3_sess)

    # Ensure we aren't accidently working on an unintended account.
    assert aid == environ.get('MU_TEST_ACCT_ID')

    return aid


@pytest.fixture(scope='session')
def b3_iam(b3_sess):
    return b3_sess.client('iam')
