import pytest

from mu.config import Config
from mu.libs import gateway, testing, utils
from mu.libs.testing import Logs, mock_patch_obj
from mu_tests import mocking

from . import fake


@pytest.fixture(scope='module')
def b3s_fake():
    return testing.b3_sess()


@pytest.mark.integration
class TestIntegration:
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
        certs.delete(domain_name)

        assert logs.messages[0] == 'ACMCerts ensure: record created'
        # Because we might wait for the cert to be available, there
        # could be seom waiting for" messages.  Since it varies, just
        # skip them.
        assert logs.messages[-1] == 'ACMCerts delete: record deleted'

    def test_api_gateway(self, config: Config, b3_sess, logs: Logs):
        tmp_la = testing.tmp_lambda(b3_sess, config)
        apis = gateway.GatewayAPIs(b3_sess)

        # Ensure not present from previous test
        apis.delete(config.resource_ident)
        apis.clear_cache()
        logs.clear()

        # Ensure created
        apis.ensure(config.resource_ident, lambda_arn=tmp_la.arn)
        assert apis.get(config.resource_ident).ApiEndpoint

        # No error when exists
        apis.ensure(config.resource_ident, lambda_arn=tmp_la.arn)
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

    def test_domain_names(self, config: Config, b3_sess, logs: Logs):
        domain_name = testing.PERSISTENT_CERT_DOMAIN

        cert = testing.persistent_cert(b3_sess)
        d_names = gateway.DomainNames(b3_sess)

        # Ensure not present from previous test
        d_names.delete(domain_name)
        d_names.clear_cache()
        logs.clear()

        # Ensure created
        d_names.ensure(domain_name, cert_arn=cert.arn)
        assert d_names.get(domain_name).GatewayDomainName

        # No error when exists
        d_names.ensure(domain_name, cert_arn=cert.arn)
        assert d_names.get(domain_name)

        # Delete
        d_names.delete(domain_name)
        assert d_names.get(domain_name) is None

        # No error when not present
        d_names.delete(domain_name)

        assert logs.messages == [
            'DomainNames ensure: record created',
            'DomainNames ensure: record existed',
            'DomainNames delete: record deleted',
        ]

    def test_api_mappings(self, config: Config, b3_sess, logs: Logs):
        apis = gateway.GatewayAPIs(b3_sess)
        d_names = gateway.DomainNames(b3_sess)
        mappings = gateway.APIMappings(b3_sess)

        domain_name = testing.PERSISTENT_CERT_DOMAIN
        cert = testing.persistent_cert(b3_sess)
        la = testing.tmp_lambda(b3_sess, config)

        gw_api: gateway.APIMapping = apis.ensure(config.resource_ident, lambda_arn=la.arn)
        d_names.ensure(domain_name, cert_arn=cert.arn)

        # Ensure not present from previous test
        mappings.delete(gw_api.ApiId, domain_name)
        mappings.clear_cache()
        logs.clear()

        # Ensure created
        mappings.ensure(gw_api.ApiId, domain_name)
        assert mappings.get(gw_api.ApiId, domain_name).ApiId == gw_api.ApiId
        assert mappings.get(gw_api.ApiId, domain_name).Stage == '$default'

        # No error when exists
        mappings.ensure(gw_api.ApiId, domain_name)
        assert mappings.get(gw_api.ApiId, domain_name)

        # Delete
        mappings.delete(gw_api.ApiId, domain_name)
        assert mappings.get(gw_api.ApiId, domain_name) is None

        # No error when not present
        mappings.delete(gw_api.ApiId, domain_name)

        assert logs.messages == [
            'APIMappings ensure: record created',
            'APIMappings ensure: record existed',
            'APIMappings delete: record deleted',
        ]

    def test_provision_and_delete_persistent_cert(self, config: Config, b3_sess, logs: Logs):
        config.domain_name = testing.PERSISTENT_CERT_DOMAIN

        tmp_la = testing.tmp_lambda(b3_sess, config, recreate=True)
        config._func_arn_override = tmp_la.FunctionArn

        gw = gateway.Gateway(config, b3_sess=b3_sess)

        # Delete to avoid prior test contamination but keep our persistent cert!
        gw.delete(delete_cert=False)
        logs.clear()

        gw.provision()

        api_endpoint = gw.gw_apis.get(config.resource_ident).ApiEndpoint
        dn_host = gw.gw_domains.get(config.domain_name).GatewayDomainName

        assert logs.messages == [
            'ACMCerts ensure: record existed',
            'GatewayAPIs ensure: record created',
            f'  - Api Endpoint: {api_endpoint}',
            'FunctionPermissions ensure: record created',
            'DomainNames ensure: record created',
            f'  - Host: {dn_host}',
            f'  - Alias: {config.domain_name}',
            '  - Status: AVAILABLE',
            'APIMappings ensure: record created',
        ]

        logs.clear()
        gw.delete(delete_cert=False)

        assert logs.messages == [
            'APIMappings delete: record deleted',
            'DomainNames delete: record deleted',
            'GatewayAPIs delete: record deleted',
            'FunctionPermissions delete: record deleted',
        ]

    def test_provision_and_delete_fresh_cert(self, config: Config, b3_sess, logs: Logs):
        config.domain_name = f'{config.project_ident}.level12.app'

        gw = gateway.Gateway(config, b3_sess=b3_sess)

        # Delete to avoid prior test contamination
        gw.delete()
        logs.clear()

        gw.provision()

        assert logs.messages[0] == 'ACMCerts ensure: record created'
        assert (
            logs.messages[-1]
            == 'Gateway provision: can not continue until certificate is validated.'
        )

        logs.clear()
        gw.delete()

        assert logs.messages == [
            'ACMCerts delete: record deleted',
        ]


