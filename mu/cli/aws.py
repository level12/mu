import logging
from pprint import pprint

import click

from ..cli import cli
from ..config import Config, cli_load
from ..libs import auth, ec2


log = logging.getLogger()


@cli.group()
def aws():
    pass


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
        print(f"{subnet['AvailabilityZone']} - {subnet['SubnetId']} - {name}")
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
        print(f"{group['GroupId']} - {name} - {group['Description']}")
        if verbose:
            pprint(group)
