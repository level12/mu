from pathlib import Path

from mu import config
from mu.libs.testing import mock_patch_obj


tests_dpath = Path(__file__).parent


def load(*start_at) -> config.Config:
    return config.load(tests_dpath.joinpath(*start_at))


class TestConfig:
    @mock_patch_obj(config.utils, 'host_user')
    def test_minimal_config_defaults(self, m_host_user):
        m_host_user.return_value = 'picard.science-station'

        c = load('pkg1')
        assert c.project_org == 'Starfleet'
        assert c.project_name == 'TNG'
        assert c.lambda_name == 'starfleet-tng-handler'
        assert c.image_name == 'tng'
        assert c.default_env == 'picard.science-station'
        assert c.action_key == 'do-action'

    @mock_patch_obj(config.utils, 'host_user')
    def test_mu_toml(self, m_host_user):
        m_host_user.return_value = 'picard.science-station'

        c = load('pkg2')
        assert c.project_org == 'Starfleet'
        assert c.project_name == 'TNG'
        assert c.lambda_name == 'starfleet-tng-handler'
        assert c.image_name == 'tng'
        assert c.default_env == 'picard.science-station'
        assert c.action_key == 'do-action'
