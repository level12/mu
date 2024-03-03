import boto3


def acct_name(account_id: str):
    # Assuming this script is run with credentials that have access to the organization details
    org_client = boto3.client('organizations')

    for account in org_client.list_accounts()['Accounts']:
        if account['Id'] == account_id:
            return account['Name']

    return 'Account not found in organization.'
