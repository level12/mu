from dataclasses import dataclass
import logging
from os import environ
from typing import Self

import boto3
from botocore.exceptions import ClientError

from mu.libs import utils

from ..config import Config
from . import auth, lamb, sts
from .aws_recs import AWSRec, AWSRecsCRUD


log = logging.getLogger(__name__)

notset = ()


@dataclass
class ACMCertDNSValidation:
    Name: str
    Type: str
    Value: str


@dataclass
class ACMCert(AWSRec):
    CertificateArn: str
    DomainName: str
    Status: str
    dns_validation: ACMCertDNSValidation | None = None

    @property
    def ident(self):
        return self.DomainName.lower()

    @property
    def arn(self):
        return self.CertificateArn

    @classmethod
    def from_aws(cls, data: dict) -> Self:
        cert_data = cls.take_fields(data)

        options = data.get('DomainValidationOptions')
        if options and options[0].get('ResourceRecord'):
            cert_data['dns_validation'] = ACMCertDNSValidation(**options[0]['ResourceRecord'])

        return cls(**cert_data)


class ACMCerts(AWSRecsCRUD):
    client_name: str = 'acm'
    rec_cls: type[ACMCert] = ACMCert
    # Certs aren't immediately in the listing after create, so wait for them
    ensure_get_wait = True

    def get(self, ident: str, wait=False):
        return super().get(ident.lower(), wait=wait)

    def client_list(self):
        return self.b3c.list_certificates()['CertificateSummaryList']

    def client_create(self, domain_name: str):
        self.b3c.request_certificate(
            DomainName=domain_name,
            ValidationMethod='DNS',
        )

    def client_delete(self, rec: ACMCert):
        try:
            self.b3c.delete_certificate(CertificateArn=rec.arn)
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise

    def client_describe(self, rec: ACMCert) -> dict:
        return self.b3c.describe_certificate(CertificateArn=rec.arn)['Certificate']

    def hydrate(self, rec: ACMCert):
        log.info(f'{self.log_prefix} hydrate: fetching full cert description')

        def full_cert_desc():
            desc = self.client_describe(rec)
            options = desc.get('DomainValidationOptions')
            if options and options[0].get('ResourceRecord'):
                return desc

        cert_data = utils.retry(
            full_cert_desc,
            count=60,
            waiting_for='full cert description',
        )

        if cert_data is None:
            raise RuntimeError(
                "Waited 60s for certificate validation but it didn't appear. Try again.",
            )
        self._list_recs[rec.ident] = cert = ACMCert.from_aws(cert_data)
        return cert

    def dns_hydrate(self, domain_name):
        cert: ACMCert = self.get(domain_name)
        if cert.Status == 'PENDING_VALIDATION' and cert.dns_validation is None:
            return self.hydrate(cert)
        return cert

    def log_dns_validation(self, domain_name: str):
        cert = self.dns_hydrate(domain_name)

        if cert.Status == 'PENDING_VALIDATION':
            log.info('Cert ensure: DNS validation pending:')
            log.info(f'  - DNS Type: {cert.dns_validation.Type}')
            log.info(f'  - DNS Name: {cert.dns_validation.Name}')
            log.info(f'  - DNS Value: {cert.dns_validation.Value}')


@dataclass
class GatewayAPI(AWSRec):
    ApiId: str
    Name: str
    ApiEndpoint: str

    @property
    def ident(self):
        return self.Name


class GatewayAPIs(AWSRecsCRUD):
    client_name: str = 'apigatewayv2'
    rec_cls: type[GatewayAPI] = GatewayAPI

    def client_list(self):
        return self.b3c.get_apis()['Items']

    def client_create(self, name: str, *, lambda_arn):
        self.b3c.create_api(
            Name=name,
            ProtocolType='HTTP',
            Target=lambda_arn,
        )

    def client_delete(self, rec: GatewayAPI):
        self.b3c.delete_api(
            ApiId=rec.ApiId,
        )


@dataclass
class DomainName(AWSRec):
    DomainName: str
    GatewayDomainName: str
    Status: str

    @classmethod
    def from_aws(cls, data: dict) -> Self:
        api_map: dict = cls.take_fields(data)
        dn_configs = data['DomainNameConfigurations']
        if len(dn_configs) != 1:
            raise ValueError(
                f'Expected GatewayDomain to have one DomainNameConfigurations: \n{dn_configs}',
            )
        api_map['GatewayDomainName'] = dn_configs[0]['ApiGatewayDomainName']
        api_map['Status'] = dn_configs[0]['DomainNameStatus']

        return cls(**api_map)

    @property
    def ident(self):
        return self.DomainName


