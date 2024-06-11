import mu


class ActionHandler(mu.ActionHandler):
    """mu.ActionHandler is a helper to handle the events that trigger your lambda.

    It's designed to map "actions" to the methods on this handler.  Calling `mu invoke hello` would
    cause lambda to execute this hello method.  Actions are also used when defining recurring
    events in the mu config file.

    See the parent class for actions that have been provided.
    """

    @staticmethod
    def hello(event, context):
        return 'Hello from mu_hello'
