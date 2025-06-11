from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from unittest import mock

from blazeutils.strings import randchars

from mu.libs import gateway, utils
from mu.libs.aws_recs import AWSRecsCRUD
from mu.libs.testing import mock_patch_obj
from mu_tests import fake


@dataclass
class ACMCerts:
    list_certs: mock.MagicMock
    request_cert: mock.MagicMock
    describe_cert: mock.MagicMock


@contextmanager
def acm_certs(
    certs: gateway.ACMCerts,
    *,
    exists: bool = False,
    gets_created: bool = False,
    describes: list[dict] | None = None,
    status='ISSUED',
):
    if (exists or gets_created) and not describes:
        describes = [fake.cert_describe(status=status)]

    with (
        mock_patch_obj(certs.b3c, 'list_certificates') as m_list_certs,
        mock_patch_obj(certs.b3c, 'request_certificate') as m_request_cert,
        mock_patch_obj(certs.b3c, 'describe_certificate') as m_describe_cert,
    ):
        if gets_created:
            m_list_certs.side_effect = [
                # Cert will get created after this, but doesn't exist yet
                {'CertificateSummaryList': []},
                # Presumably, it's now been created, so it exists
                {'CertificateSummaryList': [fake.cert_summary(status=status)]},
            ]
        else:
            m_list_certs.return_value = {
                'CertificateSummaryList': [fake.cert_summary(status=status)] if exists else (),
            }

        if describes:
            m_describe_cert.side_effect = [{'Certificate': data} for data in describes]

        yield ACMCerts(m_list_certs, m_request_cert, m_describe_cert)


class AWSRecsStub:
    def __init__(self, id_field: str, list_resp_key: str, fake_factory: Callable):
        self.list_resp_key: str = list_resp_key
        self.delete_by_field: str = id_field
        self.fake_factory = fake_factory
        self.recs = {}
        self.calls = []

    def list(self, func_name, kwargs):
        self.calls.append((func_name, kwargs))
        return {
            self.list_resp_key: list(self.recs.values()),
        }

    def create(self, func_name, kwargs):
        self.calls.append((func_name, kwargs))
        self.fake(kwargs)

    def fake(self, pos_kwargs=None, /, **kwargs):
        rec = self.fake_factory(pos_kwargs or kwargs)
        self.recs[rec[self.delete_by_field]] = rec

    def delete(self, func_name, kwargs):
        self.calls.append((func_name, kwargs))
        rec_id = kwargs[self.delete_by_field]
        if rec_id in self.recs:
            del self.recs[rec_id]

    def call_count(self, func_name, **kwargs) -> int:
        needle = (func_name, kwargs)
        return len([call for call in self.calls if call == needle])


