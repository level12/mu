import base64
import json
import logging
import time

import arrow
from blazeutils.strings import case_us2mc
import boto3
import docker
from methodtools import lru_cache

from . import utils


log = logging.getLogger(__name__)


class RetryingSetRepoPolicy(utils.RetryingAction):
    """
    If a role was recently created, AWS may not have the role ready when we try to set the policy.
    This class will catch that error and retry assuming AWS will get us there eventually.
    """

    # Too bad the error isn't more specific so we could be sure its the role that's problematic
    # but its a generic error message.
    exc_contains = 'Invalid repository policy provided'
    waiting_for = 'role to be ready'

    @classmethod
    def act(cls, ecr, repo_name: str, policy_text: str):
        return ecr.set_repository_policy(
            repositoryName=repo_name,
            policyText=policy_text,
        )

    @classmethod
    def run(cls, ecr, *args):
        cls.exc_type = ecr.exceptions.InvalidParameterException
        super().run(ecr, *args)


class LocalImage:
    def __init__(self, image_name):
        self.image_name = image_name
        self.docker = docker.from_env()

    def get(self):
        return self.docker.images.get(self.image_name)

    def created_utc(self):
        image = self.get()
        return arrow.get(image.attrs['Created']).to('UTC').format('YYYY-MM-DDTHH.mm.ss')

    def tag(self, repo: str, tag: str):
        return self.get().tag(repo, tag=tag)


class Repo:
    def __init__(self, ecr, rec: dict):
        self.ecr = ecr
        self.rec = rec
        self.docker = docker.from_env()

    def __getattr__(self, item: str):
        aws_name = case_us2mc(item)

        if aws_name in self.rec:
            return self.rec[aws_name]

        raise AttributeError(item)

    @property
    def uri(self):
        return self.rec['repositoryUri']

    @property
    def name(self):
        return self.rec['repositoryName']

    def delete(self, *, force: bool):
        try:
            self.ecr.delete_repository(repositoryName=self.repository_name, force=force)
            log.info('Repository deleted: %s', self.name)
        except self.ecr.exceptions.RepositoryNotEmptyException:
            log.warning('Repository not empty: %s.  Use force option to remove.', self.name)

    def get_policy(self):
        resp = self.ecr.get_repository_policy(repositoryName=self.repository_name)
        return json.loads(resp['policyText'])

    @lru_cache()
    def images(self):
        resp = self.ecr.describe_images(
            repositoryName=self.repository_name,
        )
        return resp['imageDetails']

    def tags(self, *, prefix: str = '', limit=20):
        tags = sorted(
            [
                tag
                for image in self.images()
                if 'imageTags' in image
                for tag in image['imageTags']
                if not prefix or tag.startswith(prefix)
            ],
            reverse=True,
        )
        return tags[:limit]

    def latest_tag(self, prefix: str):
        tags = self.tags(prefix=prefix, limit=1)
        if tags:
            return tags[0]

    def tag_local(self, image_name, suffix: str | None = None):
        image = LocalImage(image_name)
        tag = suffix or image.created_utc()
        tag = f'{image_name}-{tag}'
        image.tag(self.uri, tag)
        return tag

    def tag_remote(self, tag_existing, tag_new):
        # Get the manifest of the existing image
        response = self.ecr.batch_get_image(
            repositoryName=self.name,
            imageIds=[{'imageTag': tag_existing}],
            acceptedMediaTypes=['application/vnd.docker.distribution.manifest.v2+json'],
        )

        manifest = response['images'][0]['imageManifest']

        # Put the image with the new tag
        response = self.ecr.put_image(
            repositoryName=self.name,
            imageTag=tag_new,
            imageManifest=manifest,
        )

    def push(self, image_name: str, *, tag_suffix: str | None = None):
        tag = self.tag_local(image_name, tag_suffix)
        repo_tag = self.latest_tag(image_name)

        if repo_tag == tag:
            # log.info('Repo name: %s', self.name)
            # log.info('Tag: %s', repo_tag)
            log.warning(
                'Local and ECR tags match, not pushing image.'
                "  If that's unexpected, you may need to build first.",
            )
            return tag

        # Get the ECR login token
        token = self.ecr.get_authorization_token()
        username, password = (
            base64.b64decode(token['authorizationData'][0]['authorizationToken'])
            .decode()
            .split(':')
        )
        registry = token['authorizationData'][0]['proxyEndpoint']

        # Authenticate to ECR.  TODO: catch errors
        self.docker.login(username=username, password=password, registry=registry)

        log.info(f'Tagged, pushing {image_name}:{tag}...')
        results = self.docker.images.push(self.uri, tag=tag)

        # TODO: better error handling
        assert 'error' not in str(results), results

        log.debug(results)
        log.info('Push complete')

        self.images.cache_clear()

        return tag


