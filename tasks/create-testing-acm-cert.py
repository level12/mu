#!/usr/bin/env python
# mise description="Create ACM cert used by integration tests"

from pprint import pprint

import click

from mu.libs import gateway, logs, testing


log = logs.logger()


@click.command()
@logs.click_options
def main(log_level: str):
    logs.init_logging(log_level)

    b3_sess = testing.b3_sess(kind='mu-testing-live')
    certs = gateway.ACMCerts(b3_sess)
    cert: gateway.ACMCert = certs.ensure(testing.PERSISTENT_CERT_DOMAIN)
    certs.log_dns_validation(testing.PERSISTENT_CERT_DOMAIN)

    if cert.Status in ('PENDING_VALIDATION', 'ISSUED'):
        log.info(f'Cert status: {cert.Status}')
        return

    pprint(certs.client_describe(cert))


if __name__ == '__main__':
    main()
