import logging
from pathlib import Path
from pprint import pprint

import click
import colorlog

import mu.config
from mu.config import Config
from mu.libs import api_gateway, auth, sts, utils
from mu.libs.lamb import Lambda


log = logging.getLogger()


@click.group()
@click.option('--quiet', is_flag=True)
@click.option('--verbose', is_flag=True)
@click.pass_context
def cli(ctx, quiet, verbose):
    ctx.obj = mu.config.load(Path.cwd())

    logging.addLevelName(logging.DEBUG, 'debug')
    logging.addLevelName(logging.INFO, 'info')
    logging.addLevelName(logging.WARNING, 'warning')
    logging.addLevelName(logging.ERROR, 'error')
    logging.addLevelName(logging.CRITICAL, 'critical')

    handler = colorlog.StreamHandler()
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(levelname)8s%(reset)s  %(message)s',
        log_colors={
            'debug': 'white',
            'info': 'cyan',
            'warning': 'yellow',
            'error': 'red',
            'critical': 'red',
        },
    )
    handler.setFormatter(formatter)
    level = logging.WARNING if quiet else (logging.DEBUG if verbose else logging.INFO)
    logging.getLogger('mu').setLevel(level)
    logging.basicConfig(handlers=(handler,))


@cli.command()
@click.pass_context
def auth_check(ctx):
    """Check AWS auth by displaying account info"""
    config: Config = ctx.obj
    b3_sess = auth.b3_sess(config.aws_region)
    acct_id: str = sts.account_id(b3_sess)
    print('Account:', acct_id)
    print('Region:', b3_sess.region_name)

    orgc = b3_sess.client('organizations')
    try:
        org_info = orgc.describe_organization()
        print('Organization owner:', org_info['Organization']['MasterAccountEmail'])
    except orgc.exceptions.AWSOrganizationsNotInUseException:
        print('Organization: none')


@cli.command()
@click.pass_context
def config(ctx):
    """Display mu config for active project"""
    config: Config = ctx.obj

    utils.print_dict(config.for_print())


@cli.command()
@click.argument('envs', nargs=-1)
@click.pass_context
def provision(ctx, envs: list[str]):
    """Provision lambda function in environment given (or default)"""
    config: Config = ctx.obj
    envs = envs or [config.default_env]

    lamb = Lambda(config)
    lamb.provision(*envs)


@cli.command()
@click.argument('envs', nargs=-1)
@click.option('--build', is_flag=True)
@click.pass_context
def deploy(ctx, envs: list[str], build: bool):
    """Deploy local image to ecr, update lambda"""
    config: Config = ctx.obj
    envs = envs or [config.default_env]

    if build:
        utils.compose_build()

    lamb = Lambda(config)
    lamb.deploy(envs)


@cli.command()
@click.argument('target_env')
@click.option('--force-repo', is_flag=True)
@click.pass_context
def delete(ctx, target_env: str, force_repo: bool):
    """Delete lambda and optionally related infra"""
    config: Config = ctx.obj
    lamb = Lambda(config)
    lamb.delete(target_env, force_repo=force_repo)


@cli.command()
def build():
    """Build lambda container with docker compose"""
    utils.compose_build()


@cli.command()
@click.argument('action', default='diagnostics')
@click.argument('action_args', nargs=-1)
@click.option('--env', 'target_env')
@click.option('--host', default='localhost:8080')
@click.option('--local', is_flag=True)
@click.pass_context
def invoke(ctx, target_env: str, action: str, host: str, action_args: list, local: bool):
    """Invoke lambda with diagnostics or given action"""

    config: Config = ctx.obj

    lamb = Lambda(config)
    if local:
        result = lamb.invoke_rei(host, action, action_args)
    else:
        target_env = config.default_env if target_env is None else target_env
        result = lamb.invoke(target_env, action, action_args)

    pprint(result)


@cli.command()
@click.argument('target_env', required=False)
@click.option('--limit', default=30)
@click.option('--reverse', is_flag=True)
@click.pass_context
def lambda_logs(ctx, target_env: str, limit: int, reverse: bool):
    config: Config = ctx.obj
    target_env = target_env or config.default_env

    lamb = Lambda(config)
    lamb.logs(target_env, limit, reverse)


@cli.command()
@click.pass_context
@click.option('--verbose', is_flag=True)
def apis(ctx: click.Context, verbose: bool):
    """List api gateways in active account"""
    config: Config = ctx.obj

    apis = api_gateway.APIs(auth.b3_sess(config.aws_region))
    for ag in apis.list():
        if verbose:
            print(ag.name, ag, sep='\n')
        else:
            print(ag.name, ag.created_date, ag.api_id)
