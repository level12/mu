import logging

import pytest

import mu.config
from mu.libs import ecr, iam
from mu.libs.anon import Lambda


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
        project_org='Greek',
        project_name='mu',
        project_ident='greek-mu',
        lambda_name='greek-mu-main',
        image_name='greek-mu-lambda',
        default_env='test',
        action_key='lambda-action',
    )


class TestLambda:
    role_name = 'greek-mu-lambda-test'
    logs_policy = f'{role_name}-logs'
    ecr_repo_policy = f'{role_name}-ecr-repo'
    repo_name = 'greek-mu-test'

    @pytest.fixture(autouse=True)
    def reset_aws(self, roles, policies, repos):
        roles.delete(self.role_name)

        policies.delete(self.logs_policy)
        policies.delete(self.ecr_repo_policy)
        policies.reset()

        repos.delete(self.repo_name, force=True)
        repos.reset()

    def test_provision_role(self, b3_sess, policies, roles, caplog):
        caplog.set_level(logging.INFO)

        anon = Lambda(config(), b3_sess)
        anon.provision_role('test')

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
        anon.provision_role('test')

        log_messages = [rec.message for rec in caplog.records]

        assert log_messages == [
            f'Role created: {self.role_name}',
            f'Policy created: {self.logs_policy}',
            f'Policy created: {self.ecr_repo_policy}',
            f'Role existed, assume role policy updated: {self.role_name}',
            f'Policy existed, document current: {self.logs_policy}',
            f'Policy existed, document current: {self.ecr_repo_policy}',
        ]

    def test_provision_repo(self, b3_sess, repos: ecr.Repos, caplog):
        caplog.set_level(logging.INFO)

        anon = Lambda(config(), b3_sess)
        role_arn: str = anon.provision_role('test')

        caplog.clear()
        anon.provision_repo('test', role_arn)

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

        anon.provision_repo('test', role_arn)
        log_messages = [rec.message for rec in caplog.records]

        assert log_messages == [
            f'Repository created: {self.repo_name}',
            f'Repository existed: {self.repo_name}',
        ]

    def test_provision_func(self, b3_sess, policies, roles, repos: ecr.Repos, caplog):
        caplog.set_level(logging.INFO)

        anon = Lambda(config(), b3_sess)
        anon.provision('test')
