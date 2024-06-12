from os import environ

import pytest

from mu.libs import auth, sts


@pytest.fixture(scope='session')
def b3_sess():
    aid = sts.account_id(b3_sess)

    # Ensure we aren't accidently working on an unintended account.
    assert aid == environ.get('MU_TEST_ACCT_ID')

    return auth.b3_sess()
