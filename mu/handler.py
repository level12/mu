import logging
import os

import awsgi2

import mu.tasks


log = logging.getLogger(__name__)

base64_content_types = {
    'application/octet-stream',
    'image/jpeg',
    'image/png',
    'image/x-icon',
    'application/pdf',
    'application/vnd.ms-fontobject',
    'application/x-font-ttf',
    'font/ttf',
    'application/font-woff',
    'font/woff',
    'font/woff2',
}


class ActionHandler:
    # TODO: create method that will list all possible actions
    wsgi_app = None
    base64_content_types = base64_content_types

    @classmethod
    def on_event(cls, event, context):
        """The entry point for AWS lambda"""
        try:
            keys = set(event.keys())
            wsgi_keys = {'headers', 'requestContext', 'routeKey', 'rawPath'}
            if wsgi_keys.issubset(keys) and cls.wsgi_app:
                return cls.wsgi(event, context)

            if {'task-path', 'args', 'kwargs'}.issubset(keys):
                mu.tasks.call_task(event)
                return 'Called task'

            return cls.on_action('do-action', event, context)
        except Exception as e:
            return cls.handle_exception(e, event, context)

    @classmethod
    def handle_exception(cls, e: Exception, event, context):
        log.exception(
            'ActionHandler.on_event() caught an unhandled exception',
            extra=cls.diagnostics(event, context),
        )
        return 'Internal Server Error'

    @staticmethod
    def ping(event, context):
        return 'pong'

    @staticmethod
    def diagnostics(event, context, error=None):
        try:
            context_data = {
                'aws_request_id': context.aws_request_id,
                'log_group_name': context.log_group_name,
                'log_stream_name': context.log_stream_name,
                'function_name': context.function_name,
                'memory_limit_in_mb': context.memory_limit_in_mb,
                'function_version': context.function_version,
                'invoked_function_arn': context.invoked_function_arn,
                'remaining_time': context.get_remaining_time_in_millis(),
            }
        except AttributeError as e:
            context_data = {'diagnostics attribute error': str(e)}

        return {
            'event': event,
            'context': context_data,
            'error': error,
        }

    @staticmethod
    def environ(event, context):
        return dict(os.environ)

    @staticmethod
    def log_example(event, context):
        try:
            raise Exception()
        except Exception:
            log.exception('This is an exception')
        log.error('This is an error')
        log.warning('This is a warning')
        log.info('This is an info log')
        log.debug('This is a debug log')

        return 'Logs emitted at debug, info, warning, and error levels'

    @classmethod
    def _unknown_action(cls, method_name, event, context):
        msg = f'Method `{method_name}` could not be found on handler class'
        log.error(msg)
        return cls.diagnostics(event, context, msg)

    @classmethod
    def on_action(cls, action_key, event, context):
        action = event.get(action_key)

        log.info(f'ActionHandler invoked with action: {action}')

        if action is None:
            msg = f'Action key "{action_key}" not found in event'
            log.error(msg)
            log.info(event)
            return {
                'event': event,
                'error': msg,
            }

        # Let users specify actions with dashes but be able to map them to method names
        # (underscores).
        action = action.replace('-', '_')
        if action_method := getattr(cls, action, None):
            return action_method(event, context)

        return cls._unknown_action(action, event, context)

    @classmethod
    def wsgi(cls, event, context):
        return awsgi2.response(
            cls.wsgi_app,
            event,
            context,
            base64_content_types=cls.base64_content_types,
        )

    @staticmethod
    def error(event: dict, context: dict):
        raise RuntimeError('ActionHandler.error(): deliberate error for testing purposes')
