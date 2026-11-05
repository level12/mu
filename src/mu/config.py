from dataclasses import asdict, dataclass, field
import functools
import logging
from os import environ
from pathlib import Path
import tomllib

from blazeutils.strings import simplify_string as slug
import boto3

from .libs import sts, utils


log = logging.getLogger(__name__)


def find_upwards(d: Path, filename: str):
    root = Path(d.root)

    while d != root:
        attempt = d / filename
        if attempt.exists():
            return attempt
        d = d.parent

    return None


def deep_get(d: dict, prefix: str, dotted_path: str, default=None, required=False):
    dotted_path = f'{prefix}{dotted_path}'
    keys = dotted_path.split('.')
    for key in keys:
        if key not in d:
            if required:
                raise ValueError(f'Expected a value in pyproject.yaml at: {dotted_path}')
            return default
        d = d[key]
    return d


def resolve_env(env_val: str):
    if env_val is False:
        return ''

    if env_val is True:
        return 'true'

    if not isinstance(env_val, str) or not env_val.startswith('op://'):
        return str(env_val)

    return op_read(env_val)


@functools.cache
def op_read(ref: str) -> str:
    """Cached so a deploy, which resolves the env for the lambda and the worker, only reads each
    secret from 1Password once."""
    result = utils.sub_run('op', 'read', '-n', ref, capture_output=True)
    return result.stdout.decode('utf-8')


@dataclass
class WorkerConfig:
    """
    ECS Fargate worker run from the same image as the lambda.

    Bring your own cluster, roles, log group, and security groups.  Uses the lambda's subnets.
    """

    # A list so that the first item can be used as the container's entry point.
    command: list[str]
    cluster_name: str
    execution_role_arn: str
    task_role_arn: str
    log_group_name: str
    security_group_names: list[str]
    service_name: str = ''
    cpu: int = 512
    memory: int = 1024  # MiB
    desired_count: int = 1
    assign_public_ip: bool = False
    cpu_architecture: str = 'X86_64'
    _env: dict[str, str] = field(default_factory=dict)

    @property
    def env(self) -> dict:
        return {k: resolve_env(v) for k, v in self._env.items()}


@dataclass
class Config:
    env: str
    project_org: str
    project_name: str
    domain_name: str | None = None
    _image_name: str = ''
    action_key: str = 'do-action'
    compose_service: str = 'app'  # for building
    app_runner_cpus: str | None = None
    app_runner_memory: str | None = None
    aws_config: dict = field(default_factory=dict)
    _project_ident: str = ''
    lambda_name: str = 'func'
    lambda_memory: int = 0  # MB
    lambda_timeout: int = 0  # secs
    aws_region: str | None = None
    aws_acct_id: str | None = None
    _deployed_env: dict[str, str] = field(default_factory=dict)
    event_rules: dict[str, dict[str, str]] = field(default_factory=dict)
    policy_arns: list[str] = field(default_factory=list)
    vpc_subnet_names: list[str] = field(default_factory=list)
    vpc_subnet_name_tag_key: str = 'Name'
    vpc_security_group_names: list[str] = field(default_factory=list)
    _func_arn_override: str | None = None
    mtls_truststore_uri: str = ''
    disable_execute_api_endpoint: bool = False
    disable_function_url: bool = False
    worker: WorkerConfig | None = None

    def apply_sess(self, sess: boto3.Session, testing=False):
        self.aws_region = sess.region_name
        try:
            self.aws_acct_id = '13579' if testing else sts.account_id(sess)
        except Exception as e:
            exc_str = str(type(e))
            if 'NoCredentialsError' in exc_str or 'ExpiredToken' in exc_str:
                log.warning('No AWS credentials found')
                return
            raise

    @property
    def project_env(self, env_name: str):
        return f'{self.project_ident}-{env_name}'

    @functools.cached_property
    def project_ident(self):
        return self._project_ident or f'{self.project_org}-{self.project_name}'

    @functools.cached_property
    def lambda_env(self):
        return f'{self.lambda_name}-{self.env}'

    @functools.cached_property
    def lambda_ident(self):
        return slug(f'{self.project_ident}-{self.lambda_env}')

    @functools.cached_property
    def resource_ident(self):
        return slug(f'{self.project_ident}-lambda-{self.lambda_env}')

    @functools.cached_property
    def image_name(self):
        return slug(self._image_name or self.project_ident)

    @property
    def role_arn(self):
        return f'arn:aws:iam::{self.aws_acct_id}:role/{self.resource_ident}'

    @property
    def function_arn(self):
        if self._func_arn_override:
            return self._func_arn_override

        return f'arn:aws:lambda:{self.aws_region}:{self.aws_acct_id}:function:{self.lambda_ident}'

    @property
    def repo_arn(self):
        return f'arn:aws:ecr:{self.aws_region}:{self.aws_acct_id}:repository/{self.resource_ident}'

    @property
    def sqs_resource(self):
        return f'arn:aws:sqs:{self.aws_region}:{self.aws_acct_id}:{self.resource_ident}-*'

    @property
    def api_invoke_stmt_id(self):
        return f'{self.resource_ident}-api-invoke'

    def aws_configs(self, kind: str):
        return self.aws_config.get(kind, {})

    @property
    def deployed_env(self):
        return self.deployed_env_gen(True)

    def deployed_env_gen(self, resolve: bool):
        return {
            name: resolve_env(val) if resolve else val for name, val in self._deployed_env.items()
        } | {
            'MU_ENV': self.env,
            'MU_RESOURCE_IDENT': self.resource_ident,
        }

    def for_print(self, resolve_env):
        config = asdict(self)

        config['deployed_env'] = self.deployed_env_gen(resolve_env)
        del config['_deployed_env']

        config['image_name'] = self.image_name
        del config['_image_name']

        config['project_ident'] = self.project_ident
        del config['_project_ident']

        config['lambda_ident'] = self.lambda_ident
        config['resource_ident'] = self.resource_ident
        config['role_arn'] = self.role_arn
        if self.worker:
            config['worker']['env'] = self.worker.env if resolve_env else self.worker._env
            del config['worker']['_env']
        return config


