import logging
from pathlib import Path
from pprint import pprint

import click
import colorlog

import mu.config
from mu.config import Config
from mu.libs import auth, sts, utils
from mu.libs.anon import Lambda


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
    sess = auth.b3_sess(config)
    acct_id: str = sts.account_id(sess)
    print('Account:', acct_id)
    print('Region:', sess.region_name)


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
@click.option('--delete-first', is_flag=True)
@click.pass_context
def deploy(ctx, envs: list[str], delete_first=False):
    """Deploy local image to ecr, update lambda"""
    config: Config = ctx.obj
    envs = envs or [config.default_env]

    lamb = Lambda(config)
    lamb.deploy(envs)


@cli.command()
@click.argument('target_env', required=False)
@click.pass_context
def build(ctx, target_env: str | None):
    """Build lambda container with docker compose"""
    config: Config = ctx.obj
    utils.sub_run(
        'docker',
        'compose',
        'build',
        '--pull',
        env={'MU_LAMBDA_NAME': config.lambda_env(target_env)},
    )


@cli.command()
@click.argument('target_env')
@click.argument('action', default='diagnostics')
@click.option('--host', default='localhost:8080')
@click.pass_context
def invoke(ctx, target_env: str, action: str, host: str):
    """Invoke lambda with diagnostics or given action"""

    config: Config = ctx.obj

    lamb = Lambda(config)
    if target_env == 'local':
        result = lamb.invoke_rei(host, action)
    else:
        target_env = config.default_env if target_env == 'default' else target_env
        result = lamb.invoke(target_env, action)

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
