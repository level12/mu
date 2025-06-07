from contextlib import contextmanager
from dataclasses import dataclass
from unittest import mock

from mu.libs import gateway
from mu.libs.testing import mock_patch_obj
from mu.tests import fake


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
    is_created: bool = False,
    describes: list[dict] | None = None,
):
    if (exists or is_created) and not describes:
        describes = [fake.cert_describe()]

    with (
        mock_patch_obj(certs.b3c, 'list_certificates') as m_list_certs,
        mock_patch_obj(certs.b3c, 'request_certificate') as m_request_cert,
        mock_patch_obj(certs.b3c, 'describe_certificate') as m_describe_cert,
    ):
        if is_created:
            m_list_certs.side_effect = [
                # Cert will get created after this, but doesn't exist yet
                {'CertificateSummaryList': []},
                # Presumably, it's now been created, so it exists
                {'CertificateSummaryList': [fake.cert_summary()]},
            ]
        else:
            m_list_certs.return_value = {
                'CertificateSummaryList': [fake.cert_summary()] if exists else (),
            }

        if describes:
            m_describe_cert.side_effect = [{'Certificate': data} for data in describes]

        yield ACMCerts(m_list_certs, m_request_cert, m_describe_cert)


@dataclass
class GatewayAPIs:
    get: mock.MagicMock
    create: mock.MagicMock


@contextmanager
def gateway_apis(
    apis: gateway.GatewayAPIs,
    *,
    exists=False,
    is_created: bool = False,
):
    with (
        mock_patch_obj(apis.b3c, 'get_apis') as m_get,
        mock_patch_obj(apis.b3c, 'create_api') as m_create,
    ):
        m_get.return_value = {}
        if is_created:
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
