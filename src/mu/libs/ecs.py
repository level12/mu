from dataclasses import dataclass
import functools
import logging

import boto3

from .utils import B3DataClass


log = logging.getLogger(__name__)


@dataclass
class Cluster(B3DataClass):
    name: str
    exists: bool | None = None

    @functools.cached_property
    def ecs(self):
        return self._b3_sess.client('ecs')

    def ensure(self) -> 'Cluster':
        if self.exists:
            log.info('ECS cluster existed: %s', self.name)
            return
        self.ecs.create_cluster(clusterName=self.name)
        self.exists = True
        log.info('ECS cluster created: %s', self.name)

    def delete(self):
        self.ecs.delete_cluster(cluster=self.name)
        self.exists = False
        log.info('ECS cluster deleted: %s', self.name)


class ECS:
    def __init__(self, b3_sess: boto3.Session):
        self.b3_sess = b3_sess
        self.ecs = b3_sess.client('ecs')

    def clusters(self) -> dict[str, Cluster]:
        clusters = {}
        resp = self.ecs.list_clusters()
        arn: str
        for arn in resp.get('clusterArns', ()):
            _, name = arn.rsplit('/', 1)
            clusters[name] = Cluster(self.b3_sess, name=name, exists=True)
        return clusters

    def delete(self, name_prefix: str):
        for name, cluster in self.clusters().items():
            if name.startswith(name_prefix):
                cluster.delete()

    def cluster(self, name):
        return self.clusters().get(name) or Cluster(self.b3_sess, name, exists=False)

    def provision(self, resource_ident):
        self.cluster(resource_ident).ensure()

    def deploy(self, resource_ident, role_arn):
        self.ecs.register_task_definition(
            family=resource_ident,
            executionRoleArn=role_arn,
            networkMode='awsvpc',
            containerDefinitions=[
                {
                    'name': 'my-container',
                    'image': 'arn:aws:ecr:region:account-id:repository/repository-name:tag',
                    'portMappings': [
                        {
                            'containerPort': 80,
                            'protocol': 'tcp',
                        },
                    ],
                    'essential': True,
                    'memory': 512,
                    'cpu': 256,
                },
            ],
            requiresCompatibilities=[
                'FARGATE',
            ],
            cpu='256',
            memory='512',
        )
