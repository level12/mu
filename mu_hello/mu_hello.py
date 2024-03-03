from mu.libs import handler


def lambda_entry(event, context):
    return ActionHandler.on_action('do-action', event, context)


class ActionHandler(handler.ActionHandler):
    @staticmethod
    def hello(event, context):
        return 'Hello from mu_hello'
