from os import environ
import sys


def handler(event, context):
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
        'environ': dict(environ),
        'sys.path': sys.path,
        'message': 'Response from diagnostics.handler()',
    }