class TestCRUD:
    """Stub based tests of AWSRecsCRUD implementations"""

    def test_api_gateway(self, b3s_fake, logs: Logs):
        apis = gateway.GatewayAPIs(b3s_fake)

        with mocking.GatewayStubs().mock(apis) as stub:
            apis.ensure('phaser-api', lambda_arn='arn:lambda:engage')
            api_id = apis.get('phaser-api').ApiId

            apis.ensure('phaser-api', lambda_arn='arn:lambda:engage')

            apis.delete('phaser-api')
            assert apis.get('phaser-api') is None

            apis.delete('phaser-api')

            assert (
                stub.apis.call_count(
                    'create_api',
                    Name='phaser-api',
                    ProtocolType='HTTP',
                    Target='arn:lambda:engage',
                )
                == 1
            )

            assert stub.apis.call_count('delete_api', ApiId=api_id)

        assert logs.messages == [
            'GatewayAPIs ensure: record created',
            'GatewayAPIs ensure: record existed',
            'GatewayAPIs delete: record deleted',
        ]

    def test_domain_names(self, b3s_fake, logs: Logs):
        d_names = gateway.DomainNames(b3s_fake)
        domain_name = 'app.example.com'
        cert_arn = 'arn:acm:cert:app'

        with mocking.GatewayStubs().mock(d_names) as stub:
            d_names.ensure(domain_name, cert_arn=cert_arn)
            rec = d_names.get(domain_name)

            d_names.ensure(domain_name, cert_arn=cert_arn)

            d_names.delete(domain_name)
            assert d_names.get(domain_name) is None

            d_names.delete(domain_name)

            assert (
                stub.domain_names.call_count(
                    'create_domain_name',
                    DomainName=domain_name,
                    DomainNameConfigurations=[
                        {
                            'CertificateArn': cert_arn,
                            'EndpointType': 'REGIONAL',
                            'SecurityPolicy': 'TLS_1_2',
                        },
                    ],
                )
                == 1
            )

            assert stub.domain_names.call_count('delete_domain_name', DomainName=rec.DomainName)

        assert logs.messages == [
            'DomainNames ensure: record created',
            'DomainNames ensure: record existed',
            'DomainNames delete: record deleted',
        ]

    def test_acm_certs(self, b3s_fake, logs: Logs):
        certs = gateway.ACMCerts(b3s_fake)
        domain_name = 'app.example.com'

        with mocking.GatewayStubs().mock(certs) as stub:
            certs.ensure(domain_name)
            rec = certs.get(domain_name)

            certs.ensure(domain_name)

            certs.delete(domain_name)
            assert certs.get(domain_name) is None

            certs.delete(domain_name)

            assert (
                stub.acm_certs.call_count(
                    'request_certificate',
                    DomainName=domain_name,
                    ValidationMethod='DNS',
                )
                == 1
            )

            assert stub.acm_certs.call_count('delete_certificate', CertificateArn=rec.arn)

        assert logs.messages == [
            'ACMCerts ensure: record created',
            'ACMCerts ensure: record existed',
            'ACMCerts delete: record deleted',
        ]

    def test_api_mappings(self, b3s_fake, logs: Logs):
        mappings = gateway.APIMappings(b3s_fake)
        domain_name = 'app.example.com'
        gw_api_id = 'gw:api:id'

        with mocking.GatewayStubs().mock(mappings) as stub:
            mappings.ensure(gw_api_id, domain_name)
            rec: gateway.APIMapping = mappings.get(gw_api_id, domain_name)
            assert rec.ApiId == gw_api_id
            assert rec.Stage == '$default'

            # We'll check below to make sure only one create call is issued
            mappings.ensure(gw_api_id, domain_name)

            # Delete
            mappings.delete(gw_api_id, domain_name)
            assert mappings.get(gw_api_id, domain_name) is None

            # No error when not present and only a single api call issued
            mappings.delete(gw_api_id, domain_name)

            assert (
                stub.api_mappings.call_count(
                    'delete_api_mapping',
                    ApiMappingId=rec.ApiMappingId,
                    DomainName=domain_name,
                )
                == 1
            )

        assert logs.messages == [
            'APIMappings ensure: record created',
            'APIMappings ensure: record existed',
            'APIMappings delete: record deleted',
        ]


