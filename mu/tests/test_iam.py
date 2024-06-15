import pytest

from mu.libs import iam


@pytest.fixture
def roles(b3_sess):
    return iam.Roles(b3_sess)


@pytest.fixture
def policies(b3_sess):
    return iam.Policies(b3_sess)


def is_policy_attached(b3_iam, role_name, policy_name):
    for policy in b3_iam.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']:
        if policy['PolicyName'] == policy_name:
            return policy['Arn']


class TestRoles:
    role_name = 'greek-mu-lambda-test'
    logs_policy = f'{role_name}-logs'
    repo_name = 'greek-mu-test'

    @pytest.fixture(autouse=True)
    def reset_aws(self, roles, policies):
        roles.delete(self.role_name)
        policies.delete(self.logs_policy)

    def test_ensure_role(self, roles):
        roles.ensure_role(self.role_name, {'Service': 'lambda.amazonaws.com'}, {})

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

        # Ensure calling again is ok
        roles.ensure_role(self.role_name, {'Service': 'lambda.amazonaws.com'}, {})

        # Ensure that an update works
        roles.ensure_role(self.role_name, {'Service': 's3.amazonaws.com'}, {})

        role = roles.get(self.role_name)
        statement = role['AssumeRolePolicyDocument']['Statement'][0]

        assert statement['Principal'] == {'Service': 's3.amazonaws.com'}

    def test_attach_policy(self, roles, policies: iam.Policies):
        roles.ensure_role(self.role_name, {'Service': 'lambda.amazonaws.com'}, {})

        logs_policy = iam.policy_doc('logs:PutLogEvents', resource='arn:aws:logs:*:*:*')
        roles.attach_policy(self.role_name, 'logs', logs_policy)

        policy = policies.get(self.logs_policy)

        assert policy.has_role_attachment(self.role_name)
        assert policy.document == logs_policy

        logs_policy_doc = iam.policy_doc('logs:CreateLogsStream', resource='arn:aws:logs:*:*:*')
        roles.attach_policy(self.role_name, 'logs', logs_policy_doc)

        # clear cache on .document
        del policy.document
        assert policy.statement['Action'] == ['logs:CreateLogsStream']
