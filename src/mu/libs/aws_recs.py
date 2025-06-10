from dataclasses import dataclass, fields
import logging
from typing import Self

import boto3
import botocore.config

from . import utils


log = logging.getLogger(__name__)


@dataclass
class AWSRec:
    @classmethod
    def take_fields(cls, data: dict) -> dict:
        field_names = [f.name for f in fields(cls)]
        return utils.take(data, *field_names, strict=False)

    @classmethod
    def from_aws(cls, data: dict) -> Self:
        return cls(**cls.take_fields(data))

    @property
    def ident(self):
        raise NotImplementedError


class AWSRecsCRUD:
    client_name: str
    rec_cls: type[AWSRec]
    ensure_get_wait: bool = False
    # Gateway has stupidly low limits:
    # https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html#api-gateway-control-service-limits-table
    b3_config = botocore.config.Config(retries={'total_max_attempts': 30, 'mode': 'adaptive'})

    def __init__(self, b3_sess: boto3.Session):
        self.b3_sess = b3_sess
        self.b3c = b3_sess.client(self.client_name, config=self.b3_config)
        self.clear_cache()
        self.rec_kind = self.rec_cls.__name__
        self.log_prefix = self.__class__.__name__

    def clear_cache(self):
        self._list_recs = None

    def get(self, ident: str, *list_args, wait=False):
        if not wait:
            return self.list(*list_args).get(ident)

        def clear_and_get():
            self.clear_cache()
            return self.list().get(ident)

        return utils.retry(clear_and_get, waiting_for=f'{self.rec_kind} to be created')

    def client_create(self) -> None:
        raise NotImplementedError

    def client_delete(self) -> None:
        raise NotImplementedError

    def client_list(self) -> list[dict]:
        raise NotImplementedError

    def list(self, *list_args) -> dict[str, AWSRec]:
        if self._list_recs is None:
            recs: list[dict] = self.client_list(*list_args)
            self._list_recs = {
                rec.ident: rec for rec in [self.rec_cls.from_aws(rec_d) for rec_d in recs]
            }
        return self._list_recs

    def ensure(self, ident: str, *list_args, **create_kwargs):
        if rec := self.get(ident, *list_args):
            log.info(f'{self.log_prefix} ensure: record existed')
            return rec

        self.clear_cache()
        self.client_create(ident, **create_kwargs)
        log.info(f'{self.log_prefix} ensure: record created')

        return self.get(ident, *list_args, wait=self.ensure_get_wait)

    def delete(self, ident: str, *list_args):
        rec = self.get(ident, *list_args)
        if not rec:
            return

        self.client_delete(rec, *list_args)
        log.info(f'{self.log_prefix} delete: record deleted')

        self.clear_cache()
