from pathlib import Path

from mu import config
from mu.libs.testing import mock_patch_obj


tests_dpath = Path(__file__).parent


def load(*start_at) -> config.Config:
    return config.load(tests_dpath.joinpath(*start_at), 'qa')


class TestConfig:
    @mock_patch_obj(config.utils, 'host_user')
    def test_minimal_config_defaults(self, m_host_user):
        m_host_user.return_value = 'picard.science-station'

        c = load('pkg1')
        assert c.project_org == 'Starfleet'
        assert c.project_name == 'TNG'
        assert c.lambda_name == 'func'
        assert c.lambda_ident == 'starfleet-tng-func-qa'
        assert c.resource_ident == 'starfleet-tng-lambda-func-qa'
        assert c.image_name == 'starfleet-tng'
        assert c.action_key == 'do-action'
        assert c.deployed_env == {
            'GEORDI': 'La Forge',
            'MU_ENV': 'qa',
            'MU_RESOURCE_IDENT': 'starfleet-tng-lambda-func-qa',
        }

        c.aws_acct_id = '1234'
        c.aws_region = 'south'

        assert c.role_arn == 'arn:aws:iam::1234:role/starfleet-tng-lambda-func-qa'
        assert c.sqs_resource == 'arn:aws:sqs:south:1234:starfleet-tng-lambda-func-qa-*'
        assert c.function_arn == 'arn:aws:lambda:south:1234:function:starfleet-tng-func-qa'

    @mock_patch_obj(config.utils, 'host_user')
    def test_mu_toml(self, m_host_user):
        m_host_user.return_value = 'picard.science-station'

        c = load('pkg2')
        assert c.resource_ident == 'starfleet-tng-lambda-func-qa'
        assert c.domain_name == 'pkg2.example.com'

    def test_sqs_configs(self):
        conf = load('pkg-sqs')
        sqs = conf.aws_configs('sqs')
        assert len(sqs) == 2
        assert sqs['celery']['VisibilityTimeout'] == 3600
        assert sqs['photons']['MessageRetentionPeriod'] == 10

    def test_defaults(self):
        conf = config.Config(
            env='qa',
            project_org='Greek',
            project_name='mu',
        )
        assert conf.lambda_ident == 'greek-mu-func-qa'
        assert conf.resource_ident == 'greek-mu-lambda-func-qa'
        assert conf.domain_name is None
