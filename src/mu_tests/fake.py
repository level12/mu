import datetime as dt

from dateutil.tz import tzlocal


def cert_summary(
    *,
    arn='arn:mu-test-cert-arn',
    domain='app.example.com',
    status='PENDING_VALIDATION',
):
    return {
        'CertificateArn': arn,
        'DomainName': domain,
        'SubjectAlternativeNameSummaries': [domain],
        'HasAdditionalSubjectAlternativeNames': False,
        'Status': status,
        'Type': 'AMAZON_ISSUED',
        'KeyAlgorithm': 'RSA-2048',
        'KeyUsages': [],
        'ExtendedKeyUsages': [],
        'InUse': False,
        'RenewalEligibility': 'INELIGIBLE',
        # This time format matches what the boto3 API returns
        'CreatedAt': dt.datetime.now(tzlocal()),
    }


def cert_describe(
    *,
    arn='arn:mu-test-cert-desc',
    domain='app.example.com',
    status='PENDING_VALIDATION',
):
    return {
        'CertificateArn': arn,
        'DomainName': domain,
        'SubjectAlternativeNameSummaries': [domain],
        # NOTE: this key isn't always present, especially right after the domain is created.
        'DomainValidationOptions': [
            {
                'DomainName': domain,
                'ValidationDomain': domain,
                'ValidationStatus': 'PENDING_VALIDATION',
                'ResourceRecord': {
                    'Name': f'_abcfake.{domain}.',
                    'Type': 'CNAME',
                    'Value': '_defake.acm-validations.aws.',
                },
                'ValidationMethod': 'DNS',
            },
        ],
        'Subject': f'CN={domain}',
        'Issuer': 'Amazon',
        # This time format matches what the boto3 API returns
        'CreatedAt': dt.datetime.now(tzlocal()),
        'Status': status,
        'KeyAlgorithm': 'RSA-2048',
        'SignatureAlgorithm': 'SHA256WITHRSA',
        'InUseBy': [],
        'Type': 'AMAZON_ISSUED',
        'KeyUsages': [],
        'ExtendedKeyUsages': [],
        'RenewalEligibility': 'INELIGIBLE',
        'Options': {'CertificateTransparencyLoggingPreference': 'ENABLED'},
    }


def cert_describe_minimal(arn='arn:mu-test-cert-desc-min', status='PENDING_VALIDATION'):
    """The API returns this minimal record shortly after the cert gets created until the fuller
    record becomes available"""

    return {
        'CertificateArn': arn,
        'Issuer': 'Amazon',
        # This time format matches what the boto3 API returns
        'CreatedAt': dt.datetime.now(tzlocal()),
        'Status': status,
        'InUseBy': [],
        'Type': 'AMAZON_ISSUED',
        'RenewalEligibility': 'INELIGIBLE',
        'Options': {'CertificateTransparencyLoggingPreference': 'ENABLED'},
    }


def gateway_api(name='greek-mu-lambda-func-qa', api_id='fake-api-id'):
    return {
        'ApiEndpoint': 'https://cnstryckkl.execute-api.us-east-2.amazonaws.com',
        'ApiId': api_id,
        'ApiKeySelectionExpression': '$request.header.x-api-key',
        # This time format matches what the boto3 API returns
        'CreatedAt': dt.datetime.now(tzlocal()),
        'DisableExecuteApiEndpoint': False,
        'Name': name,
        'ProtocolType': 'HTTP',
        'RouteSelectionExpression': '$request.method $request.path',
        'Tags': {},
    }


def gateway_api_mapping(api_id='fake-api-id', api_map_id='fake-api-map-id'):
    return {
        'ApiId': api_id,
        'ApiMappingId': api_map_id,
        'ApiMappingKey': '',
        'Stage': '$default',
    }


def domain_name(name='app.example.com'):
    return {
        'ApiMappingSelectionExpression': '$request.basepath',
        'DomainName': name,
        'DomainNameConfigurations': [
            {
                'ApiGatewayDomainName': 'd-bbddxy8sl8.execute-api.us-east-2.amazonaws.com',
                'CertificateArn': 'arn:aws:acm:us-east-2:429829037495:certificate/26399e1b-5d13-46b6-b4e8-399261a9fff0',  # noqa: E501
                'DomainNameStatus': 'AVAILABLE',
                'EndpointType': 'REGIONAL',
                'HostedZoneId': 'ZOJJZC49E0EPZ',
                'SecurityPolicy': 'TLS_1_2',
            },
        ],
    }
