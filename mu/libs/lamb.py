import functools
import json
import logging

import boto3
import docker
import requests

from mu.config import Config

from . import api_gateway, auth, ecr, iam, sqs, sts


log = logging.getLogger(__name__)


class Lambda:
    logs_policy: dict = iam.policy_doc(
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        resource='arn:aws:logs:*:*:*',
    )

    sqs_actions = (
        'sqs:SendMessage',
        'sqs:ReceiveMessage',
        'sqs:DeleteMessage',
        'sqs:GetQueueAttributes',
        'sqs:GetQueueUrl',
        'sqs:ChangeMessageVisibility',
        'sqs:PurgeQueue',
    )

    def __init__(self, config: Config, b3_sess: boto3.Session | None = None):
        self.config: Config = config
        self.b3_sess = b3_sess = b3_sess or auth.b3_sess(config.aws_region)
        config.apply_sess(b3_sess)

        self.ident = config.lambda_name
        self.image_name = config.image_name
        self.lambda_name = config.lambda_name

        self.lc = b3_sess.client('lambda')
        self.event_client = b3_sess.client('events')
        self.not_found_exc = (
            self.lc.exceptions.ResourceNotFoundException,
            self.event_client.exceptions.ResourceNotFoundException,
        )
        self.exists_exc = (self.lc.exceptions.ResourceConflictException,)
        self.docker = docker.from_env()

        self.roles = iam.Roles(b3_sess)
        self.repos = ecr.Repos(b3_sess)
        self.apis = api_gateway.APIs(b3_sess)
        self.sqs = sqs.SQS(b3_sess)

    def provision_role(self):
        role_name: str = self.config.resource_ident
        role_arn: str = self.config.role_arn

        # Ensure the role exists and give lambda permission to use it.
        self.roles.ensure_role(
            role_name,
            {'Service': 'lambda.amazonaws.com'},
            self.config.policy_arns,
        )

        # Give permission to create logs
        self.roles.attach_policy(role_name, 'logs', self.logs_policy)

        # Give permission to get images from the container registry
        policy = iam.policy_doc(*self.repos.policy_actions, resource=role_arn)
        self.roles.attach_policy(role_name, 'ecr-repo', policy)

        # Give permission to sqs queues
        policy = iam.policy_doc(*self.sqs_actions, resource=self.config.sqs_resource)
        self.roles.attach_policy(role_name, 'sqs-queues', policy)

    def provision_repo(self):
        # TODO: can probably remove this once testing is fast enough that we don't need to run
        # a separate test_provision_repo().  Besides, those tests should probably move to
        # test_ecr.py.
        self.repos.ensure(self.config.resource_ident, self.config.role_arn)

    def provision_aws_config(self):
        if sqs_configs := self.config.aws_configs('sqs'):
            self.sqs.sync_config(self.config.resource_ident, sqs_configs)
        else:
            self.sqs.delete(self.config.resource_ident)

    def provision(self):
        """Provision AWS dependencies for the lambda function."""

        self.provision_role()
        self.provision_repo()
        self.provision_aws_config()

        log.info(f'Provision finished for: {self.config.lambda_ident}')

    def ensure_func(self, env_name: str, image_uri: str):
        func_name = self.config.lambda_ident

        log.info('Deploying lambda function')

        # TODO: should get these values from the config
        shared_config = {
            'FunctionName': func_name,
            'Role': self.config.role_arn,
            'Timeout': self.config.lambda_timeout,
            'MemorySize': self.config.lambda_memory,
            'LoggingConfig': {
                'LogFormat': 'JSON',
                'ApplicationLogLevel': 'INFO',
                'SystemLogLevel': 'INFO',
            },
            'Environment': {
                'Variables': self.config.deployed_env,
            },
        }

        try:
            response = self.lc.create_function(
                PackageType='Image',
                Code={'ImageUri': image_uri},
                **shared_config,
            )
            log.info('Lambda function created')
        except self.exists_exc:
            try:
                response = self.lc.update_function_configuration(**shared_config)
                self.wait_updated(func_name)

                self.lc.update_function_code(
                    FunctionName=func_name,
                    ImageUri=image_uri,
                )

                log.info('Lambda function updated')

            except self.lc.exceptions.InvalidParameterValueException as e:
                # TODO: don't need this if not doing zips
                needle = "don't provide ImageUri when updating a function with packageType Zip"
                if needle not in str(e):
                    raise

                raise RuntimeError("Existing function is Zip type, can't update.") from e

        return response['FunctionArn']

    def delete_permissions(self, func_name):
        """TODO: this never deletes permissions.  Maybe b/c the lambda is already deleted?"""
        # Retrieve the current policy attached to the Lambda function
        try:
            policy = self.lc.get_policy(FunctionName=func_name)
        except self.lc.exceptions.ResourceNotFoundException:
            log.info('No policy found for this function.')
            return

        # Load the policy as JSON and extract statement IDs
        policy_document = json.loads(policy['Policy'])
        statements = policy_document.get('Statement', [])

        # Remove each permission statement by its StatementId
        for statement in statements:
            statement_id = statement['Sid']
            self.lc.remove_permission(
                FunctionName=func_name,
                StatementId=statement_id,
            )
            log.info(f'Removed permission {statement_id} from function')

    def delete(self, env_name, *, force_repo):
        lambda_name = self.config.lambda_ident
        resource_ident = self.config.resource_ident

        try:
            self.lc.delete_function(
                FunctionName=lambda_name,
            )
            log.info(f'Lambda function deleted: {lambda_name}')
        except self.not_found_exc:
            log.info(f'Lambda function not found: {lambda_name}')

        for rule_ident in self.config.event_rules:
            rule_name = f'{lambda_name}-{rule_ident}'

            try:
                self.event_client.remove_targets(Rule=rule_name, Ids=['lambda-func'])
                log.info(f'Event target deleted: {rule_name}')
            except self.not_found_exc:
                log.info(f'Event target not found: {rule_name}')

            # No exception thrown if the rule doesn't exist.
            self.event_client.delete_rule(Name=rule_name)

        self.roles.delete(resource_ident)
        # self.apis.delete(resource_ident)
        self.sqs.delete(resource_ident)

        try:
            self.lc.delete_function_url_config(FunctionName=lambda_name)
            log.info('Function URL config deleted')
        except self.not_found_exc:
            log.info('Function URL config not found')

        self.delete_permissions(lambda_name)

        if repo := self.repos.get(resource_ident):
            repo.delete(force=force_repo)
        else:
            log.info(f'Repository not found: {resource_ident}')

    def event_rules(self, env_name, func_arn):
        name_prefix = self.config.resource_ident
        for rule_ident, config in self.config.event_rules.items():
            rule_name = f'{name_prefix}-{rule_ident}'
            log.info('Adding event schedule: %s', rule_name)

            # TODO: better error handling
            assert 'rate' not in config or 'cron' not in config
            assert 'rate' in config or 'cron' in config

            resp = self.event_client.put_rule(
                Name=rule_name,
                State=config.get('state', 'enabled').upper(),
                ScheduleExpression=(
                    f'rate({config["rate"]})' if 'rate' in config else f'cron({config["cron"]})'
                ),
            )
            rule_arn = resp['RuleArn']

            lambda_event = {'do-action': config['action']}
            self.event_client.put_targets(
                Rule=rule_name,
                Targets=[{'Id': 'lambda-func', 'Arn': func_arn, 'Input': json.dumps(lambda_event)}],
            )

            try:  # noqa: SIM105
                self.lc.add_permission(
                    FunctionName=func_arn,
                    StatementId=rule_name,
                    Action='lambda:InvokeFunction',
                    Principal='events.amazonaws.com',
                    SourceArn=rule_arn,
                )
            except self.exists_exc:
                # TODO: do we need to be smarter about re-creating this?
                pass

            log.info('Rule arn: %s', rule_arn)

    # def api_gateway(self, func_arn: str) -> api_gateway.APIEndpoint:
    #     api: api_gateway.APIEndpoint = self.apis.ensure(self.config.api_name(env), func_arn)
    #     source_arn = f'arn:aws:execute-api:{self.aws_region}:{self.aws_acct_id}:{api.api_id}/*'

    #     try:
    #         self.lc.add_permission(
    #             FunctionName=func_arn,
    #             StatementId='HttpApiInvoke',
    #             Action='lambda:InvokeFunction',
    #             Principal='apigateway.amazonaws.com',
    #             SourceArn=source_arn,
    #         )
    #     except self.exists_exc:
    #         # TODO: do we need to be smarter about this case?
    #         pass

    #     return api

    def function_url(self, func_arn):
        try:
            resp = self.lc.create_function_url_config(
                FunctionName=func_arn,
                AuthType='NONE',
            )
            log.info('Function url config created')
        except self.exists_exc:
            resp = self.lc.get_function_url_config(FunctionName=func_arn)
            log.info('Function url config existed')

        try:
            # policy_stmt = iam.policy_doc(
            #     'lambda.InvokeFunctionUrl',
            #     resource=func_arn,
            #     condition={'StringEquals': {'lambda:FunctionUrlAuthType': 'NONE'}},
            # )
            self.lc.add_permission(
                FunctionName=func_arn,
                StatementId='AllowPublicAccessFunctionUrl',
                Action='lambda:InvokeFunctionUrl',
                Principal='*',
                FunctionUrlAuthType='NONE',
            )
            log.info('Function url config permission added')
        except self.exists_exc:
            # TODO: do we need to be smarter about re-creating this?
            log.info('Function url config permission existed')

        return resp['FunctionUrl']

    def _deploy(self, env):
        repo: ecr.Repo = self.repos.get(self.config.resource_ident)
        if not repo:
            log.error(
                'Repo not found: %s.  Do you need to provision first?',
                self.repo_name(env),
            )
            return

        image_tag: str = repo.push(self.config.image_name)
        image_uri = f'{repo.uri}:{image_tag}'
        func_arn = self.ensure_func(env, image_uri)

        self.event_rules(env, func_arn)
        # TODO: offer api gateway as a config option
        # api = self.api_gateway(env, func_arn)
        func_url = self.function_url(func_arn)

        func_ident = self.config.lambda_ident
        # The newly deployed app takes a bit to become active.  Wait for it to avoid prompt
        # testing of the newly deployed changes from getting an older not-updated lambda.  Not fun.
        self.wait_updated(func_ident)

        spacing = '\n' + ' ' * 13
        log.info(f'Repo name:{spacing}%s', repo.name)
        log.info(f'Image URI:{spacing}%s', image_uri)
        log.info(f'Function name:{spacing}%s', func_ident)
        log.info(f'Function URL:{spacing}%s', func_url)

    def deploy(self, target_envs):
        for env in target_envs:
            self._deploy(env)

    def wait_updated(self, lambda_name: str):
        log.info('Waiting for lambda to be updated...')
        waiter = self.lc.get_waiter('function_updated_v2')
        waiter.wait(FunctionName=lambda_name)

    def wait_active(self, lambda_name: str):
        log.info('Waiting for lambda to be active...')
        waiter = self.lc.get_waiter('function_active_v2')
        waiter.wait(FunctionName=lambda_name)

    def invoke(self, action: str, action_args: list):
        event = {self.config.action_key: action, 'action-args': action_args}
        response = self.lc.invoke(
            FunctionName=self.config.lambda_ident,
            # TODO: maybe enable 'Event' for InvocationType for async invocation
            InvocationType='RequestResponse',
            Payload=bytes(json.dumps(event), encoding='utf8'),
        )

        return json.loads(response['Payload'].read())

    def invoke_rei(self, host, action: str, action_args: list):
        event = {self.config.action_key: action, 'action-args': action_args}

        url = f'http://{host}/2015-03-31/functions/function/invocations'
        resp = requests.post(url, json=event)

        return resp.json()

    def logs(self, limit: int, from_head: bool):
        logs_client = self.b3_sess.client('logs')
        lambda_name = self.config.lambda_ident

        # TODO: after the lambda is updated and invoked, there is a few second delay until the
        # log output is converted over to the lastest lambda.  Can we let the user know when that
        # happens?  Well, the delay is there just from invoking too, even when an update hasn't
        # happened, so maybe that's just the delay for the output to get through AWS to cloudwatch.
        # TODO: we should support old log streems
        log_streams = logs_client.describe_log_streams(
            logGroupName=f'/aws/lambda/{lambda_name}',
            orderBy='LastEventTime',
            descending=True,
            limit=1,
        )

        if log_streams.get('logStreams'):
            log_stream_name = log_streams['logStreams'][0]['logStreamName']

            # TODO: we should support start and end times which the API supports
            log_events = logs_client.get_log_events(
                logGroupName=f'/aws/lambda/{lambda_name}',
                logStreamName=log_stream_name,
                # Default startFromHead is False (latest events first)
                startFromHead=from_head,
                limit=limit,
            )

            # TODO: can we stream (i.e. follow) them?
            # TODO: can format out the output better.  See misc/lambda-logs-example.txt
            for event in log_events['events']:
                try:
                    rec: dict = json.loads(event['message'])
                    rec_type = rec.get('type')
                    if rec_type is None:
                        print(
                            rec['timestamp'],
                            rec['level'],
                            rec['logger'],
                            rec['message'],
                        )
                        if st_lines := rec.get('stackTrace'):
                            print(rec.get('errorType', '') + ':', rec.get('errorMessage', ''))
                            print(''.join(st_lines))

                    elif rec_type == 'platform.start':
                        print(rec['time'], rec_type, 'version:', rec['record']['version'])
                    elif rec_type == 'platform.report':
                        record = rec['record']
                        print(rec['time'], rec_type)
                        print('   ', 'status:', record['status'])
                        for metric, value in record['metrics'].items():
                            print('   ', f'{metric}:', value)
                    else:
                        print(rec)
                except json.JSONDecodeError:
                    print(event)
        else:
            log.info(f'No log streams found for: {lambda_name}')

    # def placeholder_zip(self):
    #     zip_buffer = io.BytesIO()

    #     with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
    #         zip_file.writestr('placeholder.py', placeholder_code)

    #     # Move buffer position to beginning so it can be read from the start
    #     zip_buffer.seek(0)

    #     return zip_buffer.getvalue()

    # def deploy(self, env_name, force_deps=False):
    #     """Deploy source code as-is to lambda function."""
    #     lambda_name = self.lambda_name(env_name)

    #     reqs_fpath = reqs_dpath / 'aws.txt'
    #     dist_dpath = pkg_dpath / 'dist-aws'
    #     dist_app_dpath = dist_dpath / app_dname
    #     app_dpath = pkg_dpath / app_dname
    #     zip_fpath = pkg_dpath / f'{app_dname}-lambda.zip'

    #     # TODO: use lambda layers and/or use detection to know when any reqs change.  See
    #     # shiv utils for example.
    #     if force_deps and dist_dpath.exists():
    #         shutil.rmtree(dist_dpath)

    #     dist_dpath.mkdir(exist_ok=True)

    #     # TODO: why count?
    #     if _child_count(dist_dpath) == 0:
    #         log.info('Installing reqs to: %s', reqs_fpath)
    #         _sub_run(
    #             'pip',
    #             'install',
    #             '--platform',
    #             'manylinux2014',
    #             '--only-binary',
    #             ':all:',
    #             '--target',
    #             dist_dpath,
    #             '-r',
    #             reqs_fpath,
    #         )

    #     log.info('Building source code zip file...')
    #     if dist_app_dpath.exists():
    #         shutil.rmtree(dist_app_dpath)

    #     shutil.copytree(app_dpath, dist_app_dpath)

    #     if zip_fpath.exists():
    #         zip_fpath.unlink()

    #     shutil.make_archive(zip_fpath.with_suffix(''), 'zip', dist_dpath)

    #     log.info('Updating lambda configuration...')
    #     # TODO: handle error
    #     self.lc.update_function_configuration(
    #         FunctionName=lambda_name,
    #         Handler=self.handler,
    #         # TODO: set secrets
    #         # Environment={
    #         #     'Variables': {
    #         #         'KEY1': 'VALUE1',
    #         #         'KEY2': 'VALUE2',
    #         #     },
    #         # },
    #     )

    #     log.info('Updating lambda code...')
    #     # TODO: handle error
    #     self.lc.update_function_code(
    #         FunctionName=lambda_name,
    #         ZipFile=zip_fpath.read_bytes(),
    #     )

    #     print(f'Source code deployed as: {lambda_name}')
