import logging
import os

import awsgi2


log = logging.getLogger(__name__)


class ActionHandler:
    # TODO: create method that will list all possible actions
    wsgi_app = None

    @classmethod
    def on_event(cls, event, context):
        """The entry point for AWS lambda"""

        keys = set(event.keys())
        wsgi_keys = {'headers', 'requestContext', 'routeKey', 'rawPath'}
        if cls.wsgi_app and wsgi_keys.issubset(keys):
            return cls.wsgi(event, context)

        return cls.on_action('do-action', event, context)

    @staticmethod
    def ping(event, context):
        return 'pong'

    @staticmethod
    def diagnostics(event, context, error=None):
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

        log.info(f'Handler invoked with action: {action}')

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
        return awsgi2.response(cls.wsgi_app, event, context, base64_content_types={'image/png'})

    @staticmethod
    def error(event: dict, context: dict):
        raise RuntimeError('ActionHandler.error(): deliberate error for testing purposes')
