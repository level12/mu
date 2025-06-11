#!/usr/bin/env python
# mise description="Create AWS IAM role for GitHub CI integration tests"


import click

from mu.libs import auth, iam, logs, sts


log = logs.logger()


@click.command()
@click.option('--role-name', default='mu-github-ci-role', help='Name of the IAM role to create')
@click.option('--github-org', default='level12', help='GitHub organization name')
@click.option('--github-repo', default='mu', help='GitHub repository name')
@click.option('--allow-user', is_flag=True, help='Allow current IAM user to assume the role')
@click.option(
    '--clear-policies',
    is_flag=True,
    help='Clear all existing policies before attaching new ones',
)
@logs.click_options
def main(
    role_name: str,
    github_org: str,
    github_repo: str,
    allow_user: bool,
    clear_policies: bool,
    log_level: str,
):
    """Create an IAM role for GitHub Actions to use for integration tests."""
    logs.init_logging(log_level)

    # Create a session with your AWS account
    b3_sess = auth.b3_sess()
    account_id = sts.account_id(b3_sess)
    log.info(f'Creating role in AWS account: {account_id}')

    # Get current user identity if needed
    # TODO: it doesn't work to use the "Current user" if we've assumed a role.  Clean this up
    # if/when someone else wants to test the CI role permissions locally.
    current_user_arn = 'arn:aws:iam::684642904613:user/randy.syring'

    # Initialize our IAM utilities
    roles = iam.Roles(b3_sess)

    # Define the GitHub OIDC provider
    github_provider = 'token.actions.githubusercontent.com'

    # Create statements for the trust policy
    statements = [
        # GitHub OIDC trust relationship
        {
            'Effect': 'Allow',
            'Principal': {
                'Federated': f'arn:aws:iam::{account_id}:oidc-provider/{github_provider}',
            },
            'Action': 'sts:AssumeRoleWithWebIdentity',
            'Condition': {
                'StringEquals': {
                    f'{github_provider}:aud': 'sts.amazonaws.com',
                },
                'StringLike': {
                    f'{github_provider}:sub': f'repo:{github_org}/{github_repo}:*',
                },
            },
        },
    ]

    # Add IAM user trust relationship if requested
    if current_user_arn:
        log.info(f'Adding user to trust policy: {current_user_arn}')
        statements.append(
            {
                'Effect': 'Allow',
                'Principal': {'AWS': current_user_arn},
                'Action': 'sts:AssumeRole',
            },
        )

    # Create the complete trust policy
    trust_policy = {
        'Version': '2012-10-17',
        'Statement': statements,
    }

    # Create or update the role with the trust policy
    try:
        roles.iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=iam.json.dumps(trust_policy),
            Description=f'Role for GitHub Actions CI in {github_org}/{github_repo}',
        )
        log.info(f'Role created: {role_name}')
    except roles.iam.exceptions.EntityAlreadyExistsException:
        roles.iam.update_assume_role_policy(
            RoleName=role_name,
            PolicyDocument=iam.json.dumps(trust_policy),
        )
        log.info(f'Role existed, assume role policy updated: {role_name}')

    # Clear existing policies if requested
    if clear_policies:
        log.info(f'Clearing existing policies from role: {role_name}')
        try:
            # List all attached policies
            attached_policies = roles.iam.list_attached_role_policies(RoleName=role_name)

            # Detach each policy
            for policy in attached_policies.get('AttachedPolicies', []):
                policy_arn = policy['PolicyArn']
                roles.iam.detach_role_policy(
                    RoleName=role_name,
                    PolicyArn=policy_arn,
                )
                log.info(f'Detached policy: {policy["PolicyName"]}')
        except Exception as e:
            log.error(f'Error clearing policies: {e}')

    # Consolidate policies to stay within AWS limit of 10 policies per role

    # 1. AWS Services policy (Lambda, API Gateway, EventBridge, ACM, Organizations)
    aws_services_policy = iam.policy_doc(
        # Lambda permissions
        'lambda:*',
        # API Gateway permissions
        'apigateway:*',
        'apigatewayv2:*',
        # EventBridge permissions
        'events:*',
        # ACM permissions
        'acm:*',
        # Organizations permissions
        'organizations:DescribeOrganization',
        resource='*',
    )
    roles.attach_policy(role_name, 'aws-services', aws_services_policy)

    # 2. ECR policy (includes auth token)
    ecr_policy = iam.policy_doc(
        'ecr:*',
        resource='*',
    )
    roles.attach_policy(role_name, 'ecr', ecr_policy)

    # 3. IAM policy (combined roles and policies)
    iam_actions = [
        'iam:CreateRole',
        'iam:DeleteRole',
        'iam:GetRole',
        'iam:PassRole',
        'iam:UpdateAssumeRolePolicy',
        'iam:CreatePolicy',
        'iam:DeletePolicy',
        'iam:GetPolicy',
        'iam:ListPolicies',
        'iam:ListPolicyVersions',
        'iam:CreatePolicyVersion',
        'iam:DeletePolicyVersion',
        'iam:GetPolicyVersion',
        'iam:AttachRolePolicy',
        'iam:DetachRolePolicy',
        'iam:ListAttachedRolePolicies',
        'iam:ListEntitiesForPolicy',
    ]

    iam_policy = {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Effect': 'Allow',
                'Action': iam_actions,
                'Resource': [
                    f'arn:aws:iam::{account_id}:role/*-mu-*',
                    f'arn:aws:iam::{account_id}:policy/*-mu-*',
                ],
            },
            {
                'Effect': 'Allow',
                'Action': [
                    'iam:GetPolicy',
                    'iam:ListPolicies',
                    'iam:ListEntitiesForPolicy',
                ],
                'Resource': '*',
            },
        ],
    }
    roles.attach_policy(role_name, 'iam', iam_policy)

    # 4. SQS policy
    sqs_policy = {
        'Version': '2012-10-17',
        'Statement': [
            {
                'Effect': 'Allow',
                'Action': 'sqs:*',
                'Resource': [
                    f'arn:aws:sqs:*:{account_id}:*-mu-*',
                    f'arn:aws:sqs:*:{account_id}:test-*',
                ],
            },
            {
                'Effect': 'Allow',
                'Action': 'sqs:ListQueues',
                'Resource': '*',
            },
        ],
    }
    roles.attach_policy(role_name, 'sqs', sqs_policy)

    # 5. CloudWatch Logs policy
    logs_policy = iam.policy_doc(
        'logs:*',
        resource='arn:aws:logs:*:*:*',
    )
    roles.attach_policy(role_name, 'logs', logs_policy)

    # 6. ECS policy
    ecs_policy = iam.policy_doc(
        'ecs:*',
        resource='*',
    )
    roles.attach_policy(role_name, 'ecs', ecs_policy)

    log.info(f'Role {role_name} has been configured with all necessary permissions')
    log.info(f'Role ARN: arn:aws:iam::{account_id}:role/{role_name}')

    log.info('To use this role with GitHub Actions, add the following to your workflow:')
    log.info(f'  role-to-assume: arn:aws:iam::{account_id}:role/{role_name}')


if __name__ == '__main__':
    main()
