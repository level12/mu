import pytest

from mu.config import Config
from mu.libs import gateway, testing
from mu.libs.testing import Logs, mock_patch_obj
from mu.tests import mocking

from . import fake


class TestCRUDIntegration:
    """A basic CRUD integration test for each API that uses AWSRecsCRUD"""

    def test_certs(self, config: Config, b3_sess, logs: Logs):
        domain_name = f'{config.project_ident}.level12.app'

        certs = gateway.ACMCerts(b3_sess)

        # Ensure not present from previous test
        certs.delete(domain_name)
        certs.clear_cache()
        logs.clear()

        # Ensure created
        certs.ensure(domain_name)
        assert certs.get(domain_name)

        # No error when exists
        certs.ensure(domain_name)
        assert certs.get(domain_name)

        certs.log_dns_validation(domain_name)

        # Delete
        certs.delete(domain_name)
        assert certs.get(config.resource_ident) is None

        # No error when not present
        certs.delete(config.resource_ident)

        assert logs.messages[0] == 'ACMCerts ensure: record created'
        # Because we might wait for the cert to be available, there
        # could be seom waiting for" messages.  Since it varies, just
        # skip them.
        assert logs.messages[-1] == 'ACMCerts delete: record deleted'

    def test_api_gateway(self, config: Config, b3_sess, logs: Logs):
        with testing.tmp_lambda(b3_sess, config) as la:
            apis = gateway.GatewayAPIs(b3_sess)

            # Ensure not present from previous test
            apis.delete(config.resource_ident)
            apis.clear_cache()
            logs.clear()

            # Ensure created
            apis.ensure(config.resource_ident, lambda_arn=la.arn)
            assert apis.get(config.resource_ident).ApiEndpoint

            # No error when exists
            apis.ensure(config.resource_ident, lambda_arn=la.arn)
            assert apis.get(config.resource_ident)

            # Delete
            apis.delete(config.resource_ident)
            assert apis.get(config.resource_ident) is None

            # No error when not present
            apis.delete(config.resource_ident)

            assert logs.messages == [
                'GatewayAPIs ensure: record created',
                'GatewayAPIs ensure: record existed',
                'GatewayAPIs delete: record deleted',
            ]


class TestACMCerts:
    @pytest.fixture
    def certs(self):
        return gateway.ACMCerts(testing.b3_sess())

    def test_ensure_creates(self, certs: gateway.ACMCerts, logs: Logs):
        with mocking.acm_certs(certs, is_created=True):
            assert certs.ensure('app.example.com')

        assert logs.messages == [
            'ACMCerts ensure: record created',
        ]

    def test_ensure_waits(self, certs: gateway.ACMCerts, logs: Logs):
        with (
            mock_patch_obj(certs.b3c, 'list_certificates') as m_list_certs,
            mock_patch_obj(certs.b3c, 'request_certificate'),
        ):
            m_list_certs.side_effect = (
                # First list() to see if it exists already()
                {'CertificateSummaryList': []},
                # Second list() for the post-ensure get
                {'CertificateSummaryList': []},
                # Third list() for the post-ensure get retry
                {'CertificateSummaryList': [fake.cert_summary()]},
            )
            assert certs.ensure('app.example.com')

        assert logs.messages == [
            'ACMCerts ensure: record created',
            'Waiting 0.1s for ACMCert to be created',
        ]

    def test_from_aws_summary(self, certs: gateway.ACMCerts):
        with mock_patch_obj(certs.b3c, 'list_certificates') as m_list_certs:
            m_list_certs.return_value = {'CertificateSummaryList': [fake.cert_summary()]}
            cert: gateway.ACMCert = certs.ensure('app.example.com')

        assert cert.arn == 'arn:mu-test-cert-arn'
        assert cert.DomainName == 'app.example.com'
        assert cert.Status == 'PENDING_VALIDATION'
        assert cert.dns_validation is None

    def test_hydrate(self, certs: gateway.ACMCerts, logs: Logs):
        describe_resps = (
            fake.cert_describe_minimal(),
            fake.cert_describe_minimal(),
            fake.cert_describe(),
        )
        with mocking.acm_certs(certs, exists=True, describes=describe_resps) as mocks:
            cert: gateway.ACMCert = certs.get('app.example.com')
            assert not cert.dns_validation

            cert = certs.hydrate(cert)
            # The arn isn't the same as tested below b/c the arn comes from the fake summary record.
            # It has a different arn than the describe record.  So this doesn't match like it would
            # in prod but helps ensure we are pulling fake data from the right place.
            mocks.describe_cert.assert_called_with(CertificateArn='arn:mu-test-cert-arn')

            assert cert.arn == 'arn:mu-test-cert-desc'
            assert cert.DomainName == 'app.example.com'
            assert cert.Status == 'PENDING_VALIDATION'

            validation = cert.dns_validation
            assert validation.Name == '_abcfake.app.example.com.'
            assert validation.Type == 'CNAME'
            assert validation.Value == '_defake.acm-validations.aws.'

        assert logs.messages == [
            'ACMCerts hydrate: fetching full cert description',
            'Waiting 0.1s for full cert description',
            'Waiting 0.25s for full cert description',
        ]

    def test_log_dns_validation(self, certs: gateway.ACMCerts, logs: Logs):
        with mocking.acm_certs(certs, exists=True):
            certs.log_dns_validation('app.example.com')

        assert logs.messages == [
            'ACMCerts hydrate: fetching full cert description',
            'Cert ensure: DNS validation pending:',
            '  - DNS Type: CNAME',
            '  - DNS Name: _abcfake.app.example.com.',
            '  - DNS Value: _defake.acm-validations.aws.',
        ]


class TestGateway:
    @pytest.fixture
    def gw(self, config):
        return gateway.Gateway(config, 'app.example.com', testing=True)

    def test_provision(self, gw: gateway.Gateway, logs: Logs):
        with (
            mocking.acm_certs(gw.acm_certs, is_created=True),
            mocking.gateway_apis(gw.gw_apis, is_created=True),
        ):
            gw.provision()

        assert logs.messages == [
            'ACMCerts ensure: record created',
            'GatewayAPIs ensure: record created',
            '  - Api Endpoint: https://cnstryckkl.execute-api.us-east-2.amazonaws.com',
            'ACMCerts hydrate: fetching full cert description',
            'Cert ensure: DNS validation pending:',
            '  - DNS Type: CNAME',
            '  - DNS Name: _abcfake.app.example.com.',
            '  - DNS Value: _defake.acm-validations.aws.',
        ]
