import io

from mu.config import Config
from mu.libs import auth, aws_recs, concurrent, gateway, lamb, logs


log = logs.logger()


class Status:
    def __init__(self, config: Config):
        self.config = config
        self.b3_sess = auth.b3_sess(config=self.config)

        self.lambda_func: aws_recs.LambdaFunc | None = None
        self.lambda_url: aws_recs.FunctionURLConfig | None = None
        self.gw_api: gateway.GatewayAPI | None = None
        self.acm_cert: gateway.ACMCert | None = None
        self.gw_domain_name: gateway.DomainName | None = None

    @classmethod
    def fetch(cls, config, max_threads: int = 4):
        status = cls(config)

        def method_dispatch(method_name: str):
            getattr(status, method_name)()

        method_names = (
            ('fetch_lambda',),
            ('fetch_gateway_cert',),
            ('fetch_gateway_api',),
            ('fetch_gateway_domain_name',),
        )
        with concurrent.thread_futures(method_dispatch, method_names) as results:
            if exc := concurrent.futures_exc(results):
                raise RuntimeError('Exception in child process or thread') from exc

        return status.results()

    def fetch_lambda(self):
        self.lambda_func = lamb.Functions(self.b3_sess).get(self.config.lambda_ident)
        if self.lambda_func:
            self.lambda_url = lamb.FunctionURLConfigs(self.b3_sess).get(self.config.function_arn)

    def fetch_gateway_api(self):
        if not self.config.domain_name:
            return
        self.gw_api = gateway.GatewayAPIs(self.b3_sess).get(self.config.resource_ident)

    def fetch_gateway_cert(self):
        if not self.config.domain_name:
            return
        self.acm_cert = gateway.ACMCerts(self.b3_sess).get(self.config.domain_name)

    def fetch_gateway_domain_name(self):
        if not self.config.domain_name:
            return
        self.gw_domain_name = gateway.DomainNames(self.b3_sess).get(self.config.domain_name)

    def results(self):
        indent = '   '
        results = io.StringIO()
        results.write(
            'Project:\n'
            f'{indent}{self.config.project_ident}\n'
            'Env:\n'
            f'{indent}{self.config.env}\n'
            'Lambda:\n'
            f'{indent}Name: {self.config.lambda_ident}\n'
            f'{indent}Created: {bool(self.lambda_func)}\n'
            'Lambda URL:\n'
            f'{indent}{self.lambda_url.FunctionUrl if self.lambda_url else None}\n',
        )

        if self.config.domain_name:
            results.write(
                f'Domain:\n{indent}Name:\n{indent * 2}{self.config.domain_name}\n',
            )
            results.write(
                f'{indent}Certificate Status:\n'
                f'{indent * 2}{self.acm_cert.Status if self.acm_cert else None}\n',
            )
            results.write(
                f'{indent}Gateway API URL:\n'
                f'{indent * 2}{self.gw_api.ApiEndpoint if self.gw_api else None}\n',
            )
            results.write(
                f'{indent}Gateway Domain Name:\n'
                f'{indent * 2}{self.gw_domain_name.GatewayDomainName if self.gw_domain_name else None}\n',  # noqa: E501
            )
            results.write(
                f'{indent}Gateway Domain Name Status:\n'
                f'{indent * 2}{self.gw_domain_name.Status if self.gw_domain_name else None}\n',
            )

        else:
            results.write(
                f'Domain:\n{indent}Name: None\n',
            )

        print(self.gw_api)

        return results.getvalue()
