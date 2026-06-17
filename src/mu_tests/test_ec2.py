from unittest import mock

from mu.libs import ec2


@mock.patch('boto3.client')
def test_describe_subnets_handles_untagged_subnets(mock_client):
    mock_client.return_value.describe_subnets.return_value = {
        'Subnets': [
            {
                'SubnetId': 'subnet-untagged',
            },
            {
                'SubnetId': 'subnet-tagged',
                'Tags': [{'Key': 'Name', 'Value': 'nest-dev-private-a'}],
            },
        ],
    }

    result = ec2.describe_subnets(None, name_tag_key='Name')

    assert result == {
        'subnet-untagged': {'SubnetId': 'subnet-untagged'},
        'nest-dev-private-a': {
            'SubnetId': 'subnet-tagged',
            'Tags': [{'Key': 'Name', 'Value': 'nest-dev-private-a'}],
        },
    }
