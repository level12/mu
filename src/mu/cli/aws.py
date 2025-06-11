import logging
from pprint import pprint

import click

from ..config import Config, cli_load
from ..libs import api_gateway, auth, ec2, ecr, ecs, gateway
from .core import cli


log = logging.getLogger()


@cli.group()
def aws():
    """(group)"""


@aws.command()
@click.argument('target_env', required=False)
@click.option('--name-prefix', help='Filter on name tag')
@click.option('--name-key', help='Key of tag to use for name', default='Name')
@click.option('--verbose', '-v', is_flag=True)
def subnets(target_env, name_prefix, name_key, verbose):
    """List ec2 subnets"""
    config: Config = cli_load(target_env)
    b3_sess = auth.b3_sess(config.aws_region)

    for name, subnet in ec2.describe_subnets(b3_sess, name_prefix, name_key).items():
        print(f'{subnet["AvailabilityZone"]} - {subnet["SubnetId"]} - {name}')
        if verbose:
            pprint(subnet)


@aws.command()
@click.argument('only_names', nargs=-1)
@click.option('--env', 'target_env')
@click.option('--verbose', '-v', is_flag=True)
def security_groups(target_env, only_names, verbose):
    """List ec2 subnets"""
    config: Config = cli_load(target_env)
    b3_sess = auth.b3_sess(config.aws_region)

    for name, group in ec2.describe_security_groups(b3_sess, only_names).items():
        print(f'{group["GroupId"]} - {name} - {group["Description"]}')
        if verbose:
            pprint(group)


@aws.command()
@click.option('--env', 'target_env')
@click.option('--verbose', '-v', is_flag=True)
def ecs_clusters(target_env, verbose):
    """List App Runner instance configurations"""
    config: Config = cli_load(target_env)
    b3_sess = auth.b3_sess(config.aws_region)

    ecs_ = ecs.ECS(b3_sess)
    for name in ecs_.clusters():
        print(name)


@cli.command()
@click.argument('target_env', required=False)
@click.pass_context
def ecr_push(ctx: click.Context, target_env: str | None):
    """Push built image to ecr"""
    config: Config = cli_load(target_env)
    repo_name = config.resource_ident
    print(config.aws_region)
    repos = ecr.Repos(auth.b3_sess(config.aws_region))
    repo = repos.get(repo_name)
    print('Pushing to:', repo.uri)
    repo.push(config.image_name)


@cli.command()
@click.argument('target_env', required=False)
@click.option('--verbose', is_flag=True)
def ecr_repos(verbose: bool, target_env: str | None):
    """List ECR repos in active account"""
    config: Config = cli_load(target_env)
    b3_sess = auth.b3_sess(config.aws_region)

    repos = ecr.Repos(b3_sess)
    for name, repo in repos.list().items():
        if verbose:
            pprint(repo.rec)
        else:
            print(name)


@cli.command()
@click.argument('repo_name', required=False)
@click.option('--verbose', is_flag=True)
@click.option('--env', 'target_env')
def ecr_images(verbose: bool, target_env: str | None, repo_name: str | None):
    """List all images in a repo"""
    config: Config = cli_load(target_env)
    b3_sess = auth.b3_sess(config.aws_region)

    repos = ecr.Repos(b3_sess)

    repo_name = repo_name or config.resource_ident
    repo = repos.get(repo_name)
    if not repo:
        print(f"Repo doesn't exist: {repo_name}")
        return

    if not verbose:
        print('Pushed At\tTags')
    for image in repo.images():
        if verbose:
            pprint(image)
        else:
            print(image['imagePushedAt'].isoformat(), ' '.join(image['imageTags']))


@cli.command()
@click.argument('repo_name', required=False)
@click.option('--env', 'target_env')
@click.option('--prefix', default='')
@click.option('--limit', default=25)
@click.pass_context
def ecr_tags(
    ctx: click.Context,
    prefix: str,
    limit: int,
    target_env: str | None,
    repo_name: str | None,
):
    """List ecr tags"""
    config: Config = cli_load(target_env)
    b3_sess = auth.b3_sess(config.aws_region)

    repos = ecr.Repos(b3_sess)

    repo_name = repo_name or config.resource_ident

    print('Repository:\n ', repo_name)
    print('Tags:')
    for tag in repos.ecr_tags(repo_name, prefix=prefix, limit=limit):
        print(f'  {tag}')


@aws.command()
@click.option('--verbose', is_flag=True)
def api_gateways(verbose: bool):
    """List api gateways in active account"""
    config: Config = cli_load(None)
    b3_sess = auth.b3_sess(config.aws_region)

    apis = api_gateway.APIs(b3_sess)
    for ag in apis.list():
        if verbose:
            print(ag.name, ag, sep='\n')
        else:
            print(ag.name, ag.created_date, ag.api_id)


@aws.command()
def gateway_cleanup():
    b3_sess = auth.b3_sess()
    gateway.acct_cleanup(b3_sess)
