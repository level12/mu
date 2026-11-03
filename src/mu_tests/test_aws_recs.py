from dataclasses import dataclass

import pytest

from mu.libs import testing
from mu.libs.aws_recs import AWSRec, AWSRecsCRUD
from mu.libs.testing import Logs


@dataclass
class Widget(AWSRec):
    Name: str
    Color: str

    @property
    def ident(self):
        return self.Name


class Widgets(AWSRecsCRUD):
    """In-memory stand-in for an AWS resource collection."""

    client_name = 'sts'
    rec_cls = Widget

    def __init__(self, b3_sess):
        super().__init__(b3_sess)
        self.store: dict[str, dict] = {}
        self.calls: list[str] = []

    def client_list(self):
        return list(self.store.values())

    def client_create(self, name, *, color):
        self.calls.append('create')
        self.store[name] = {'Name': name, 'Color': color}

    def client_delete(self, rec):
        self.calls.append('delete')
        del self.store[rec.Name]


class UpdatableWidgets(Widgets):
    ensure_updates = True

    def client_update(self, rec: Widget, *, color):
        self.calls.append('update')
        self.store[rec.Name]['Color'] = color


@pytest.fixture(scope='module')
def b3_sess():
    return testing.b3_sess()


class TestEnsure:
    def test_default_never_updates(self, b3_sess, logs: Logs):
        widgets = Widgets(b3_sess)
        widgets.ensure('w1', color='red')
        rec = widgets.ensure('w1', color='blue')

        assert rec.Color == 'red'
        assert widgets.calls == ['create']
        assert logs.messages == [
            'Widgets ensure: record created',
            'Widgets ensure: record existed',
        ]

    def test_existing_updated_in_place(self, b3_sess, logs: Logs):
        widgets = UpdatableWidgets(b3_sess)
        widgets.ensure('w1', color='red')
        rec = widgets.ensure('w1', color='blue')

        # Fresh record is returned, not the cached pre-update one.
        assert rec.Color == 'blue'
        assert widgets.calls == ['create', 'update']
        assert logs.messages == [
            'UpdatableWidgets ensure: record created',
            'UpdatableWidgets ensure: record existed, updated',
        ]

        # Updates on every ensure, even when nothing changed.
        widgets.ensure('w1', color='blue')
        assert widgets.calls == ['create', 'update', 'update']
