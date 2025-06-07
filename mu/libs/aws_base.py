from dataclasses import dataclass, fields
import logging
from typing import Self

import boto3

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

    def __init__(self, b3_sess: boto3.Session):
        self.b3_sess = b3_sess
        self.b3c = b3_sess.client(self.client_name)
        self.clear_cache()
        self.rec_kind = self.rec_cls.__name__
        self.log_prefix = self.__class__.__name__

    def clear_cache(self):
        self._list_recs = None

    def get(self, ident: str, wait=False):
        if not wait:
            return self.list().get(ident)

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

    def list(self) -> dict[str, AWSRec]:
        if self._list_recs is None:
            recs: list[dict] = self.client_list()
            self._list_recs = {
                rec.ident: rec for rec in [self.rec_cls.from_aws(rec_d) for rec_d in recs]
            }
        return self._list_recs

    def ensure(self, ident: str, **kwargs):
        if rec := self.get(ident):
            log.info(f'{self.log_prefix} ensure: record existed')
            return rec

        self.clear_cache()
        self.client_create(ident, **kwargs)
        log.info(f'{self.log_prefix} ensure: record created')

        return self.get(ident, wait=self.ensure_get_wait)

    def delete(self, ident: str):
        rec = self.get(ident)
        if not rec:
            return

        self.client_delete(rec)
        log.info(f'{self.log_prefix} delete: record deleted')

        self.clear_cache()
