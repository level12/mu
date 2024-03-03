class JukeException(Exception):
    pass


class DeployAppException(Exception):
    pass


class DeployAppConfigMissing(DeployAppException):
    pass
