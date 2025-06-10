import concurrent.futures as cf
from contextlib import contextmanager
from dataclasses import dataclass
import typing

from mu.libs import logs


log = logs.logger()


@dataclass
class FutureResult:
    """Result of concurrent.Futures execution"""

    # Unique identifiying object for this record that the calling code can use to handle the result.
    ident: typing.Any
    # rec: record returned by future.result().  None if an exception occured.
    rec: typing.Any | None = None
    # exception raised by future.result()
    exc: Exception | None = None


@contextmanager
def thread_futures(
    call: typing.Callable,
    call_with: dict,
    *,
    max_workers: int = 5,
    initializer=None,
):
    """
    Use concurrent.futures with the process pool executor and enhancements to result processing
    and error handling.
    """
    yield _futures_process(cf.ThreadPoolExecutor, call, call_with, max_workers, initializer)


def _futures_process(
    exec_cls: cf.ThreadPoolExecutor | cf.ProcessPoolExecutor,
    call: typing.Callable,
    call_with: dict,
    max_workers: int,
    initializer: typing.Callable | None,
):
    exc = None
    cpe = exec_cls(max_workers=max_workers, initializer=initializer)
    with cpe as executor:
        if not isinstance(call_with, dict):
            call_with = {str(args): args for args in call_with}

        futures = {executor.submit(call, *args): ident for ident, args in call_with.items()}

        try:
            for future in cf.as_completed(futures):
                ident = futures[future]
                try:
                    yield FutureResult(ident, future.result())
                except Exception as e:
                    exc = e
                    log.error(
                        '\n   >>>>   Unhandled exception detected, cancelling futures..',
                    )
                    for to_cancel in futures:
                        if not to_cancel.done():
                            to_cancel.cancel()
                    break
        except KeyboardInterrupt:
            log.info(
                '\n   >>>>   KeyboardInterrupt detected, cancelling pending futures.'
                '\n          Running futures will continue until complete...',
            )
            for to_cancel in futures:
                if not to_cancel.done():
                    to_cancel.cancel()
    if exc:
        yield FutureResult(ident, exc=exc)


def futures_exc(results: typing.Iterable[FutureResult]) -> Exception | None:
    """
    Combine with futures context managers to only handle exceptions in the results.

    Use when processing return values don't matter but you do want to handle an error as it
    occures.  Example:

        with thread_futures(some_callable, some_list) as results:
            if exc := futures_exc(results):
                raise RuntimeError('Exception in child process or thread') from exc
    """
    for result in results:
        if result.exc:
            return result.exc
