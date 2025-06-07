import datetime as dt

from dateutil.tz import tzlocal


def cert_summary(*, arn='arn:mu-test-cert-arn', domain='app.example.com'):
    return {
        'CertificateArn': arn,
        'DomainName': domain,
        'SubjectAlternativeNameSummaries': [domain],
        'HasAdditionalSubjectAlternativeNames': False,
        'Status': 'PENDING_VALIDATION',
        'Type': 'AMAZON_ISSUED',
        'KeyAlgorithm': 'RSA-2048',
        'KeyUsages': [],
        'ExtendedKeyUsages': [],
        'InUse': False,
        'RenewalEligibility': 'INELIGIBLE',
        # This time format matches what the boto3 API returns
        'CreatedAt': dt.datetime.now(tzlocal()),
    }


def cert_describe(*, arn='arn:mu-test-cert-desc', domain='app.example.com'):
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
        'Status': 'PENDING_VALIDATION',
        'KeyAlgorithm': 'RSA-2048',
        'SignatureAlgorithm': 'SHA256WITHRSA',
        'InUseBy': [],
        'Type': 'AMAZON_ISSUED',
        'KeyUsages': [],
        'ExtendedKeyUsages': [],
        'RenewalEligibility': 'INELIGIBLE',
        'Options': {'CertificateTransparencyLoggingPreference': 'ENABLED'},
    }


def cert_describe_minimal(arn='arn:mu-test-cert-desc-min'):
    """The API returns this minimal record shortly after the cert gets created until the fuller
    record becomes available"""

    return {
        'CertificateArn': arn,
        'Issuer': 'Amazon',
        # This time format matches what the boto3 API returns
        'CreatedAt': dt.datetime.now(tzlocal()),
        'Status': 'PENDING_VALIDATION',
        'InUseBy': [],
        'Type': 'AMAZON_ISSUED',
        'RenewalEligibility': 'INELIGIBLE',
        'Options': {'CertificateTransparencyLoggingPreference': 'ENABLED'},
    }


def gateway_api(name='greek-mu-lambda-func-qa'):
    return {
        'ApiEndpoint': 'https://cnstryckkl.execute-api.us-east-2.amazonaws.com',
        'ApiId': 'fake-api-id',
        'ApiKeySelectionExpression': '$request.header.x-api-key',
        # This time format matches what the boto3 API returns
        'CreatedAt': dt.datetime.now(tzlocal()),
        'DisableExecuteApiEndpoint': False,
        'Name': name,
        'ProtocolType': 'HTTP',
        'RouteSelectionExpression': '$request.method $request.path',
        'Tags': {},
    }