class GatewayStubs:
    def __init__(self):
        self.apis = AWSRecsStub('ApiId', 'Items', self.fake_api)
        self.domain_names = AWSRecsStub('DomainName', 'Items', self.fake_domain_name)
        self.acm_certs = AWSRecsStub('CertificateArn', 'CertificateSummaryList', self.fake_cert)
        self.api_mappings = AWSRecsStub('ApiMappingId', 'Items', self.fake_api_mapping)

    def fake_api(self, kwargs):
        return utils.deep_merge(
            fake.gateway_api(api_id=randchars()),
            kwargs,
        )

    def get_apis(self, **kwargs):
        return self.apis.list('get_apis', kwargs)

    def create_api(self, **kwargs):
        return self.apis.create('create_api', kwargs)

    def delete_api(self, **kwargs):
        return self.apis.delete('delete_api', kwargs)

    def fake_domain_name(self, kwargs):
        kwargs = kwargs.copy()
        dnc = 'DomainNameConfigurations'
        kw_dn_configs = kwargs.pop(dnc)

        rec = utils.deep_merge(fake.domain_name(), kwargs)

        for i, dnc_rec in enumerate(kw_dn_configs):
            rec[dnc][i] = utils.deep_merge(rec[dnc][i], dnc_rec)

        return rec

    def get_domain_names(self, **kwargs):
        return self.domain_names.list('get_domain_names', kwargs)

    def create_domain_name(self, **kwargs):
        return self.domain_names.create('create_domain_name', kwargs)

    def delete_domain_name(self, **kwargs):
        return self.domain_names.delete('delete_domain_name', kwargs)

    def fake_cert(self, kwargs):
        return utils.deep_merge(
            fake.cert_summary(),
            kwargs,
        )

    def list_certificates(self, **kwargs):
        return self.acm_certs.list('list_certificates', kwargs)

    def request_certificate(self, **kwargs):
        return self.acm_certs.create('request_certificate', kwargs)

    def delete_certificate(self, **kwargs):
        return self.acm_certs.delete('delete_certificate', kwargs)

    def describe_certificate(self, **kwargs):
        self.acm_certs.calls.append(('describe_certificate', kwargs))
        arn = kwargs['CertificateArn']
        self.acm_certs.recs[arn] = utils.deep_merge(fake.cert_describe(), self.acm_certs.recs[arn])
        return {
            'Certificate': self.acm_certs.recs[arn],
        }

    def fake_api_mapping(self, kwargs):
        return utils.deep_merge(
            fake.gateway_api_mapping(),
            kwargs,
        )

    def get_api_mappings(self, **kwargs):
        return self.api_mappings.list('get_api_mappings', kwargs)

    def create_api_mapping(self, **kwargs):
        return self.api_mappings.create('create_api_mapping', kwargs)

    def delete_api_mapping(self, **kwargs):
        return self.api_mappings.delete('delete_api_mapping', kwargs)

    @contextmanager
    def mock(self, *recs_cruds: tuple[AWSRecsCRUD]):
        originals = [rc.b3c for rc in recs_cruds]
        for rc in recs_cruds:
            rc.b3c = self
        try:
            yield self
        finally:
            for rc in recs_cruds:
                rc.b3c = originals.pop(0)

    @contextmanager
    def mock_gw(self, gw: gateway.Gateway):
        with (
            self.mock(
                gw.acm_certs,
                gw.gw_apis,
                gw.gw_domains,
                gw.api_mappings,
            ) as stub,
            mock_patch_obj(gw.func_perms, 'ensure') as m_ensure,
            mock_patch_obj(gw.func_perms, 'client_list'),
        ):
            self.m_func_perms_ensure = m_ensure
            yield stub


@dataclass
class GatewayAPIs:
    get: mock.MagicMock
    create: mock.MagicMock


@contextmanager
def gateway_apis(
    apis: gateway.GatewayAPIs,
    *,
    exists=False,
    gets_created: bool = False,
):
    with (
        mock_patch_obj(apis.b3c, 'get_apis') as m_get,
        mock_patch_obj(apis.b3c, 'create_api') as m_create,
    ):
        m_get.return_value = {}
        if gets_created:

            def side_effect():
                # Record will get created after this, but doesn't exist yet
                yield {'Items': []}
                # Presumably, it's now been created, so return a fake
                while True:
                    yield {'Items': [fake.gateway_api()]}

            m_get.side_effect = side_effect
        else:
            m_get.return_value = {
                'Items': [fake.gateway_api()] if exists else (),
            }

        yield GatewayAPIs(m_get, m_create)


@dataclass
class DomainNames:
    get: mock.MagicMock
    create: mock.MagicMock


@contextmanager
def domain_names(
    d_names: gateway.DomainNames,
    *,
    exists=False,
    gets_created: bool = False,
):
    with (
        mock_patch_obj(d_names.b3c, 'get_domain_names') as m_get,
        mock_patch_obj(d_names.b3c, 'create_domain_name') as m_create,
    ):
        m_get.return_value = {}
        if gets_created:
            m_get.side_effect = [
                # Record will get created after this, but doesn't exist yet
                {'Items': []},
                # Presumably, it's now been created, so it exists
                {'Items': [fake.gateway_api()]},
            ]
        else:
            m_get.return_value = {
                'Items': [fake.gateway_api()] if exists else (),
            }

        yield GatewayAPIs(m_get, m_create)
