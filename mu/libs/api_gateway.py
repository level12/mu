from dataclasses import asdict, dataclass
from datetime import datetime
import logging
import pprint

import boto3
from methodtools import lru_cache


log = logging.getLogger(__name__)


@dataclass
class APIEndpoint:
    api_endpoint: str
    api_id: str
    api_key_selection_expression: str
    created_date: datetime
    disable_execute_api_endpoint: bool
    name: str
    protocol_type: str
    route_selection_expression: str

    @classmethod
    def from_dict(cls, data: dict):
        return cls(
            api_endpoint=data['ApiEndpoint'],
            api_id=data['ApiId'],
            api_key_selection_expression=data['ApiKeySelectionExpression'],
            created_date=data['CreatedDate'],
            disable_execute_api_endpoint=data['DisableExecuteApiEndpoint'],
            name=data['Name'],
            protocol_type=data['ProtocolType'],
            route_selection_expression=data['RouteSelectionExpression'],
        )

    def __str__(self):
        return pprint.pformat(asdict(self))

    def delete(self, agc):
        agc.delete_api(ApiId=self.api_id)


class APIs:
    def __init__(self, b3_sess: boto3.Session):
        self.b3_sess = b3_sess
        self.agc = b3_sess.client('apigatewayv2')

    def clear(self):
        self.list.cache_clear()

    @lru_cache()
    def list(self, name=None) -> list[APIEndpoint]:
        # TODO: pager
        items = self.agc.get_apis()['Items']
        return [
            APIEndpoint.from_dict(item) for item in items if name is None or item['Name'] == name
        ]

    def delete(self, *names):
        ag: APIEndpoint
        for ag in self.list():
            if ag.name in names:
                ag.delete(self.agc)
                log.info('API resource deleted: %s %s', ag.api_id, ag.name)

        self.clear()

    def ensure(self, api_name: str, func_arn: str):
        agc = self.b3_sess.client('apigatewayv2')
        apis = self.list(api_name)
        if len(apis) > 1:
            raise RuntimeError(f'More than one api exists with name: {api_name}')

        api: APIEndpoint = apis[0] if apis else 0

        if apis:
            log.info('API resource existed')
            return api

        api_response = agc.create_api(
            Name=api_name,
            ProtocolType='HTTP',
            Target=func_arn,
        )
        api = APIEndpoint.from_dict(api_response)

        log.info('API resource created')
        return api
