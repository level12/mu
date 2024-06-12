from pathlib import Path
from pprint import pprint

import click

import mu.config
from mu.config import Config
from mu.libs import auth, ecr, utils
from mu.libs.lamb import Lambda

from ..cli import cli


@cli.command()
@click.argument('target_env', required=False)
@click.pass_context
def ecr_push(ctx: click.Context, target_env: str | None):
    """Push built image to ecr"""
    config: Config = ctx.obj
    target_env = target_env or config.default_env
    repo_name = config.repo_name(target_env)

    repos = ecr.Repos(auth.b3_sess(config.aws_region))
    repo = repos.get(repo_name)
    print('Pushing to:', repo.uri)
    repo.push(config.image_name)


@cli.command()
@click.pass_context
@click.option('--verbose', is_flag=True)
def ecr_repos(ctx: click.Context, verbose: bool):
    """List ECR repos in active account"""
    config: Config = ctx.obj

    repos = ecr.Repos(auth.b3_sess(config.aws_region))
    for name, repo in repos.list().items():
        if verbose:
            pprint(repo.rec)
        else:
            print(name)


@cli.command()
@click.argument('target', required=False)
@click.option('--verbose', is_flag=True)
@click.option('--repo', is_flag=True)
@click.pass_context
def ecr_images(ctx: click.Context, verbose: bool, target: str, repo: bool):
    """List all images in a repo, optionally with tags"""
    config: Config = ctx.obj
    target = target or config.default_env

    repos = ecr.Repos(auth.b3_sess(config.aws_region))

    repo_name = target if repo else config.repo_name(target)
    repo = repos.get(repo_name)

    if not repo:
        print(f"Repo doesn't exist: {repo_name}")
        return

    for image in repo.images():
        if verbose:
            print(repo.rec)
        else:
            print(image)


@cli.command()
@click.option('--prefix', default='')
@click.option('--limit', default=25)
@click.pass_context
def ecr_tags(ctx: click.Context, prefix: str, limit: int):
    """List ecr tags"""
    config: Config = ctx.obj
    lamb = Lambda(config)

    print('Repository:\n ', lamb.ecr_ident())
    print('Tags:')
    for tag in lamb.ecr_tags(prefix=prefix, limit=limit):
        print(f'  {tag}')
