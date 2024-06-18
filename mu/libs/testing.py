import logging
from pathlib import Path
from unittest import mock

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


def data_read(fname):
    return Path(data.__file__).parent.joinpath(fname).read_text()