class TestACMCerts:
    @pytest.fixture
    def certs(self):
        return gateway.ACMCerts(testing.b3_sess())

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
        cert = gateway.ACMCert.from_aws(fake.cert_summary())

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

    def test_log_dns_validation(self, b3s_fake, logs: Logs):
        certs = gateway.ACMCerts(b3s_fake)

        with mocking.GatewayStubs().mock(certs) as stub:
            stub.acm_certs.fake(status='PENDING_VALIDATION')
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
        config.domain_name = 'app.example.com'
        return gateway.Gateway(config, testing=True)

    def test_provision_cert_pending(self, gw: gateway.Gateway, logs: Logs):
        with mocking.GatewayStubs().mock_gw(gw):
            gw.provision()

        assert logs.messages == [
            'ACMCerts ensure: record created',
            'ACMCerts hydrate: fetching full cert description',
            'Cert ensure: DNS validation pending:',
            '  - DNS Type: CNAME',
            '  - DNS Name: _abcfake.app.example.com.',
            '  - DNS Value: _defake.acm-validations.aws.',
            'Gateway provision: can not continue until certificate is validated.',
        ]

    def test_provision_cert_status_unknown(self, gw: gateway.Gateway, logs: Logs):
        with mocking.GatewayStubs().mock_gw(gw) as stub:
            stub.acm_certs.fake(Status='FAILED')
            gw.provision()

        assert logs.messages == [
            'ACMCerts ensure: record existed',
            'Gateway provision: certificate has unknown status (FAILED).',
            '  - Use `mu domain-name ...` to inspect, maybe delete cert, and try again.',
        ]

    def test_provision_cert_issued(self, gw: gateway.Gateway, logs: Logs, config: Config):
        with mocking.GatewayStubs().mock_gw(gw) as stub:
            stub.acm_certs.fake(Status='ISSUED')
            gw.provision()

        assert logs.messages == [
            'ACMCerts ensure: record existed',
            'GatewayAPIs ensure: record created',
            '  - Api Endpoint: https://cnstryckkl.execute-api.us-east-2.amazonaws.com',
            'DomainNames ensure: record created',
            '  - Host: d-bbddxy8sl8.execute-api.us-east-2.amazonaws.com',
            '  - Alias: app.example.com',
            '  - Status: AVAILABLE',
            'APIMappings ensure: record created',
        ]

        assert len(stub.apis.recs) == 1
        api_id = utils.first(stub.apis.recs)

        stub.m_func_perms_ensure.assert_called_once_with(
            'greek-mu-lambda-func-qa-api-invoke',
            config=config,
            perm_type='api-invoke',
            api_key=api_id,
        )

    def test_cert_describe(self, gw: gateway.Gateway):
        with mocking.acm_certs(gw.acm_certs, exists=True):
            cert: dict = gw.cert_describe()
            assert cert['CertificateArn'] == 'arn:mu-test-cert-desc'