class DomainNames(AWSRecsCRUD):
    client_name: str = 'apigatewayv2'
    rec_cls: type[DomainName] = DomainName

    def client_list(self):
        return self.b3c.get_domain_names()['Items']

    def client_create(self, name: str, *, cert_arn: str):
        self.b3c.create_domain_name(
            DomainName=name,
            DomainNameConfigurations=[
                {
                    'CertificateArn': cert_arn,
                    'EndpointType': 'REGIONAL',
                    'SecurityPolicy': 'TLS_1_2',
                },
            ],
        )

    def client_delete(self, domain_name: DomainName):
        self.b3c.delete_domain_name(DomainName=domain_name.DomainName)


@dataclass
class APIMapping(AWSRec):
    ApiId: str
    ApiMappingId: str
    Stage: str

    @property
    def ident(self):
        # TODO: this should really be ApiId and Stage I believe but the ClientBase api
        # isn't built to use composite keys.  We only use the $default stage right now anyway.
        return self.ApiId


class APIMappings(AWSRecsCRUD):
    client_name: str = 'apigatewayv2'
    rec_cls: type[APIMapping] = APIMapping

    def client_list(self, domain_name):
        return self.b3c.get_api_mappings(DomainName=domain_name)['Items']

    def client_create(self, api_id: str, *, domain_name, stage='$default'):
        self.b3c.create_api_mapping(
            DomainName=domain_name,
            ApiId=api_id,
            Stage=stage,
        )

    def client_delete(self, rec: APIMapping, domain_name: str):
        self.b3c.delete_api_mapping(ApiMappingId=rec.ApiMappingId, DomainName=domain_name)

    def ensure(self, api_id: str, domain_name: str):
        # Need domain name for listing and create
        return super().ensure(api_id, domain_name, domain_name=domain_name)


class Gateway:
    def __init__(
        self,
        config: Config,
        *,
        b3_sess: boto3.Session = None,
        testing=False,
    ):
        self.config: Config = config
        self.b3_sess = b3_sess or auth.b3_sess(config, testing=testing)

        self.domain_name = self.config.domain_name
        self.lambda_arn = config.function_arn
        self.api_name = config.resource_ident

        self.acm_certs = ACMCerts(self.b3_sess)
        self.gw_apis = GatewayAPIs(self.b3_sess)
        self.gw_domains = DomainNames(self.b3_sess)
        self.api_mappings = APIMappings(self.b3_sess)
        self.func_perms = lamb.FunctionPermissions(self.b3_sess)

    def cert_describe(self) -> dict:
        cert = self.acm_certs.get(self.domain_name)
        return self.acm_certs.client_describe(cert)

    def delete(self, delete_cert=True):
        gw_api: GatewayAPI = self.gw_apis.get(self.config.resource_ident)

        if gw_api:
            self.api_mappings.delete(gw_api.ApiId, self.domain_name)

        self.gw_domains.delete(self.domain_name)
        self.gw_apis.delete(self.config.resource_ident)
        self.func_perms.delete(self.config.api_invoke_stmt_id, self.config.function_arn)

        if delete_cert:
            self.acm_certs.delete(self.domain_name)

    def provision(self):
        cert: ACMCert = self.acm_certs.ensure(self.domain_name)
        self.acm_certs.log_dns_validation(self.domain_name)

        if cert.Status == 'PENDING_VALIDATION':
            log.info('Gateway provision: can not continue until certificate is validated.')
            return

        if cert.Status != 'ISSUED':
            log.info(f'Gateway provision: certificate has unknown status ({cert.Status}).')
            log.info(
                '  - Use `mu domain-name ...` to inspect, maybe delete cert, and try again.',
            )
            return

        gw_api: GatewayAPI = self.gw_apis.ensure(
            self.config.resource_ident,
            lambda_arn=self.config.function_arn,
        )
        log.info(f'  - Api Endpoint: {gw_api.ApiEndpoint}')

        # TODO: we could be smarter about only replacing if there is a difference
        self.func_perms.delete(self.config.api_invoke_stmt_id, self.config.function_arn)
        self.func_perms.ensure(
            self.config.api_invoke_stmt_id,
            config=self.config,
            perm_type='api-invoke',
            api_key=gw_api.ApiId,
        )

        gw_domain: DomainName = self.gw_domains.ensure(
            self.domain_name,
            cert_arn=cert.arn,
        )
        log.info(f'  - Host: {gw_domain.GatewayDomainName}')
        log.info(f'  - Alias: {self.domain_name}')
        log.info(f'  - Status: {gw_domain.Status}')

        self.api_mappings.ensure(gw_api.ApiId, self.domain_name)


def acct_cleanup(b3_sess):
    aid = sts.account_id(b3_sess)

    # Ensure we aren't accidently working on an unintended account.
    assert aid == environ.get('MU_TEST_ACCT_ID')

    for name in DomainNames(b3_sess).list():
        print(name)

    # for api_map in APIMappings(b3_sess).list():
    #     print(api_map)
