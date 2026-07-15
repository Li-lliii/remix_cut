from __future__ import annotations

import json

import httpx

from platform_app.services.algorithm_errors import (
    AlgorithmServiceBusyError,
    AlgorithmServiceNotReadyError,
    AlgorithmServiceProtocolError,
    AlgorithmServiceRequestError,
    AlgorithmServiceTimeoutError,
)


class AlgorithmHttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        service_name: str,
        connect_timeout_sec: float = 10.0,
        read_timeout_sec: float = 600.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.service_name = service_name
        self.transport = transport
        self.timeout = httpx.Timeout(
            connect=connect_timeout_sec,
            read=read_timeout_sec,
            write=read_timeout_sec,
            pool=read_timeout_sec,
        )

    def post_json(self, path: str, *, json: dict) -> dict:
        return self._request_json("POST", path, json=json)

    def get_json(self, path: str, *, params: dict | None = None) -> dict:
        return self._request_json("GET", path, params=params)

    def _request_json(self, method: str, path: str, **kwargs) -> dict:
        url = f"{self.base_url}{path}"
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport, trust_env=False) as client:
                response = client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise AlgorithmServiceTimeoutError(f"{self.service_name} 服务请求超时: {exc}") from exc
        except httpx.HTTPError as exc:
            raise AlgorithmServiceRequestError(f"{self.service_name} 服务请求失败: {exc}") from exc

        payload = self._decode_json(response)
        if response.status_code >= 400:
            self._raise_service_error(payload)
        if not isinstance(payload, dict):
            raise AlgorithmServiceProtocolError(f"{self.service_name} 服务返回结构异常: 顶层不是对象")
        return payload

    def _decode_json(self, response: httpx.Response):
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise AlgorithmServiceProtocolError(
                f"{self.service_name} 服务返回结构异常: 非 JSON 响应"
            ) from exc

    def _raise_service_error(self, payload):
        if not isinstance(payload, dict):
            raise AlgorithmServiceProtocolError(f"{self.service_name} 服务返回结构异常: 错误响应不是对象")
        detail = payload.get("detail")
        nested_message = None
        if isinstance(detail, dict):
            nested_message = detail.get("error") or detail.get("message")
        elif isinstance(detail, str):
            nested_message = detail
        message = str(payload.get("error") or payload.get("message") or nested_message or "未知错误")
        normalized = message.strip().lower()
        if normalized == "service busy":
            raise AlgorithmServiceBusyError(f"{self.service_name} 服务繁忙: {message}")
        if normalized == "not ready":
            raise AlgorithmServiceNotReadyError(f"{self.service_name} 服务未就绪: {message}")
        raise AlgorithmServiceRequestError(f"{self.service_name} 服务请求失败: {message}")
