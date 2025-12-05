from pathlib import Path
from pprint import pprint

import click

import mu.config
from mu.config import Config, default_env, load
from mu.libs import auth, logs, sqs, sts, utils
from mu.libs.lamb import Lambda
from mu.libs.status import Status


log = logs.logger()


@click.group()
@click.option(
    '--config',
    'config_path',
    type=click.Path(path_type=Path),
    help='Path to mu config file',
    envvar='MU_CONFIG_PATH',
)
@logs.click_options
@click.pass_context
def cli(ctx: click.Context, log_level: str, config_path: Path | None):
    logs.init_logging(log_level)
    ctx.ensure_object(dict)

    def load_config(env: str | None = None) -> Config:
        return load(Path.cwd(), env or default_env(), config_path)

    ctx.obj['load_config'] = load_config


@cli.command()
@click.argument('target_env', required=False)
@click.pass_context
def auth_check(ctx: click.Context, target_env):
    """Check AWS auth by displaying account info"""
    config: Config = ctx.obj['load_config'](target_env)
    b3_sess = auth.b3_sess(config.aws_region)
    ident: str = sts.caller_identity(b3_sess)
    print('Account:', ident['Account'])
    print(f'User ID: {ident["UserId"]}')
    print(f'User Arn: {ident["Arn"]}')

    print('Region:', b3_sess.region_name)

    orgc = b3_sess.client('organizations')
    try:
        org_info = orgc.describe_organization()
        print('Organization owner:', org_info['Organization']['MasterAccountEmail'])
    except orgc.exceptions.AWSOrganizationsNotInUseException:
        print('Organization: none')


@cli.command()
@click.argument('target_env', required=False)
@click.option('--resolve-env', is_flag=True, help='Show env after resolution (e.g. secrets)')
@click.pass_context
def config(ctx: click.Context, target_env: str, resolve_env: bool):
    """Display mu config for active project"""
    config: Config = ctx.obj['load_config'](target_env)

    sess = auth.b3_sess(config.aws_region)
    config.apply_sess(sess)

    utils.print_dict(config.for_print(resolve_env))


@cli.command()
@click.argument('envs', nargs=-1)
@click.pass_context
def provision(ctx: click.Context, envs: list[str]):
    """Provision lambda function in environment given (or default)"""
    envs = envs or [None]

    for env in envs:
        lamb = Lambda(ctx.obj['load_config'](env))
        lamb.provision()


@cli.command()
@click.argument('envs', nargs=-1)
@click.option('--build', is_flag=True)
@click.pass_context
def deploy(ctx: click.Context, envs: list[str], build: bool):
    """Deploy local image to ecr, update lambda"""
    envs = envs or [mu.config.default_env()]

    configs = [ctx.obj['load_config'](env) for env in envs]

    if build:
        service_names = [config.compose_service for config in configs]
        utils.compose_build(*service_names)

    for config in configs:
        lamb = Lambda(config)
        lamb.deploy(config.env)


@cli.command()
@click.argument('target_env')
@click.option('--force-repo', is_flag=True)
@click.pass_context
def delete(ctx: click.Context, target_env: str, force_repo: bool):
    """Delete lambda and optionally related infra"""
    lamb = Lambda(ctx.obj['load_config'](target_env))
    lamb.delete(target_env, force_repo=force_repo)


@cli.command()
@click.argument('target_env', required=False)
@click.pass_context
def build(ctx: click.Context, target_env: str):
    """Build lambda container with docker compose"""
    conf = ctx.obj['load_config'](target_env)
    utils.compose_build(conf.compose_service)


@cli.command()
@click.argument('action', default='diagnostics')
@click.argument('action_args', nargs=-1)
@click.option('--env', 'target_env')
@click.option('--host', default='localhost:8080')
@click.option('--local', is_flag=True)
@click.pass_context
def invoke(
    ctx: click.Context,
    target_env: str,
    action: str,
    host: str,
    action_args: list,
    local: bool,
):
    """Invoke lambda with diagnostics or given action"""
    lamb = Lambda(ctx.obj['load_config'](target_env))
    if local:
        result = lamb.invoke_rei(host, action, action_args)
    else:
        result = lamb.invoke(action, action_args)

    print(result)


@cli.command('logs')
@click.argument('target_env', required=False)
@click.option('--first', default=0)
@click.option('--last', default=0)
@click.option('--streams', is_flag=True)
@click.pass_context
def _logs(
    ctx: click.Context,
    target_env: str,
    first: int,
    last: int,
    streams: bool,
):
    if first and last:
        ctx.fail('Give --first or --last, not both')

    if not first and not last:
        last = 10 if streams else 25

    lamb = Lambda(ctx.obj['load_config'](target_env))
    lamb.logs(first, last, streams)


@cli.command()
@click.pass_context
@click.argument('name_prefix', required=False, default='')
@click.option('--verbose', is_flag=True)
@click.option('--delete', is_flag=True)
def sqs_list(ctx: click.Context, verbose: bool, delete: bool, name_prefix=str):
    """List sqs queues in active account"""
    sqs_ = sqs.SQS(auth.b3_sess())
    for q in sqs_.list(name_prefix).values():
        if delete:
            q.delete()
            continue

        if verbose:
            print(q.name, q.attrs, sep='\n')
        else:
            print(q.name)


@cli.command()
@click.argument('action', type=click.Choice(('show', 'provision', 'delete')))
@click.argument('target_env', required=False)
@click.pass_context
def domain_name(ctx: click.Context, target_env: str, action: str):
    """Manage AWS config needed for domain name support"""
    from ..libs import gateway

    config: Config = ctx.obj['load_config'](target_env)
    assert config.domain_name

    gw = gateway.Gateway(config)
    if action == 'show':
        pprint(gw.cert_describe())
        return

    if action == 'delete':
        gw.delete()
        return

    if action == 'provision':
        gw.provision()
        return

    raise RuntimeError(f'Unhandled action: {action}')


@cli.command()
@click.argument('target_env', required=False)
@click.pass_context
def status(ctx: click.Context, target_env: str | None):
    """Check status of all infrastructure components for the app"""
    config = ctx.obj['load_config'](target_env)

    print(Status.fetch(config))
