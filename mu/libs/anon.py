import base64
import io
import json
import logging
import shutil
import zipfile

import arrow
import boto3
import botocore.exceptions
import docker
from methodtools import lru_cache  # respects instance lifetimes
import requests

from mu.config import Config

from . import auth, ecr, iam, sts


log = logging.getLogger(__name__)


class Lambda:
    # Lambda
    lambda_timeout = 900
    lambda_memory = 4096

    logs_policy: dict = iam.policy_doc(
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents',
        resource='arn:aws:logs:*:*:*',
    )

    def __init__(self, config: Config, b3_sess: boto3.Session | None = None):
        self.config: Config = config
        self.b3_sess = b3_sess = b3_sess or auth.b3_sess(config.aws_region)

        self.ident = config.lambda_name
        self.image_name = config.image_name
        self.lambda_name = config.lambda_name
        self.aws_acct_id = sts.account_id(b3_sess)

        self.lc = b3_sess.client('lambda')
        self.docker = docker.from_env()

        self.roles = iam.Roles(b3_sess)
        self.repos = ecr.Repos(b3_sess)

    def repo_name(self, env: str):
        return self.config.repo_name(env)

    def repo(self, env: str) -> ecr.Repo:
        return self.repos.get(self.repo_name(env))

    def role_arn(self, env) -> str:
        role_name: str = self.config.lambda_env(env)
        return self.roles.arn(role_name)

    def provision_role(self, env: str):
        role_name: str = self.config.lambda_env(env)
        role_arn: str = self.role_arn(env)

        # Ensure the role exists and give lambda permission to use it.
        self.roles.ensure_role(role_name, {'Service': 'lambda.amazonaws.com'})

        # Give permission to create logs
        self.roles.attach_policy(role_name, 'logs', self.logs_policy)

        # Give permission to get images from the container registry
        policy = iam.policy_doc(*self.repos.policy_actions, resource=role_arn)
        self.roles.attach_policy(role_name, 'ecr-repo', policy)

        return role_arn

    def provision_repo(self, env: str, role_arn: str):
        # TODO: can probably remove this once testing is fast enough that we don't need to run
        # a separate test_provision_repo().  Besides, those tests should probably move to
        # test_ecr.py.
        self.repos.ensure(self.repo_name(env), role_arn)

    def provision(self, *envs):
        """Provision AWS dependencies for the lambda function."""

        for env_name in envs:
            role_arn: str = self.provision_role(env_name)
            self.provision_repo(env_name, role_arn)

        log.info(f'Provision finished for env: {env_name}')

    def ensure_func(self, env_name: str, image_uri: str):
        lambda_name = self.config.lambda_name_env(env_name)

        log.info('Deploying: %s', image_uri)

        # TODO: should get these values from the config
        shared_config = {
            'FunctionName': lambda_name,
            'Role': self.role_arn(env_name),
            'Timeout': self.lambda_timeout,
            'MemorySize': self.lambda_memory,
            'LoggingConfig': {
                'LogFormat': 'JSON',
                'ApplicationLogLevel': 'INFO',
                'SystemLogLevel': 'INFO',
            },
            'Environment': {
                'Variables': self.config.environ(),
            },
        }

        try:
            self.lc.create_function(
                PackageType='Image',
                Code={'ImageUri': image_uri},
                **shared_config,
            )
            print(f'Lambda function created: {lambda_name}')
        except self.lc.exceptions.ResourceConflictException:
            try:
                self.lc.update_function_configuration(**shared_config)
                self.wait_updated(lambda_name)

                self.lc.update_function_code(
                    FunctionName=lambda_name,
                    ImageUri=image_uri,
                )

                log.info(f'Lambda function updated: {lambda_name}')

            except self.lc.exceptions.InvalidParameterValueException as e:
                # TODO: don't need this if not doing zips
                needle = "don't provide ImageUri when updating a function with packageType Zip"
                if needle not in str(e):
                    raise
                log.warning("Existing function is Zip type, can't update.  Deleting.")

                self.delete_func(env_name)
                self.create_func(image_uri, lambda_name)

    def delete_func(self, env_name):
        lambda_name = self.lambda_name(env_name)
        self.lc.delete_function(
            FunctionName=lambda_name,
        )
        print(f'Lambda function {lambda_name} deleted.')

    def deploy(self, target_envs):
        for env in target_envs:
            repo: ecr.Repo = self.repo(env)
            image_tag: str = repo.push(self.config.image_name)
            image_uri = f'{repo.uri}:{image_tag}'
            self.ensure_func(env, image_uri)

        lambda_name = self.config.lambda_name_env(env)
        self.wait_updated(lambda_name)

    def wait_updated(self, lambda_name: str):
        log.info('Waiting for lambda to be updated: %s', lambda_name)
        waiter = self.lc.get_waiter('function_updated_v2')
        waiter.wait(FunctionName=lambda_name)

    def wait_active(self, lambda_name: str):
        log.info('Waiting for lambda to be active: %s', lambda_name)
        waiter = self.lc.get_waiter('function_active_v2')
        waiter.wait(FunctionName=lambda_name)

    def invoke(self, env_name: str, action: str):
        event = {self.config.action_key: action}
        response = self.lc.invoke(
            FunctionName=self.config.lambda_name_env(env_name),
            # TODO: maybe enable 'Event' for InvocationType for async invocation
            InvocationType='RequestResponse',
            Payload=bytes(json.dumps(event), encoding='utf8'),
        )

        return json.loads(response['Payload'].read())

    def invoke_rei(self, host, action: str):
        url = f'http://{host}/2015-03-31/functions/function/invocations'
        event = {self.config.action_key: action}
        resp = requests.post(url, json=event)
        return resp.json()

    def logs(self, env_name: str, limit: int, from_head: bool):
        logs_client = self.b3_sess.client('logs')
        lambda_name = self.config.lambda_name_env(env_name)

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
                rec: dict = json.loads(event['message'])
                rec_type = rec.get('type')
                if rec_type is None:
                    print(rec['timestamp'], rec['level'], rec['logger'], rec['message'])
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
