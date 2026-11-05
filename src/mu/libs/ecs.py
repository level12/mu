import logging

from blazeutils.strings import simplify_string as slug
import boto3

from mu.config import Config, WorkerConfig

from . import ec2


log = logging.getLogger(__name__)


class Worker:
    """ECS Fargate service that runs the lambda's image with a different command."""

    def __init__(self, config: Config, b3_sess: boto3.Session):
        self.config = config
        self.wc: WorkerConfig = config.worker
        self.b3_sess = b3_sess
        self.ecs = b3_sess.client('ecs')
        self.service_name: str = self.wc.service_name or slug(
            f'{config.lambda_ident}-worker',
        )
        cluster_name = self.wc.cluster_name.rsplit('/', 1)[-1]
        self.task_family = f'{cluster_name}-{self.service_name}'

    def env_vars(self) -> list[dict]:
        env = self.config.deployed_env | self.wc.env
        return [{'name': name, 'value': val} for name, val in sorted(env.items())]

    def task_def_params(self, image_uri: str) -> dict:
        entry_point, *command = self.wc.command
        return {
            'family': self.task_family,
            'requiresCompatibilities': ['FARGATE'],
            'networkMode': 'awsvpc',
            'cpu': str(self.wc.cpu),
            'memory': str(self.wc.memory),
            'executionRoleArn': self.wc.execution_role_arn,
            'taskRoleArn': self.wc.task_role_arn,
            'runtimePlatform': {
                'cpuArchitecture': self.wc.cpu_architecture,
                'operatingSystemFamily': 'LINUX',
            },
            'containerDefinitions': [
                {
                    'name': 'worker',
                    'image': image_uri,
                    'essential': True,
                    # Replaces the lambda base image's entry point (the lambda runtime).
                    'entryPoint': [entry_point],
                    'command': command,
                    'environment': self.env_vars(),
                    'logConfiguration': {
                        'logDriver': 'awslogs',
                        'options': {
                            'awslogs-group': self.wc.log_group_name,
                            'awslogs-region': self.config.aws_region,
                            'awslogs-stream-prefix': 'worker',
                        },
                    },
                },
            ],
        }

    def network_config(self) -> dict:
        return {
            'awsvpcConfiguration': {
                'subnets': ec2.subnet_ids(
                    self.b3_sess,
                    self.config.vpc_subnet_names,
                    self.config.vpc_subnet_name_tag_key,
                ),
                'securityGroups': ec2.security_group_ids(
                    self.b3_sess,
                    self.wc.security_group_names,
                ),
                'assignPublicIp': 'ENABLED' if self.wc.assign_public_ip else 'DISABLED',
            },
        }

    def describe_service(self) -> dict | None:
        resp = self.ecs.describe_services(
            cluster=self.wc.cluster_name,
            services=[self.service_name],
        )
        services = resp.get('services')
        if not services or services[0]['status'] == 'INACTIVE':
            return None
        return services[0]

    def register_task_def(self, image_uri: str) -> str:
        resp = self.ecs.register_task_definition(**self.task_def_params(image_uri))
        arn = resp['taskDefinition']['taskDefinitionArn']
        log.info('ECS task definition registered: %s', arn)
        return arn

    def ensure_service(self, task_def_arn: str):
        shared = {
            'cluster': self.wc.cluster_name,
            'taskDefinition': task_def_arn,
            'desiredCount': self.wc.desired_count,
            'networkConfiguration': self.network_config(),
            'deploymentConfiguration': {
                'deploymentCircuitBreaker': {'enable': True, 'rollback': True},
            },
        }

        if self.describe_service():
            self.ecs.update_service(service=self.service_name, **shared)
            log.info('ECS service updated: %s', self.service_name)
            return

        self.ecs.create_service(serviceName=self.service_name, launchType='FARGATE', **shared)
        log.info('ECS service created: %s', self.service_name)

    def wait_deployed(self, task_def_arn: str):
        log.info('Waiting for ECS worker service to be stable...')
        waiter = self.ecs.get_waiter('services_stable')
        waiter.wait(cluster=self.wc.cluster_name, services=[self.service_name])

        # The circuit breaker rolls back a failed deployment and the service then goes stable on
        # the old task definition, so stable alone doesn't mean our deployment succeeded.
        service = self.describe_service()
        primary = next(d for d in service['deployments'] if d['status'] == 'PRIMARY')
        if primary['taskDefinition'] != task_def_arn:
            events = '\n'.join(f'  {e["message"]}' for e in service.get('events', [])[:5])
            raise RuntimeError(
                f'ECS worker deployment failed and was rolled back: {self.service_name}\n'
                f'Recent service events:\n{events}',
            )

    def deploy(self, image_uri: str):
        log.info('Deploying ECS worker: %s', self.service_name)
        task_def_arn = self.register_task_def(image_uri)
        self.ensure_service(task_def_arn)
        self.wait_deployed(task_def_arn)
        # Only after the deploy is confirmed: a rollback needs the previous revision.
        self.remove_task_defs(keep=task_def_arn)

    def task_def_arns(self, status: str) -> list[str]:
        """Revisions in this worker's family.  familyPrefix is a prefix match, so filter to the
        exact family to avoid touching e.g. "<task-family>-other"."""
        paginator = self.ecs.get_paginator('list_task_definitions')
        return [
            arn
            for page in paginator.paginate(familyPrefix=self.task_family, status=status)
            for arn in page['taskDefinitionArns']
            if arn.rsplit('/', 1)[-1].rsplit(':', 1)[0] == self.task_family
        ]

    def remove_task_defs(self, *, keep: str | None = None):
        """
        Deregister and delete task definition revisions, other than `keep`.

        Revisions hold the resolved deployed env (including secrets) so they shouldn't be left
        around.  Deregistering alone leaves them readable as INACTIVE, so they also get deleted.
        """
        for arn in self.task_def_arns('ACTIVE'):
            if arn != keep:
                self.ecs.deregister_task_definition(taskDefinition=arn)

        inactive = self.task_def_arns('INACTIVE')
        failed = []
        # API accepts at most 10 per call.
        for i in range(0, len(inactive), 10):
            resp = self.ecs.delete_task_definitions(taskDefinitions=inactive[i : i + 10])
            failed.extend(resp.get('failures', ()))

        for failure in failed:
            log.warning(
                'ECS task definition delete failed: %s - %s',
                failure.get('arn'),
                failure.get('reason'),
            )
        if removed := len(inactive) - len(failed):
            log.info('ECS task definitions removed: %s', removed)

    def delete(self):
        if self.describe_service():
            self.ecs.delete_service(
                cluster=self.wc.cluster_name,
                service=self.service_name,
                force=True,
            )
            log.info('Waiting for ECS service to be deleted...')
            self.ecs.get_waiter('services_inactive').wait(
                cluster=self.wc.cluster_name,
                services=[self.service_name],
            )
            log.info('ECS service deleted: %s', self.service_name)
        else:
            log.info('ECS service not found: %s', self.service_name)

        # Even without a service, there could be revisions from an earlier partial deploy.
        self.remove_task_defs()

    def status(self) -> dict | None:
        if not (service := self.describe_service()):
            return None
        primary = next(d for d in service['deployments'] if d['status'] == 'PRIMARY')
        return {
            'status': service['status'],
            'running': service['runningCount'],
            'desired': service['desiredCount'],
            'pending': service['pendingCount'],
            'task_def': primary['taskDefinition'].rsplit('/', 1)[-1],
            'rollout': primary.get('rolloutState'),
        }
