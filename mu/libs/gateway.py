from dataclasses import dataclass
import logging
from typing import Self

from botocore.exceptions import ClientError

from mu.libs import utils

from ..config import Config
from . import auth
from .aws_base import AWSRec, AWSRecsCRUD


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
        self.b3c.delete_certificate(CertificateArn=rec.arn)

    def hydrate(self, rec: ACMCert):
        log.info(f'{self.log_prefix} hydrate: fetching full cert description')

        def full_cert_desc():
            try:
                desc = self.b3c.describe_certificate(CertificateArn=rec.arn)['Certificate']
                options = desc.get('DomainValidationOptions')
                if options and options[0].get('ResourceRecord'):
                    return desc
            except Exception as e:
                print(e)

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

    def log_dns_validation(self, domain_name: str):
        cert: ACMCert = self.get(domain_name)
        if cert.Status == 'PENDING_VALIDATION':
            if cert.dns_validation is None:
                # Cert data was loaded from the list operation and we don't have DNS info available
                # yet.
                cert = self.hydrate(cert)

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
class LambdaFunction(AWSRec):
    FunctionName: str
    FunctionArn: str

    @property
    def ident(self):
        return self.FunctionName

    @property
    def arn(self):
        return self.FunctionArn


class Lambdas(AWSRecsCRUD):
    client_name: str = 'lambda'
    rec_cls: type[LambdaFunction] = LambdaFunction

    def client_list(self):
        return self.b3c.list_functions()['Functions']

    def client_create(self, name: str, **kwargs):
        self.b3c.create_function(
            FunctionName=name,
            **kwargs,
        )


@dataclass
class GatewayDomain(AWSRec):
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


class GatewayDomains(AWSRecsCRUD):
    client_name: str = 'apigatewayv2'
    rec_cls: type[GatewayDomain] = GatewayDomain

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


@dataclass
class APIMapping(AWSRec):
    ApiId: str
    Stage: str

    @property
    def ident(self):
        # TODO: this should really be ApiId and Stage I believe but the ClientBase api
        # isn't built to use composite keys.  We only use the $default stage right now anyway.
        return self.ApiId


class APIMappings(AWSRecsCRUD):
    client_name: str = 'apigatewayv2'
    rec_cls: type[APIMapping] = APIMapping

    def __init__(self, *args, domain_name, **kwargs):
        super().__init__(*args, **kwargs)
        self.domain_name = domain_name
        self.stage = '$default'

    def client_list(self):
        return self.b3c.get_api_mappings(DomainName=self.domain_name)['Items']

    def client_create(self, api_id: str):
        self.b3c.create_api_mapping(
            DomainName=self.domain_name,
            ApiId=api_id,
            Stage=self.stage,
        )


class Gateway:
    def __init__(
        self,
        config: Config,
        domain_name: str,
        *,
        testing=False,
    ):
        self.config: Config = config
        self.b3_sess = b3_sess = auth.b3_sess(config.aws_region, testing)
        config.apply_sess(b3_sess, testing)

        self.domain_name = domain_name
        self.lambda_arn = config.function_arn
        self.api_name = config.resource_ident

        self.acm_certs = ACMCerts(self.b3_sess)
        self.gw_apis = GatewayAPIs(self.b3_sess)
        self.gw_domains = GatewayDomains(self.b3_sess)
        self.api_mappings = APIMappings(self.b3_sess, domain_name=domain_name)

    def ensure_lambda_permission(self, api_id):
        source_arn = (
            f'arn:aws:execute-api:{self.config.aws_region}:{self.config.aws_acct_id}:{api_id}/*/*'
        )
        try:
            self.b3c_lambda.add_permission(
                FunctionName=self.config.lambda_ident,
                StatementId=f'{self.config.resource_ident}-{api_id}-invoke',
                Action='lambda:InvokeFunction',
                Principal='apigateway.amazonaws.com',
                SourceArn=source_arn,
            )
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceConflictException':
                raise

    def delete(self):
        GatewayAPIs(self.b3_sess).delete(self.config.resource_ident)
        self.cert_delete()

    def provision(self):
        cert: ACMCert = self.acm_certs.ensure(self.domain_name)

        gw_api: GatewayAPI = self.gw_apis.ensure(
            self.config.resource_ident,
            lambda_arn=self.config.function_arn,
        )
        log.info(f'  - Api Endpoint: {gw_api.ApiEndpoint}')
        self.acm_certs.log_dns_validation(self.domain_name)
        return
        self.ensure_lambda_permission(gw_api.ApiId)

        # TODO: if the certificate is not issued (i.e. validated), you can't create the domain
        # yet
        gw_domain: GatewayDomain = self.gw_domains.ensure(
            self.domain_name,
            cert_arn=cert.arn,
        )
        log.info(f'  - Host: {gw_domain.GatewayDomainName}')
        log.info(f'  - Alias: {self.domain_name}')
        log.info(f'  - Status: {gw_domain.Status}')

        self.api_mappings.ensure(gw_api.ApiId)


# Example usage:
# gw = Gateway(domain_name='api.example.com', lambda_function_name='my-func', api_name='my-api')
# gw.deploy()
