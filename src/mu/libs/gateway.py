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
        certs = self.b3c.list_certificates()['CertificateSummaryList']

        def preference(cert: dict):
            status_rank = {'ISSUED': 2, 'PENDING_VALIDATION': 1}.get(cert['Status'], 0)
            not_after = cert.get('NotAfter')
            return (status_rank, not_after.timestamp() if not_after else 0)

        return sorted(certs, key=preference)

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
    DisableExecuteApiEndpoint: bool = False

    @property
    def ident(self):
        return self.Name


class GatewayAPIs(AWSRecsCRUD):
    client_name: str = 'apigatewayv2'
    rec_cls: type[GatewayAPI] = GatewayAPI
    ensure_updates = True

    def client_list(self):
        return self.b3c.get_apis()['Items']

    def client_create(self, name: str, *, lambda_arn, disable_execute_api):
        self.b3c.create_api(
            Name=name,
            ProtocolType='HTTP',
            Target=lambda_arn,
            DisableExecuteApiEndpoint=disable_execute_api,
        )

    def client_update(self, rec: GatewayAPI, *, lambda_arn, disable_execute_api):
        # lambda_arn is derived from the same identity as the API name, so it can't change.
        self.b3c.update_api(
            ApiId=rec.ApiId,
            DisableExecuteApiEndpoint=disable_execute_api,
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
    CertificateArn: str | None
    TruststoreUri: str | None
    TruststoreVersion: str | None
    TruststoreWarnings: list[str]

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
        api_map['CertificateArn'] = dn_configs[0].get('CertificateArn')

        mtls = data.get('MutualTlsAuthentication') or {}
        api_map['TruststoreUri'] = mtls.get('TruststoreUri')
        api_map['TruststoreVersion'] = mtls.get('TruststoreVersion')
        api_map['TruststoreWarnings'] = mtls.get('TruststoreWarnings', [])

        return cls(**api_map)

    @property
    def ident(self):
        return self.DomainName


class DomainNames(AWSRecsCRUD):
    client_name: str = 'apigatewayv2'
    rec_cls: type[DomainName] = DomainName
    ensure_updates = True

    def client_list(self):
        return self.b3c.get_domain_names()['Items']

    @staticmethod
    def domain_kwargs(
        name: str,
        cert_arn: str,
        truststore_uri: str,
        truststore_version: str | None,
    ) -> dict:
        mtls = {'TruststoreUri': truststore_uri}
        if truststore_version:
            mtls['TruststoreVersion'] = truststore_version

        return {
            'DomainName': name,
            'DomainNameConfigurations': [
                {
                    'CertificateArn': cert_arn,
                    'EndpointType': 'REGIONAL',
                    'SecurityPolicy': 'TLS_1_2',
                },
            ],
            'MutualTlsAuthentication': mtls,
        }

    def client_create(
        self,
        name: str,
        *,
        cert_arn: str,
        truststore_uri: str,
        truststore_version: str,
    ):
        kwargs = self.domain_kwargs(name, cert_arn, truststore_uri, truststore_version)
        if not truststore_uri:
            del kwargs['MutualTlsAuthentication']
        self.b3c.create_domain_name(**kwargs)

    def client_update(
        self,
        rec: DomainName,
        *,
        cert_arn: str,
        truststore_uri: str = '',
        truststore_version: str,
    ):
        self.b3c.update_domain_name(
            **self.domain_kwargs(rec.DomainName, cert_arn, truststore_uri, truststore_version),
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
        self.s3 = self.b3_sess.client('s3')

    def truststore_version(self) -> str | None:
        """
        Latest S3 version of the truststore.  It's passed explicitly because AWS doesn't record or
        report a version when none is given, so the deployed truststore couldn't be confirmed.
        """
        uri = self.config.mtls_truststore_uri
        if not uri:
            return None

        bucket, _, key = uri.removeprefix('s3://').partition('/')
        version = self.s3.head_object(Bucket=bucket, Key=key).get('VersionId')
        # Objects uploaded before versioning was enabled have the version 'null'.
        if not version or version == 'null':
            raise RuntimeError(
                f'Truststore {uri} has no S3 version.  Enable versioning on bucket {bucket} and '
                'upload the truststore again.',
            )
        return version

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
            disable_execute_api=self.config.disable_execute_api_endpoint,
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
            truststore_uri=self.config.mtls_truststore_uri,
            truststore_version=self.truststore_version(),
        )
        log.info(f'  - Host: {gw_domain.GatewayDomainName}')
        log.info(f'  - Alias: {self.domain_name}')
        log.info(f'  - Status: {gw_domain.Status}')
        if gw_domain.TruststoreUri:
            log.info(f'  - Truststore: {gw_domain.TruststoreUri} ({gw_domain.TruststoreVersion})')
        for warning in gw_domain.TruststoreWarnings:
            log.warning(f'  - Truststore warning: {warning}')
        if gw_domain.TruststoreUri and not gw_api.DisableExecuteApiEndpoint:
            log.warning(
                '  - mTLS is enabled but the default execute-api endpoint is not disabled, so '
                'clients can bypass mTLS. Set disable-execute-api-endpoint = true.',
            )

        self.api_mappings.ensure(gw_api.ApiId, self.domain_name)


def acct_cleanup(b3_sess):
    aid = sts.account_id(b3_sess)

    # Ensure we aren't accidently working on an unintended account.
    assert aid == environ.get('MU_TEST_ACCT_ID')

    for name in DomainNames(b3_sess).list():
        print(name)

    # for api_map in APIMappings(b3_sess).list():
    #     print(api_map)
