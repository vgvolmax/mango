"""Application-facing MANGO errors."""


class MangoError(Exception):
    pass


class MangoAuthenticationError(MangoError):
    pass


class MangoNetworkError(MangoError):
    pass


class MangoApiError(MangoError):
    pass


class MangoStatisticsTimeout(MangoError):
    pass
