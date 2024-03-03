import contextlib

import pytest

from mu.libs import iam


def delete_role(b3_iam, role_name):
    attached = b3_iam.list_attached_role_policies(RoleName=role_name)
    for idents in attached.get('AttachedPolicies', []):
        b3_iam.detach_role_policy(RoleName=role_name, PolicyArn=idents['PolicyArn'])

    with contextlib.suppress(b3_iam.exceptions.NoSuchEntityException):
        b3_iam.delete_role(RoleName=role_name)


@pytest.fixture
def delete_policies(b3_iam):
    iam.Policy.delete_all(b3_iam)


def is_policy_attached(b3_iam, role_name, policy_name):
    for policy in b3_iam.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']:
        if policy['PolicyName'] == policy_name:
            return policy['Arn']


class TestRolesUtil:
    @pytest.fixture
    def ru(self, b3, b3_iam, aws_acct_id) -> iam.RolesUtil:
        self.role_name = __name__ + self.__class__.__name__
        delete_role(b3_iam, self.role_name)

        ru = iam.RolesUtil(b3, aws_acct_id)
        ru.ensure_role(self.role_name, {'Service': 'lambda.amazonaws.com'})
        return ru

    def test_ensure_role(self, ru, b3_iam):
        role = b3_iam.get_role(RoleName=self.role_name)['Role']
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
        ru.ensure_role(self.role_name, {'Service': 'lambda.amazonaws.com'})

        # Ensure that an update works
        ru.ensure_role(self.role_name, {'Service': 's3.amazonaws.com'})

        role = b3_iam.get_role(RoleName=self.role_name)['Role']
        statement = role['AssumeRolePolicyDocument']['Statement'][0]

        assert statement['Principal'] == {'Service': 's3.amazonaws.com'}

    def test_attach_policy(self, ru, b3_iam, aws_acct_id, delete_policies):
        logs_policy = iam.policy_doc('logs:PutLogEvents', policy='arn:aws:logs:*:*:*')

        ru.attach_policy(self.role_name, 'allow-logs', logs_policy)

        policy_name = f'{self.role_name}-allow-logs'
        policy = iam.Policy.get(b3_iam, aws_acct_id, policy_name)

        assert policy.has_role_attachment(self.role_name)
        assert policy.document == logs_policy

        logs_policy = iam.policy_doc('logs:CreateLogsStream', policy='arn:aws:logs:*:*:*')
        ru.attach_policy(self.role_name, 'allow-logs', logs_policy)

        # clear cache on .document
        del policy.document
        assert policy.statement['Action'] == ['logs:CreateLogsStream']
