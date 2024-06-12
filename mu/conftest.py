from os import environ

import pytest

from mu.libs import auth, sts


@pytest.fixture(scope='session')
def b3_sess():
    sess = auth.b3_sess()
    aid = sts.account_id(sess)

    # Ensure we aren't accidently working on an unintended account.
    assert aid == environ.get('MU_TEST_ACCT_ID')

    return sess
