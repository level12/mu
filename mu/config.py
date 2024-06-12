from dataclasses import asdict, dataclass
from os import environ
from pathlib import Path
import tomllib

from blazeutils.strings import simplify_string as slug

from .libs import utils


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
    project_org: str
    project_name: str
    project_ident: str
    lambda_name: str
    lambda_memory: int  # MB
    lambda_timeout: int  # secs
    image_name: str
    default_env: str
    action_key: str
    _environ: dict[str, str]
    event_rules: dict[str, dict[str, str]]
    policy_arns: list[str]
    # TODO: set region in config or trust its all setup in the active environ?
    aws_region: str | None = None

    def project_env(self, env_name: str):
        return f'{self.project_ident}-{env_name}'

    def lambda_env(self, env_name: str):
        return f'{self.project_ident}-lambda-{env_name}'

    def lambda_name_env(self, env_name: str):
        return slug(f'{self.lambda_name}-{env_name}')

    def repo_name(self, env_name: str):
        return self.project_env(env_name)

    def api_name(self, env_name: str):
        return self.project_env(env_name)

    def resolve_env(self, env_val: str):
        if not env_val.startswith('op://'):
            return env_val

        result = utils.sub_run('op', 'read', '-n', env_val, capture_output=True)
        return result.stdout.decode('utf-8')

    def environ(self):
        return {name: self.resolve_env(val) for name, val in self._environ.items()}

    def for_print(self):
        config = asdict(self)
        config['project_env'] = f'{self.project_env(self.default_env)}'
        config['lambda_env'] = f'{self.lambda_env(self.default_env)}'
        config['lambda_name_env'] = f'{self.lambda_name_env(self.default_env)}'
        config['repo_name'] = f'{self.repo_name(self.default_env)}'
        return config


def load(start_at: Path):
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

    project_name: str = deep_get(pp_config, '', 'project.name', required=True)
    project_org = deep_get(config, key_prefix, 'project-org', required=True)
    project_ident = deep_get(
        config,
        key_prefix,
        'project-ident',
        default=f'{project_org}-{project_name}',
    )
    lambda_name = deep_get(
        config,
        key_prefix,
        'lambda-name',
        default=f'{project_ident}-handler',
    )
    image_name = deep_get(config, key_prefix, 'image-name', default=project_name)
    action_key = deep_get(config, key_prefix, 'lambda-action-key', default='do-action')

    return Config(
        project_org=project_org,
        project_name=project_name,
        project_ident=slug(project_ident),
        lambda_name=slug(lambda_name),
        image_name=slug(image_name),
        default_env=environ.get('MU_DEFAULT_ENV') or utils.host_user(),
        action_key=action_key,
        _environ=deep_get(config, key_prefix, 'lambda-env', default={}),
        event_rules=deep_get(config, key_prefix, 'event-rules', default={}),
        lambda_memory=deep_get(config, key_prefix, 'lambda_memory', default=2048),
        lambda_timeout=deep_get(config, key_prefix, 'lambda_timeout', default=900),
        policy_arns=deep_get(config, key_prefix, 'policy_arns', default=[]),
    )
