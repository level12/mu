import docker
import docker.errors
import pytest

from mu.config import Config
from mu.libs import ecr, iam


@pytest.fixture(scope='module')
def repos(b3_sess):
    return ecr.Repos(b3_sess)


@pytest.fixture
def roles(b3_sess):
    return iam.Roles(b3_sess)


@pytest.fixture(scope='module')
def config(b3_sess):
    conf = Config('qa', project_org='greek', project_name='mu')
    conf.apply_sess(b3_sess)
    return conf


@pytest.fixture
def role_arn(roles, config):
    roles.ensure_role(config.resource_ident, {'Service': 'lambda.amazonaws.com'}, ())
    return config.role_arn


@pytest.fixture(scope='module')
def hw_tag():
    docker_ensure('hello-world')
    created = ecr.LocalImage('hello-world').created_utc()
    return f'hello-world-{created}'


@pytest.fixture(scope='module')
def bb_tag():
    docker_ensure('busybox')
    created = ecr.LocalImage('busybox').created_utc()
    return f'busybox-{created}'


def docker_ensure(img):
    doc = docker.from_env()

    try:
        doc.images.get(img)
    except docker.errors.ImageNotFound:
        doc.images.pull(img)


class TestECR:
    @pytest.fixture(autouse=True, scope='class')
    def prep(self, repos, config: Config):
        repos.delete(config.resource_ident, force=True)

    def test_tag_local(self, repos: ecr.Repos, role_arn: str, hw_tag: str, config: Config):
        repo = repos.ensure(config.resource_ident, role_arn)
        tag = repo.tag_local('hello-world')
        assert tag == hw_tag

    def test_push(self, repos: ecr.Repos, role_arn: str, hw_tag: str, bb_tag: str, config: Config):
        repo = repos.ensure(config.resource_ident, role_arn)

        repo.push('hello-world')
        repo.tag_remote(hw_tag, 'hello-world-foo')

        assert repo.tags() == ['hello-world-foo', hw_tag]

        repo.push('busybox')
        assert repo.tags() == [
            'hello-world-foo',
            hw_tag,
            bb_tag,
        ]

        assert repo.tags(prefix='hello-world') == [
            'hello-world-foo',
            hw_tag,
        ]
        assert repo.latest_tag('hello-world') == 'hello-world-foo'
