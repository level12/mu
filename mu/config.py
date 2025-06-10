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

    def resolve_env(self, env_val: str):
        if env_val is False:
            return ''

        if env_val is True:
            return 'true'

        if not isinstance(env_val, str) or not env_val.startswith('op://'):
            return str(env_val)

        result = utils.sub_run('op', 'read', '-n', env_val, capture_output=True)
        return result.stdout.decode('utf-8')

    @property
    def deployed_env(self):
        return self.deployed_env_gen(True)

    def deployed_env_gen(self, resolve: bool):
        return {
            name: self.resolve_env(val) if resolve else val
            for name, val in self._deployed_env.items()
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
        return config


def default_env():
    return environ.get('MU_DEFAULT_ENV') or utils.host_user()


def load(start_at: Path, env: str) -> Config:
    pp_fpath = find_upwards(start_at, 'pyproject.toml')
    if pp_fpath is None:
        raise Exception(f'No pyproject.toml found in {start_at} or parents')

    mu_fpath = pp_fpath.with_name('mu.toml')
    if mu_fpath.exists():
        config_fpath = mu_fpath
        key_prefix = ''
    else:
        config_fpath = pp_fpath
        key_prefix = 'tool.mu.'

    with pp_fpath.open('rb') as fo:
        pp_config = tomllib.load(fo)

    with config_fpath.open('rb') as fo:
        config = tomllib.load(fo)

    return Config(
        env=env,
        project_org=deep_get(config, key_prefix, 'project-org', required=True),
        project_name=deep_get(pp_config, '', 'project.name', required=True),
        domain_name=deep_get(config, key_prefix, 'domain-name'),
        _project_ident=deep_get(config, key_prefix, 'project-ident'),
        lambda_name=deep_get(config, key_prefix, 'lambda-name', 'func'),
        _image_name=deep_get(config, key_prefix, 'image-name'),
        action_key=deep_get(config, key_prefix, 'lambda-action-key', default='do-action'),
        _deployed_env=deep_get(config, key_prefix, 'deployed-env', default={}),
        event_rules=deep_get(config, key_prefix, 'event-rules', default={}),
        lambda_memory=deep_get(config, key_prefix, 'lambda-memory', default=2048),
        lambda_timeout=deep_get(config, key_prefix, 'lambda-timeout', default=900),
        policy_arns=deep_get(config, key_prefix, 'policy-arns', default=()),
        aws_config=deep_get(config, key_prefix, 'aws', default={}),
        compose_service=deep_get(config, key_prefix, 'compose-service', default='app'),
        vpc_subnet_names=deep_get(config, key_prefix, 'vpc-subnet-names', default=()),
        vpc_subnet_name_tag_key=deep_get(
            config,
            key_prefix,
            'vpc-subnet-name-tag-key',
            default='Name',
        ),
        vpc_security_group_names=deep_get(
            config,
            key_prefix,
            'vpc-security-group-names',
            default=(),
        ),
    )


def cli_load(env) -> Config:
    return load(Path.cwd(), env or default_env())
