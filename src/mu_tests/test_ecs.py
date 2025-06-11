import pytest

from mu.libs.ecs import ECS
from mu.libs.testing import Logs


@pytest.fixture(scope='module')
def ecs(b3_sess):
    return ECS(b3_sess)


@pytest.fixture(autouse=True, scope='module')
def cleanup(ecs):
    ecs.delete('test-')
    yield
    ecs.delete('test-')


class TestCluster:
    def test_ensure(self, ecs: ECS, logs: Logs):
        clust = ecs.cluster('test-enterprise')
        assert clust.exists is False

        clust.ensure()
        assert clust.exists

        assert 'test-enterprise' in ecs.clusters()
        clust.ensure()

        assert logs.messages == [
            'ECS cluster created: test-enterprise',
            'ECS cluster existed: test-enterprise',
        ]
