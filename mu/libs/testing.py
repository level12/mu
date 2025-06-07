from contextlib import contextmanager
import io
import logging
from pathlib import Path
from unittest import mock
import zipfile

import mu.config
from mu.libs import auth, gateway
from mu.tests import data


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


@contextmanager
def tmp_lambda(b3_sess, config):
    lambda_name = config.lambda_ident + 'tmp-lambda'
    lambdas = gateway.Lambdas(b3_sess)
    la = lambdas.ensure(lambda_name, Role=config.role_arn, **lambda_code())
    yield la


def b3_sess():
    return auth.b3_sess('us-east-fake', testing=True)
