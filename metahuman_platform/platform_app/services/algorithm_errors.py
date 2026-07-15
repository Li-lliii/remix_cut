class AlgorithmServiceError(RuntimeError):
    """算法服务调用失败基类。"""


class AlgorithmServiceRequestError(AlgorithmServiceError):
    """算法服务不可达。"""


class AlgorithmServiceTimeoutError(AlgorithmServiceError):
    """算法服务超时。"""


class AlgorithmServiceProtocolError(AlgorithmServiceError):
    """算法服务返回结构异常。"""


class AlgorithmServiceBusyError(AlgorithmServiceError):
    """算法服务繁忙。"""


class AlgorithmServiceNotReadyError(AlgorithmServiceError):
    """算法服务未就绪。"""
