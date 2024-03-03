from pathlib import Path

from mu import config


tests_dpath = Path(__file__).parent


def load(*start_at):
    return config.load(tests_dpath.joinpath(*start_at))


class TestConfig:
    def test_minimal_config_defaults(self):
        c: config.Config = load('pkg1')
        assert c.project_name == 'TNG'
        assert c.project_org == 'Starfleet'
        assert c.lambda_name == 'starfleet-tng-main'
        assert c.image_name == 'starfleet-tng-lambda'
        assert c.aws_region == 'us-east-2'
        assert c.default_env == 'local-dev'
        assert c.action_key == 'lambda-action'
