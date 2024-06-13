import logging
from unittest import mock


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
