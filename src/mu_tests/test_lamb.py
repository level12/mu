import logging

import pytest

import mu.config
from mu.libs import ecr, iam, testing
from mu.libs.lamb import FunctionPermissions, Lambda, PolicyStatement
from mu.libs.testing import Logs, data_read
from mu_tests.data import log_events


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
    res_ident = 'greek-mu-lambda-func-qa'
    logs_policy = f'{res_ident}-logs'
    ecr_repo_policy = f'{res_ident}-ecr-repo'
    sqs_policy = f'{res_ident}-sqs-queues'
    lambda_policy = f'{res_ident}-lambda'
    repo_name = res_ident

    @pytest.fixture(autouse=True)
    def reset_aws(self, roles, policies, repos):
        roles.delete(self.res_ident)
        policies.delete(self.logs_policy, self.ecr_repo_policy)
        repos.delete(self.repo_name, force=True)

    def test_provision_role(
        self,
        b3_sess,
        policies: iam.Policies,
        roles,
        caplog,
        aws_acct_id,
        aws_region,
    ):
        caplog.set_level(logging.INFO)

        anon = Lambda(config(), b3_sess)
        anon.provision_role()

        role = roles.get(self.res_ident)
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

        pols = policies.list(prefix=self.res_ident)
        assert len(pols) == 4

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
                    'Resource': f'arn:aws:ecr:{aws_region}:{aws_acct_id}:repository/{self.res_ident}',  # noqa
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

        policy = policies.get(self.sqs_policy)
        assert policy.document == {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': [
                        'sqs:SendMessage',
                        'sqs:ReceiveMessage',
                        'sqs:DeleteMessage',
                        'sqs:GetQueueAttributes',
                        'sqs:GetQueueUrl',
                        'sqs:ChangeMessageVisibility',
                        'sqs:PurgeQueue',
                    ],
                    'Resource': f'arn:aws:sqs:{aws_region}:{aws_acct_id}:{self.res_ident}-*',
                    'Effect': 'Allow',
                },
            ],
        }

        policy = policies.get(self.lambda_policy)
        assert policy.document == {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': [
                        'lambda:InvokeFunction',
                    ],
                    'Resource': f'arn:aws:lambda:{aws_region}:{aws_acct_id}:function:greek-mu-func-qa',  # noqa: E501
                    'Effect': 'Allow',
                },
            ],
        }

        # Should be able to run it with existing resources and not get any errors.
        anon.provision_role()

        log_messages = [rec.message for rec in caplog.records]

        assert log_messages == [
            f'Role created: {self.res_ident}',
            f'Policy created: {self.logs_policy}',
            f'Policy created: {self.ecr_repo_policy}',
            'Policy created: greek-mu-lambda-func-qa-sqs-queues',
            'Attaching managed policy: AWSLambdaVPCAccessExecutionRole',
            'Policy created: greek-mu-lambda-func-qa-lambda',
            f'Role existed, assume role policy updated: {self.res_ident}',
            f'Policy existed, document current: {self.logs_policy}',
            f'Policy existed, document current: {self.ecr_repo_policy}',
            'Policy existed, document current: greek-mu-lambda-func-qa-sqs-queues',
            'Attaching managed policy: AWSLambdaVPCAccessExecutionRole',
            'Policy existed, document current: greek-mu-lambda-func-qa-lambda',
        ]

    def test_provision_repo(self, b3_sess, repos: ecr.Repos, caplog):
        caplog.set_level(logging.INFO)

        anon = Lambda(config(), b3_sess)
        anon.provision_role()

        caplog.clear()
        anon.provision_repo()

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


class TestLambdaLogs:
    def check_event(self, capsys, event: dict, fname: str):
        Lambda.log_event_print(event)
        expected = data_read(fname)
        assert capsys.readouterr().out.strip() == expected.strip()

    def test_platform_report(self, capsys):
        self.check_event(capsys, log_events.platform_report, 'platform-report.txt')

    def test_platform_start(self, capsys):
        self.check_event(capsys, log_events.platform_start, 'platform-start.txt')

    def test_unhandled_exc(self, capsys):
        self.check_event(capsys, log_events.unhandled_exc, 'unhandled-exc.txt')

    def test_text_message(self, capsys):
        self.check_event(capsys, log_events.text_message, 'text-message.txt')

    def test_exc_extras(self, capsys):
        self.check_event(capsys, log_events.exc_extras, 'exc-extras.txt')


@pytest.mark.integration
class TestLambdaCRUD:
    def test_permissions(self, config: mu.config.Config, b3_sess, logs: Logs):
        statement_id = config.api_invoke_stmt_id
        lambda_perms = FunctionPermissions(b3_sess)
        assert lambda_perms._list_recs is None

        # Recreate the tmp lambda so we can be sure no permissions exist on it at the start of the
        # test
        tmp_la = testing.tmp_lambda(b3_sess, config, recreate=True)
        config._func_arn_override = tmp_la.FunctionArn
        logs.clear()

        # # Ensure created
        lambda_perms.ensure(
            statement_id,
            config=config,
            perm_type='api-invoke',
            api_key='foo',
        )
        stmt: PolicyStatement = lambda_perms.get(statement_id)
        assert stmt.Sid == statement_id
        assert stmt.Effect == 'Allow'
        assert stmt.Action == 'lambda:InvokeFunction'
        assert stmt.Principal == {'Service': 'apigateway.amazonaws.com'}
        assert stmt.Condition == {
            'ArnLike': {'AWS:SourceArn': 'arn:aws:execute-api:us-east-2:429829037495:foo/*/*'},
        }

        # No error when exists and should be cached
        lambda_perms.ensure(
            statement_id,
            config=config,
            perm_type='api-invoke',
            api_key='foo',
        )
        assert lambda_perms.get(statement_id)

        # Delete
        lambda_perms.delete(statement_id, tmp_la.FunctionArn)
        assert lambda_perms.get(statement_id, tmp_la.FunctionArn) is None

        # No error when not present
        lambda_perms.delete(statement_id, tmp_la.FunctionArn)

        assert logs.messages == [
            'FunctionPermissions ensure: record created',
            'FunctionPermissions ensure: record existed',
            'FunctionPermissions delete: record deleted',
        ]
