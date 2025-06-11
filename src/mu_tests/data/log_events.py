platform_report = {
    'timestamp': 1718645035826,
    'message': '{"time":"2024-06-17T17:23:55.826Z","type":"platform.report","record":{"requestId":"40f6c622-67a3-4159-97f2-ce364a0cb7a8","metrics":{"durationMs":18.593,"billedDurationMs":19,"memorySizeMB":2048,"maxMemoryUsedMB":246},"status":"success"}}',
    'ingestionTime': 1718645040852,
}
platform_start = {
    'timestamp': 1718645035902,
    'message': '{"time":"2024-06-17T17:23:55.902Z","type":"platform.start","record":{"requestId":"ca52c236-a38d-40fc-aa6b-7e3be2b7aa55","version":"$LATEST"}}',
    'ingestionTime': 1718645040852,
}
unhandled_exc = {
    'timestamp': 1718645035919,
    'message': 'LAMBDA_WARNING: Unhandled exception. The most likely cause is an issue in the function code. However, in rare cases, a Lambda runtime update can cause unexpected function behavior. For functions using managed runtimes, runtime updates can be triggered by a function change, or can be applied automatically. To determine if the runtime has been updated, check the runtime version in the INIT_START log entry. If this error correlates with a change in the runtime version, you may be able to mitigate this error by temporarily rolling back to the previous runtime version. For more information, see https://docs.aws.amazon.com/lambda/latest/dg/runtimes-update.html\r{"timestamp": "2024-06-17T17:23:55Z", "log_level": "ERROR", "errorMessage": "\'utf-8\' codec can\'t decode byte 0x80 in position 7: invalid start byte", "errorType": "UnicodeDecodeError", "requestId": "ca52c236-a38d-40fc-aa6b-7e3be2b7aa55", "stackTrace": ["  File \\"/var/lang/lib/python3.12/site-packages/mu/handler.py\\", line 21, in on_event\\n    return cls.wsgi(event, context)\\n", "  File \\"/var/lang/lib/python3.12/site-packages/mu/handler.py\\", line 92, in wsgi\\n    return awsgi2.response(cls.wsgi_app, event, context, base64_content_types={\'image/png\'})\\n", "  File \\"/var/lang/lib/python3.12/site-packages/awsgi2/wrapper.py\\", line 27, in response\\n    return instance.response(output)\\n", "  File \\"/var/lang/lib/python3.12/site-packages/awsgi2/impl.py\\", line 18, in response\\n    resp = cast(Dict[str, Union[bool, str, int, Mapping[str, str]]], super().response(output))\\n", "  File \\"/var/lang/lib/python3.12/site-packages/awsgi2/base.py\\", line 104, in response\\n    resp.update(self.build_body(headers, output))\\n", "  File \\"/var/lang/lib/python3.12/site-packages/awsgi2/base.py\\", line 90, in build_body\\n    converted_output = ensure_str(full_body)\\n", "  File \\"/var/lang/lib/python3.12/site-packages/libadvian/binpackers.py\\", line 35, in ensure_str\\n    return instr.decode(\\"utf-8\\")\\n"]}\n',
    'ingestionTime': 1718645040852,
}


text_message = {
    'timestamp': 1718645044734,
    'message': "/var/lang/lib/python3.12/site-packages/webassets/filter/__init__.py:42: SyntaxWarning: invalid escape sequence '\\,'\n",
    'ingestionTime': 1718645053812,
}


platform_init_report = {
    'timestamp': 1718646486348,
    'message': '{"time":"2024-06-17T17:48:06.348Z","type":"platform.initReport","record":{"initializationType":"on-demand","phase":"init","status":"timeout","metrics":{"durationMs":10000.487}}}',
    'ingestionTime': 1718646486433,
}


exc_extras = {
    'timestamp': 1718676426000,
    'message': '{"timestamp": "2024-06-18T02:07:06Z", "level": "ERROR", "message": "had an error", "logger": "climate.aws", "stackTrace": ["  File \\"/app/climate/aws.py\\", line 128, in log_json\\n    raise Exception(\'with some text\')\\n"], "errorType": "Exception", "errorMessage": "with some text", "requestId": "b16742c9-fc88-48cd-b49a-da83582e3929", "location": "/app/climate/aws.py:log_json:130", "event": {"do-action": "log-json", "action-args": []}, "context": {"aws_request_id": "b16742c9-fc88-48cd-b49a-da83582e3929", "log_group_name": "/aws/lambda/stax-residuals-func-rsyringmeld", "log_stream_name": "2024/06/18/[$LATEST]227e6c26d73f4f61a661350d72d3e7e9", "function_name": "stax-residuals-func-rsyringmeld", "memory_limit_in_mb": "2048", "function_version": "$LATEST", "invoked_function_arn": "arn:aws:lambda:us-east-2:637423305257:function:stax-residuals-func-rsyringmeld", "remaining_time": 51486}}\n',
    'ingestionTime': 1718676435252,
}
