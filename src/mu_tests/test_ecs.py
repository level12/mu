import os
from pathlib import Path
from unittest import mock

import pytest

from mu.config import load
from mu.libs.ecs import Worker


@pytest.fixture
def worker_config(moto_sess):
    config = load(Path(__file__).parent / 'pkg-worker', 'qa')
    config.apply_sess(moto_sess, testing=True)
    return config


@pytest.fixture
def network(moto_sess, worker_config):
    """Create the subnets and security groups named in the config, return the ids AWS assigned."""
    ec2 = moto_sess.client('ec2')
    vpc_id = ec2.create_vpc(CidrBlock='10.0.0.0/16')['Vpc']['VpcId']
    subnet_ids = [
        ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock=f'10.0.{i}.0/24',
            TagSpecifications=[
                {'ResourceType': 'subnet', 'Tags': [{'Key': 'Name', 'Value': name}]},
            ],
        )['Subnet']['SubnetId']
        for i, name in enumerate(worker_config.vpc_subnet_names)
    ]
    group_ids = [
        ec2.create_security_group(VpcId=vpc_id, GroupName=name, Description=name)['GroupId']
        for name in worker_config.worker.security_group_names
    ]
    return {'subnet_ids': subnet_ids, 'group_ids': group_ids}


@pytest.fixture
def worker(moto_sess, worker_config, network):
    worker = Worker(worker_config, moto_sess)
    worker.ecs.create_cluster(clusterName=worker_config.worker.cluster_name)
    return worker


@mock.patch.dict(os.environ, MOTO_ECS_SERVICE_RUNNING='1')
class TestWorker:
    def test_deploy(self, worker, network):
        assert worker.status() is None
        worker.wc._env['GEORDI'] = 'Chief Engineer'
        worker.deploy('example:one')

        service = worker.describe_service()
        task = worker.ecs.describe_task_definition(
            taskDefinition=service['taskDefinition'],
        )['taskDefinition']
        container = task['containerDefinitions'][0]
        assert container['image'] == 'example:one'
        assert container['entryPoint'] == ['flask']
        assert container['command'] == ['worker', '--concurrency', '5']
        env = {item['name']: item['value'] for item in container['environment']}
        assert env['GEORDI'] == 'Chief Engineer'
        assert env['MU_ENV'] == 'qa'
        assert env['WORKER_POOL_SIZE'] == '5'
        vpc_config = service['networkConfiguration']['awsvpcConfiguration']
        assert vpc_config['subnets'] == network['subnet_ids']
        assert vpc_config['securityGroups'] == network['group_ids']
        assert vpc_config['assignPublicIp'] == 'DISABLED'
        assert worker.status() == {
            'status': 'ACTIVE',
            'running': 1,
            'desired': 1,
            'pending': 0,
            'task_def': f'{worker.task_family}:1',
            'rollout': 'COMPLETED',
        }

    def test_update_and_cleanup(self, worker):
        worker.deploy('example:one')
        other = worker.task_def_params('example:other')
        other['family'] += '-other'
        other_arn = worker.ecs.register_task_definition(**other)['taskDefinition'][
            'taskDefinitionArn'
        ]

        arn = worker.register_task_def('example:two')
        worker.wc.desired_count = 2
        # Moto updates the service but leaves its deployment record on the old revision.
        worker.ensure_service(arn)
        service = worker.describe_service()
        assert service['taskDefinition'] == arn
        assert service['desiredCount'] == 2

        worker.remove_task_defs(keep=arn)
        assert worker.task_def_arns('ACTIVE') == [arn]
        assert worker.task_def_arns('INACTIVE') == []
        assert (
            worker.ecs.describe_task_definition(taskDefinition=other_arn)['taskDefinition'][
                'status'
            ]
            == 'ACTIVE'
        )

    def test_rollback(self, worker):
        worker.deploy('example:one')
        arn = worker.register_task_def('example:two')
        # A rollback leaves the service stable on the previous task definition.
        with pytest.raises(RuntimeError, match='deployment failed and was rolled back'):
            worker.wait_deployed(arn)

    def test_delete(self, worker):
        worker.deploy('example:one')
        worker.delete()
        assert worker.status() is None
        assert worker.task_def_arns('ACTIVE') == []
        assert worker.task_def_arns('INACTIVE') == []
        worker.delete()
