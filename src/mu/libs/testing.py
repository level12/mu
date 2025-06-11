import io
import logging
from os import environ
from pathlib import Path
from unittest import mock
import zipfile

import mu.config
from mu.libs import auth, gateway, iam, lamb, sts
from mu_tests import data


PERSISTENT_CERT_DOMAIN = 'mu-testing-cert.level12.app'


def mock_patch_obj(*args, **kwargs):
    kwargs.setdefault('autospec', True)
    kwargs.setdefault('spec_set', True)
    return mock.patch.object(*args, **kwargs)


def mock_patch(*args, **kwargs):
    kwargs.setdefault('autospec', True)
    kwargs.setdefault('spec_set', True)
    return mock.patch(*args, **kwargs)


class Logs:
    def __init__(self, caplog):
        self.caplog = caplog
        caplog.set_level(logging.INFO)

    @property
    def messages(self):
        return [rec.message for rec in self.caplog.records]

    def clear(self):
        self.caplog.clear()

    def reset(self):
        self.caplog.clear()


def data_read(fname):
    return Path(data.__file__).parent.joinpath(fname).read_text()


def config(b3_sess=None):
    config = mu.config.Config(
        env='qa',
        project_org='Greek',
        project_name='mu',
    )
    if b3_sess:
        config.apply_sess(b3_sess)

    return config


def lambda_zip() -> bytes:
    py_body = """
def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/plain',
        },
        'body': 'Hello World from mu',
    }
"""

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        zip_file.writestr(
            'lambda_function.py',
            py_body,
        )
    zip_buffer.seek(0)
    return zip_buffer.getvalue()


def lambda_code():
    return {
        'Runtime': 'python3.12',
        'Handler': 'lambda_function.lambda_handler',
        'Code': {'ZipFile': lambda_zip()},
    }


def tmp_lambda(b3_sess, config: mu.config.Config, recreate=False) -> lamb.Function:
    lambda_name = config.lambda_ident + 'tmp-lambda'
    funcs = lamb.Functions(b3_sess)
    if recreate:
        funcs.delete(lambda_name)
    func = funcs.get(lambda_name)
    if not func:
        iam.Roles(b3_sess).ensure_role(
            config.resource_ident,
            {'Service': 'lambda.amazonaws.com'},
            config.policy_arns,
        )
    return funcs.ensure(lambda_name, Role=config.role_arn, **lambda_code())


def b3_sess(*, kind: str = 'fake'):
    assert kind in ('mu-testing-live', 'fake')
    if kind == 'fake':
        return auth.b3_sess(region_name='us-east-fake', testing=True)

    sess = auth.b3_sess()
    aid = sts.account_id(sess)

    # Ensure we aren't accidently working on an unintended account.
    assert aid == environ.get('MU_TEST_ACCT_ID')

    return sess


def persistent_cert(b3_sess) -> gateway.ACMCert:
    return gateway.ACMCerts(b3_sess).ensure(PERSISTENT_CERT_DOMAIN)
