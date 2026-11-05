from unittest import mock

import pytest

from mu.libs import ec2


def b3_sess():
    sess = mock.MagicMock()
    sess.client.return_value.describe_subnets.return_value = {
        'Subnets': [
            {
                'SubnetId': 'subnet-untagged',
            },
            {
                'SubnetId': 'subnet-tagged',
                'Tags': [{'Key': 'Name', 'Value': 'subnet-tagged'}],
            },
        ],
    }
    return sess


def test_describe_subnets_handles_untagged_subnets():
    sess = b3_sess()
    result = ec2.describe_subnets(sess, name_tag_key='Name')

    sess.client.assert_called_once_with('ec2')
    assert result == {
        'subnet-untagged': {'SubnetId': 'subnet-untagged'},
        'subnet-tagged': {
            'SubnetId': 'subnet-tagged',
            'Tags': [{'Key': 'Name', 'Value': 'subnet-tagged'}],
        },
    }


def test_subnet_ids():
    assert ec2.subnet_ids(b3_sess(), ['subnet-tagged'], 'Name') == ['subnet-tagged']

    with pytest.raises(ValueError, match='Subnets not found .+: subnet-missing'):
        ec2.subnet_ids(b3_sess(), ['subnet-tagged', 'subnet-missing'], 'Name')