class Repos:
    policy_actions = (
        'ecr:GetDownloadUrlForLayer',
        'ecr:BatchGetImage',
        'ecr:BatchCheckLayerAvailability',
    )

    def __init__(self, b3_sess: boto3.Session):
        self.aws_region: str = b3_sess.region_name
        self.b3_sess = b3_sess
        self.ecr = b3_sess.client('ecr')

    # @functools.cached_property
    # def aws_acct_id(self):
    #     return sts.account_id(self.b3_sess)

    def clear(self):
        self.list.cache_clear()

    def get(self, name, wait=False) -> Repo:
        if not wait:
            return self.list().get(name)

        for wait_for in (0.1, 0.25, 0.5, 0.75, 1, 1.25, 1.5):
            repo = self.list().get(name)
            if repo:
                return repo
            time.sleep(wait_for)
            self.clear()

    @lru_cache()
    def list(self) -> dict[str, Repo]:
        repos = self.ecr.describe_repositories()['repositories']
        return {repo['repositoryName']: Repo(self.ecr, repo) for repo in repos}

    def delete(self, *names, force):
        repos = self.list()
        for name in names:
            if name not in repos:
                continue

            repos[name].delete(force=force)
            del repos[name]

        self.clear()

    def ensure(self, repo_name: str, role_arn: str) -> Repo:
        try:
            self.ecr.create_repository(
                repositoryName=repo_name,
                imageTagMutability='IMMUTABLE',
                encryptionConfiguration={
                    'encryptionType': 'AES256',
                },
            )
            log.info(f'Repository created: {repo_name}')
            self.clear()
        except self.ecr.exceptions.RepositoryAlreadyExistsException:
            log.info(f'Repository existed: {repo_name}')

        # # Give the role the lambda will use permissions on this repo
        # principal = {'AWS': role_arn}
        # policy = iam.policy_doc(*self.policy_actions, principal=principal)

        # RetryingSetRepoPolicy.run(self.ecr, repo_name, json.dumps(policy))

        return self.get(repo_name, wait=True)

    def ecr_tags(self, repo_name, *, prefix: str = '', limit=20):
        response = self.ecr.describe_images(
            repositoryName=repo_name,
        )

        tags = sorted(
            [
                tag
                for image in response['imageDetails']
                if 'imageTags' in image
                for tag in image['imageTags']
                if not prefix or tag.startswith(prefix)
            ],
            reverse=True,
        )
        return tags[:limit]

    def ecr_repo_uri(self, tag=''):
        suffix = f':{tag}' if tag else ''
        return f'{self.account_id()}.dkr.ecr.{self.aws_region}.amazonaws.com/{self.ident}{suffix}'

    def ecr_latest_tag(self, prefix):
        tags = self.ecr_tags(prefix=prefix, limit=1)
        if tags:
            return tags[0]

    def local_image(self):
        return self.docker.images.get(self.local_image_name)

    def local_image_created(self):
        image = self.local_image()
        return arrow.get(image.attrs['Created']).to('UTC').format('YYYY-MM-DDTHH.mm.ss')

    def local_image_tag(self, target_env: str):
        created_utc = self.local_image_created()
        return f'{target_env}-{created_utc}'

    def ecr_push(self, target_env):
        ecr_repo_uri = self.ecr_repo_uri()

        image = self.local_image()

        tag = self.local_image_tag(target_env)
        image.tag(ecr_repo_uri, tag=tag)

        # Get the ECR login token
        token = self.ecr.get_authorization_token()
        username, password = (
            base64.b64decode(token['authorizationData'][0]['authorizationToken'])
            .decode()
            .split(':')
        )
        registry = token['authorizationData'][0]['proxyEndpoint']

        # Authenticate to ECR.  TODO: catch errors
        self.docker.login(username=username, password=password, registry=registry)

        log.info(f'Tagged, pushing {self.local_image_name}:{tag}...')
        results = self.docker.images.push(ecr_repo_uri, tag=tag, stream=True, decode=True)

        for line in results:
            print(line)

        log.info('Push complete')
