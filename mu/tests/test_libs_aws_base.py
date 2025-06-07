from mu.config import Config
from mu.libs import gateway, testing
from mu.libs.testing import Logs


class TestAWSRecsIntegration:
    def test_basics(self, config: Config, b3_sess, logs: Logs):
        with testing.tmp_lambda(b3_sess, config) as la:
            apis = gateway.GatewayAPIs(b3_sess)

            # Ensure not present from previous test
            apis.delete(config.resource_ident)
            apis.clear_cache()
            logs.clear()

            # Ensure created
            apis.ensure(config.resource_ident, lambda_arn=la.arn)
            assert apis.get(config.resource_ident)

            # Call again, should be cached
            apis.ensure(config.resource_ident, lambda_arn=la.arn)
            assert apis.get(config.resource_ident)

            assert apis.get('foobar') is None

            apis.delete(config.resource_ident)
            assert apis.get(config.resource_ident) is None

            # Make sure no errors when called without upstream record present
            # And that we cleared the cache
            apis.delete(config.resource_ident)

            assert logs.messages == [
                'GatewayAPIs ensure: record created',
                'GatewayAPIs ensure: record existed',
                'GatewayAPIs delete: record deleted',
            ]
