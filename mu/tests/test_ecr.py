import logging
from unittest import mock

import docker
import docker.errors
import pytest

import mu.config
from mu.libs import ecr, iam
from mu.libs.anon import Lambda


@pytest.fixture(scope='module')
def repos(b3_sess):
    return ecr.Repos(b3_sess)


@pytest.fixture
def roles(b3_sess):
    return iam.Roles(b3_sess)


@pytest.fixture
def role_arn(roles):
    return roles.ensure_role(TestECR.role_name, {'Service': 'lambda.amazonaws.com'})


@pytest.fixture(scope='module')
def hw_tag():
    created = ecr.LocalImage('hello-world').created_utc()
    return f'hello-world-{created}'


def docker_ensure(img):
    doc = docker.from_env()

    try:
        doc.images.get(img)
    except docker.errors.ImageNotFound:
        doc.images.pull(img)


class TestECR:
    role_name = 'greek-mu-lambda-test'
    repo_name = 'greek-mu-test'

    @pytest.fixture(autouse=True, scope='class')
    def prep(self, repos):
        docker_ensure('hello-world')
        docker_ensure('busybox')

        repos.delete(self.repo_name, force=True)
        repos.reset()

    def test_tag_local(self, repos: ecr.Repos, role_arn: str, hw_tag: str):
        repo = repos.ensure(self.repo_name, role_arn)
        tag = repo.tag_local('hello-world')
        assert tag == hw_tag

    def test_push(self, repos: ecr.Repos, role_arn: str, hw_tag: str):
        repo = repos.ensure(self.repo_name, role_arn)

        repo.push('hello-world')
        repo.tag_remote(hw_tag, 'hello-world-foo')

        assert repo.tags() == ['hello-world-foo', hw_tag]

        repo.push('busybox')
        assert repo.tags() == [
            'hello-world-foo',
            'hello-world-2023-05-02T16.49.27',
            'busybox-2024-01-17T21.49.12',
        ]

        assert repo.tags(prefix='hello-world') == [
            'hello-world-foo',
            'hello-world-2023-05-02T16.49.27',
        ]
        assert repo.latest_tag('hello-world') == 'hello-world-foo'
