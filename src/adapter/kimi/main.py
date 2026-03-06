"""Kimi Adapter - OpenAI-compatible FastAPI wrapper for Kimi Coding API.

Provides an OpenAI-compatible API that forwards requests to Kimi Coding API.
This allows using Kimi models with tools that expect OpenAI-compatible endpoints.

For ST-KIMI-ADAPTER-001: Kimi Adapter Wiring
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Kimi Adapter",
    description="OpenAI-compatible adapter for Kimi Coding API",
    version="1.0.0",
)


# Configuration from environment
KIMI_API_KEY = os.getenv("KIMI_API_KEY")
KIMI_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")


# Request/Response Models
class ChatMessage(BaseModel):
    """A message in the chat format."""

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model: str = KIMI_MODEL
    messages: list[ChatMessage]
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2048, ge=1)
    stream: bool = False
    stop: str | list[str] | None = None
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)


class Choice(BaseModel):
    """A choice in the chat completion response."""

    index: int
    message: ChatMessage
    finish_reason: str | None = None


class Usage(BaseModel):
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: Usage


class ModelInfo(BaseModel):
    """Model information for /models endpoint."""

    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelsResponse(BaseModel):
    """Response for /models endpoint."""

    object: str = "list"
    data: list[ModelInfo]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    kimi_base_url: str
    kimi_model: str


# Error response model
class ErrorDetail(BaseModel):
    """Error detail for API errors."""

    message: str
    type: str
    param: str | None = None
    code: str | None = None


class ErrorResponse(BaseModel):
    """OpenAI-compatible error response."""

    error: ErrorDetail


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns the adapter status and configuration.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        kimi_base_url=KIMI_BASE_URL,
        kimi_model=KIMI_MODEL,
    )


@app.get("/v1/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """List available models (OpenAI-compatible).

    Returns a list of models available through this adapter.
    """
    return ModelsResponse(
        data=[
            ModelInfo(
                id=KIMI_MODEL,
                created=int(time.time()),
                owned_by="kimi",
            )
        ]
    )


async def _forward_to_kimi(request: ChatCompletionRequest) -> dict[str, Any]:
    """Forward request to Kimi Coding API.

    Args:
        request: OpenAI-compatible chat completion request

    Returns:
        Kimi API response as dictionary

    Raises:
        HTTPException: If the request fails
    """
    import aiohttp

    if not KIMI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "KIMI_API_KEY not configured",
                    "type": "auth_error",
                    "code": "api_key_missing",
                }
            },
        )

    # Build Kimi API request payload
    messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

    payload = {
        "model": request.model,
        "messages": messages,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stream": request.stream,
    }

    # Add optional parameters if provided
    if request.stop:
        payload["stop"] = request.stop
    if request.presence_penalty != 0.0:
        payload["presence_penalty"] = request.presence_penalty
    if request.frequency_penalty != 0.0:
        payload["frequency_penalty"] = request.frequency_penalty

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {KIMI_API_KEY}",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{KIMI_BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                response_data = await response.json()

                # Map Kimi API errors to HTTP status codes
                if response.status == 401:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail={
                            "error": {
                                "message": "Invalid API key",
                                "type": "authentication_error",
                                "code": "invalid_api_key",
                            }
                        },
                    )
                elif response.status == 403:
                    error_msg = response_data.get("error", {}).get(
                        "message", "Permission denied"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail={
                            "error": {
                                "message": error_msg,
                                "type": "permission_error",
                                "code": "permission_denied",
                            }
                        },
                    )
                elif response.status == 429:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail={
                            "error": {
                                "message": "Rate limit exceeded",
                                "type": "rate_limit_error",
                                "code": "rate_limit_exceeded",
                            }
                        },
                    )
                elif response.status >= 500:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail={
                            "error": {
                                "message": f"Kimi API server error: {response.status}",
                                "type": "server_error",
                                "code": "server_error",
                            }
                        },
                    )
                elif response.status != 200:
                    error_msg = response_data.get("error", {}).get(
                        "message", f"HTTP {response.status}"
                    )
                    raise HTTPException(
                        status_code=response.status,
                        detail={
                            "error": {
                                "message": error_msg,
                                "type": "api_error",
                                "code": "api_error",
                            }
                        },
                    )

                return response_data

    except aiohttp.ClientError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": {
                    "message": f"Failed to connect to Kimi API: {str(e)}",
                    "type": "connection_error",
                    "code": "connection_error",
                }
            },
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "message": f"Internal error: {str(e)}",
                    "type": "internal_error",
                    "code": "internal_error",
                }
            },
        ) from e


def _map_kimi_response_to_openai(
    kimi_response: dict[str, Any],
) -> ChatCompletionResponse:
    """Map Kimi API response to OpenAI-compatible format.

    Args:
        kimi_response: Raw response from Kimi API

    Returns:
        OpenAI-compatible chat completion response
    """
    choices = []
    for i, choice in enumerate(kimi_response.get("choices", [])):
        message = choice.get("message", {})
        choices.append(
            Choice(
                index=i,
                message=ChatMessage(
                    role=message.get("role", "assistant"),
                    content=message.get("content", ""),
                ),
                finish_reason=choice.get("finish_reason"),
            )
        )

    usage_data = kimi_response.get("usage", {})
    usage = Usage(
        prompt_tokens=usage_data.get("prompt_tokens", 0),
        completion_tokens=usage_data.get("completion_tokens", 0),
        total_tokens=usage_data.get("total_tokens", 0),
    )

    return ChatCompletionResponse(
        id=kimi_response.get("id", f"chatcmpl-{uuid.uuid4().hex[:12]}"),
        created=kimi_response.get("created", int(time.time())),
        model=kimi_response.get("model", KIMI_MODEL),
        choices=choices,
        usage=usage,
    )


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """OpenAI-compatible chat completions endpoint.

    Forwards the request to Kimi Coding API and returns an OpenAI-compatible response.

    Args:
        request: Chat completion request in OpenAI format

    Returns:
        Chat completion response in OpenAI format
    """
    # Forward to Kimi API
    kimi_response = await _forward_to_kimi(request)

    # Map to OpenAI format
    return _map_kimi_response_to_openai(kimi_response)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions with OpenAI-compatible error format."""
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
        )

    # Default error format
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": str(exc.detail),
                "type": "api_error",
                "code": f"http_{exc.status_code}",
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": f"Internal server error: {str(exc)}",
                "type": "internal_error",
                "code": "internal_error",
            }
        },
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("KIMI_ADAPTER_PORT", "8002"))
    host = os.getenv("KIMI_ADAPTER_HOST", "0.0.0.0")

    uvicorn.run(app, host=host, port=port)
