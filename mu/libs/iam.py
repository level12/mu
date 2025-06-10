import functools
import json
import logging

import boto3
from methodtools import lru_cache

from . import sts


log = logging.getLogger(__name__)


def policy_doc(*actions, resource=None, principal=None, effect='Allow', condition=None):
    assert resource or principal
    assert not (resource and principal)

    condition = {} if not condition else {'Condition': condition}

    if resource:
        key_name = 'Resource'
        value = resource
    else:
        key_name = 'Principal'
        value = principal

    return {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Action': list(actions),
                key_name: value,
                'Effect': effect,
            }
            | condition,
        ],
    }


class Policy:
    def __init__(self, b3_sess, iam, rec: dict):
        self.iam = iam
        self.rec = rec
        self.b3_sess = b3_sess

    def __getattr__(self, item: str):
        aws_name = item.replace('_', ' ').title().replace(' ', '')

        if aws_name in self.rec:
            return self.rec[aws_name]

        raise AttributeError(item)

    @classmethod
    def get(cls, b3_sess, iam, arn):
        return cls(b3_sess, iam, iam.get_policy(PolicyArn=arn)['Policy'])

    @classmethod
    def list(cls, b3_iam, scope='Local'):
        result = b3_iam.list_policies(Scope=scope)
        for policy in result.get('Policies', []):
            yield cls(b3_iam, policy)

    @functools.cached_property
    def document(self):
        for version in self.versions():
            if version['IsDefaultVersion']:
                full_version = self.iam.get_policy_version(
                    PolicyArn=self.arn,
                    VersionId=version['VersionId'],
                )
                return full_version['PolicyVersion']['Document']

    @property
    def statement(self):
        return self.document['Statement'][0]

    def role_attachments(self):
        result = self.iam.list_entities_for_policy(PolicyArn=self.arn)
        yield from result.get('PolicyRoles', ())

    def versions(self):
        result = self.iam.list_policy_versions(PolicyArn=self.arn)
        yield from result.get('Versions', ())

    def delete(self):
        for attachment in self.role_attachments():
            self.iam.detach_role_policy(RoleName=attachment['RoleName'], PolicyArn=self.arn)

        policy_arn = self.rec['Arn']
        if sts.account_id(self.b3_sess) not in policy_arn:
            # An AWS managed role (e.v. AWSLambdaVPCAccessExecutionRole), can't delete.
            log.info('Not deleting external policy: %s', policy_arn)
            return

        for version in self.versions():
            # Can't delete default version
            if version['IsDefaultVersion']:
                continue

            self.iam.delete_policy_version(PolicyArn=self.arn, VersionId=version['VersionId'])

        self.iam.delete_policy(PolicyArn=self.arn)

    @classmethod
    def delete_all(cls, b3_iam):
        for policy in cls.list(b3_iam):
            policy.delete()

    @classmethod
    def create(cls, b3_sess, b3_iam, name: str, doc: dict):
        return cls(
            b3_sess,
            b3_iam,
            b3_iam.create_policy(
                PolicyName=name,
                PolicyDocument=json.dumps(doc),
            )['Policy'],
        )

    def has_role_attachment(self, role_name):
        return any(ra['RoleName'] == role_name for ra in self.role_attachments())


class Policies:
    def __init__(self, b3_sess):
        self.iam = b3_sess.client('iam')
        self.b3_sess = b3_sess

    @lru_cache()
    def list(self, prefix=None):
        policies = self.iam.list_policies(Scope='Local')['Policies']
        return {
            policy['PolicyName']: Policy(self.b3_sess, self.iam, policy)
            for policy in policies
            if prefix is None or policy['PolicyName'].startswith(prefix)
        }

    @property
    def policies(self):
        return self.list()

    def clear(self):
        self.list.cache_clear()

    def get(self, name) -> Policy:
        return self.policies.get(name)

    def add(self, policy: Policy):
        self.policies[policy.policy_name] = policy

    def delete(self, *names):
        for name in names:
            if name not in self.policies:
                continue

            self.policies[name].delete()
            del self.policies[name]

        self.clear()


class Roles:
    def __init__(self, b3_sess: boto3.Session):
        self.b3_sess = b3_sess
        self.iam = b3_sess.client('iam')
        self.policies = Policies(b3_sess)

    def get(self, role_name: str):
        return self.iam.get_role(RoleName=role_name)['Role']

    def delete(self, role_name: str):
        try:
            attached = self.iam.list_attached_role_policies(RoleName=role_name)
        except self.iam.exceptions.NoSuchEntityException:
            log.info('No policies existed for role: %s', role_name)
            return

        for idents in attached.get('AttachedPolicies', []):
            policy_arn = idents['PolicyArn']
            policy = Policy.get(self.b3_sess, self.iam, policy_arn)
            policy.delete()
            log.info('Policy deleted: %s', policy_arn)

        try:
            self.iam.delete_role(RoleName=role_name)
            log.info('Role deleted: %s', role_name)
        except self.iam.exceptions.NoSuchEntityException:
            log.info('Role not found: %s', role_name)

    def assume_role_policy(self, princpal) -> str:
        """Create policy statement to give AssumeRole to the given Principal"""
        # TODO: convert to use policy_doc()
        return json.dumps(
            {
                'Version': '2012-10-17',
                'Statement': [
                    {
                        'Action': 'sts:AssumeRole',
                        'Principal': princpal,
                        'Effect': 'Allow',
                        'Sid': '',
                    },
                ],
            },
        )

    def ensure_role(self, role_name: str, assume_role_princpal: dict, policy_arns: list[str]):
        """
        Ensure role exists and the AWS principal is allowed to use it.

        If role exists, ensure policy document is up-to-date for principal.
        """
        asr: str = self.assume_role_policy(assume_role_princpal)

        try:
            self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=asr,
            )
            log.info(f'Role created: {role_name}')
        except self.iam.exceptions.EntityAlreadyExistsException:
            self.iam.update_assume_role_policy(
                RoleName=role_name,
                PolicyDocument=asr,
            )
            log.info(f'Role existed, assume role policy updated: {role_name}')

        for arn in policy_arns:
            self.iam.attach_role_policy(
                RoleName=role_name,
                PolicyArn=arn,
            )
            log.info('Policy added to role: %s -> %s', arn, role_name)

    def attach_policy(self, role_name: str, policy_ident: str, policy_doc: dict):
        """
        Attach policy doc to the role.

        If policy doc already exists and doesn't match the given doc then a new default
        version of the policy is created with given doc.

        """
        policy_name = f'{role_name}-{policy_ident}'
        policy = self.policies.get(policy_name)

        if not policy:
            policy = Policy.create(self.b3_sess, self.iam, policy_name, policy_doc)
            self.policies.add(policy)
            log.info(f'Policy created: {policy_name}')

        elif policy.document != policy_doc:
            log.info(f'Policy existed, updating document: {policy_name}')
            self.iam.create_policy_version(
                PolicyArn=policy.arn,
                PolicyDocument=json.dumps(policy_doc),
                SetAsDefault=True,
            )
        else:
            log.info(f'Policy existed, document current: {policy_name}')

        self.iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn=policy.arn,
        )

    def attach_managed_policy(self, role_name, policy_name: str):
        # TODO: might not want /service-role/ at this level
        policy_arn = f'arn:aws:iam::aws:policy/service-role/{policy_name}'

        self.iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn=policy_arn,
        )
        log.info(f'Attaching managed policy: {policy_name}')