def default_env():
    return environ.get('MU_DEFAULT_ENV') or utils.host_user()


def load(start_at: Path, env: str, mu_fpath: Path | None = None) -> Config:
    pp_fpath = find_upwards(start_at, 'pyproject.toml')
    if pp_fpath is None:
        raise Exception(f'No pyproject.toml found in {start_at} or parents')
    with pp_fpath.open('rb') as fo:
        pp_config = tomllib.load(fo)

    if mu_fpath:
        if not mu_fpath.exists():
            raise Exception(f'Config file not found: {mu_fpath}')
        mu_fpath = mu_fpath
    else:
        mu_fpath = pp_fpath.with_name('mu.toml')

    if mu_fpath.exists():
        config_fpath = mu_fpath
        key_prefix = ''
    else:
        config_fpath = pp_fpath
        key_prefix = 'tool.mu.'

    with config_fpath.open('rb') as fo:
        config = tomllib.load(fo)
    get_config = functools.partial(deep_get, config, key_prefix)

    mtls_uri = get_config('mtls-truststore-uri', default='')
    worker = get_config('worker')

    return Config(
        env=env,
        project_org=get_config('project-org', required=True),
        project_name=deep_get(pp_config, '', 'project.name', required=True),
        domain_name=get_config('domain-name'),
        _project_ident=get_config('project-ident'),
        lambda_name=get_config('lambda-name', 'func'),
        _image_name=get_config('image-name'),
        action_key=get_config('lambda-action-key', default='do-action'),
        _deployed_env=get_config('deployed-env', default={}),
        event_rules=get_config('event-rules', default={}),
        lambda_memory=get_config('lambda-memory', default=2048),
        lambda_timeout=get_config('lambda-timeout', default=900),
        policy_arns=get_config('policy-arns', default=()),
        aws_config=get_config('aws', default={}),
        compose_service=get_config('compose-service', default='app'),
        vpc_subnet_names=get_config('vpc-subnet-names', default=()),
        vpc_subnet_name_tag_key=get_config('vpc-subnet-name-tag-key', default='Name'),
        vpc_security_group_names=get_config('vpc-security-group-names', default=()),
        mtls_truststore_uri=mtls_uri,
        # mTLS only protects the custom domain, so it forces off every other way to reach the
        # function.
        disable_execute_api_endpoint=bool(mtls_uri)
        or get_config('disable-execute-api-endpoint', default=False),
        disable_function_url=bool(mtls_uri) or get_config('disable-function-url', default=False),
        worker=WorkerConfig(
            command=worker['command'],
            cluster_name=worker['cluster-name'],
            execution_role_arn=worker['execution-role-arn'],
            task_role_arn=worker['task-role-arn'],
            log_group_name=worker['log-group-name'],
            security_group_names=worker['security-group-names'],
            service_name=worker.get('service-name', ''),
            cpu=worker.get('cpu', 512),
            memory=worker.get('memory', 1024),  # MiB
            desired_count=worker.get('desired-count', 1),
            assign_public_ip=worker.get('assign-public-ip', False),
            cpu_architecture=worker.get('cpu-architecture', 'X86_64'),
            _env=worker.get('env', {}),
        )
        if worker
        else None,
    )
