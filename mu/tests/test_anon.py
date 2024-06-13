import logging

import pytest

import mu.config
from mu.libs import ecr, iam
from mu.libs.lamb import Lambda
from mu.libs.testing import Logs


@pytest.fixture
def roles(b3_sess):
    return iam.Roles(b3_sess)


@pytest.fixture
def policies(b3_sess):
    return iam.Policies(b3_sess)


@pytest.fixture
def repos(b3_sess):
    return ecr.Repos(b3_sess)


def config():
    return mu.config.Config(
        env='qa',
        project_org='Greek',
        project_name='mu',
    )


class TestLambda:
    role_name = 'greek-mu-lambda-func-qa'
    logs_policy = f'{role_name}-logs'
    ecr_repo_policy = f'{role_name}-ecr-repo'
    repo_name = role_name

    @pytest.fixture(autouse=True)
    def reset_aws(self, roles, policies, repos):
        roles.delete(self.role_name)
        policies.delete(self.logs_policy, self.ecr_repo_policy)
        repos.delete(self.repo_name, force=True)

    def test_provision_role(self, b3_sess, policies, roles, caplog):
        caplog.set_level(logging.INFO)

        anon = Lambda(config(), b3_sess)
        anon.provision_role()

        role = roles.get(self.role_name)
        assert role['AssumeRolePolicyDocument'] == {
            'Statement': [
                {
                    'Action': 'sts:AssumeRole',
                    'Effect': 'Allow',
                    'Principal': {'Service': 'lambda.amazonaws.com'},
                    'Sid': '',
                },
            ],
            'Version': '2012-10-17',
        }

        policy = policies.get(self.ecr_repo_policy)
        assert policy.document == {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': [
                        'ecr:GetDownloadUrlForLayer',
                        'ecr:BatchGetImage',
                        'ecr:BatchCheckLayerAvailability',
                    ],
                    'Resource': f'arn:aws:iam::429829037495:role/{self.role_name}',
                    'Effect': 'Allow',
                },
            ],
        }

        policy = policies.get(self.logs_policy)
        assert policy.document == {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
                    'Resource': 'arn:aws:logs:*:*:*',
                    'Effect': 'Allow',
                },
            ],
        }

        # Should be able to run it with existing resources and not get any errors.
        anon.provision_role()

        log_messages = [rec.message for rec in caplog.records]

        assert log_messages == [
            f'Role created: {self.role_name}',
            f'Policy created: {self.logs_policy}',
            f'Policy created: {self.ecr_repo_policy}',
            'Policy created: greek-mu-lambda-func-qa-sqs-queues',
            f'Role existed, assume role policy updated: {self.role_name}',
            f'Policy existed, document current: {self.logs_policy}',
            f'Policy existed, document current: {self.ecr_repo_policy}',
            'Policy existed, document current: greek-mu-lambda-func-qa-sqs-queues',
        ]

    def test_provision_repo(self, b3_sess, repos: ecr.Repos, caplog):
        caplog.set_level(logging.INFO)

        anon = Lambda(config(), b3_sess)
        anon.provision_role()

        caplog.clear()
        anon.provision_repo()

        repo = repos.get(self.repo_name)
        assert repo.get_policy() == {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': [
                        'ecr:GetDownloadUrlForLayer',
                        'ecr:BatchGetImage',
                        'ecr:BatchCheckLayerAvailability',
                    ],
                    'Principal': {'AWS': f'arn:aws:iam::429829037495:role/{self.role_name}'},
                    'Effect': 'Allow',
                },
            ],
        }

        anon.provision_repo()
        log_messages = [rec.message for rec in caplog.records if 'Waiting' not in rec.message]

        assert log_messages == [
            f'Repository created: {self.repo_name}',
            f'Repository existed: {self.repo_name}',
        ]

    def test_provision_func(self, b3_sess, logs: Logs):
        anon = Lambda(config(), b3_sess)
        anon.provision()

        assert logs.messages[-1] == 'Provision finished for: greek-mu-func-qa'
