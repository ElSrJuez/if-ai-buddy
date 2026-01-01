"""SD-Server client for scene image generation."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from module import my_config, my_logging


@dataclass
class ImageGenerationRequest:
    """Request payload for SD server image generation."""
    
    prompt: str
    size: str
    steps: int
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to SD server request format with embedded parameters."""
        # Embed steps parameter in prompt
        embedded_json = json.dumps({"steps": self.steps})
        final_prompt = f"{self.prompt} <sd_cpp_extra_args>{embedded_json}</sd_cpp_extra_args>"
            
        return {
            "prompt": final_prompt,
            "size": self.size,
            "output_format": "png",
            "n": 1
        }


@dataclass 
class ImageGenerationResponse:
    """Response from SD server image generation."""
    
    image_data: bytes
    created: str
    prompt_used: str
    size: str
    steps: int
    
    @classmethod
    def from_api_response(cls, response_data: dict[str, Any], original_request: ImageGenerationRequest) -> ImageGenerationResponse:
        """Parse SD server API response into our response object."""
        if "data" not in response_data or not response_data["data"]:
            raise SDServerError("No image data in response", status_code=500)
            
        image_b64 = response_data["data"][0]["b64_json"]
        image_data = base64.b64decode(image_b64)
        
        # Clean prompt (remove XML tags for storage)
        clean_prompt = original_request.prompt.split(" <sd_cpp_extra_args>")[0]
        
        return cls(
            image_data=image_data,
            created=response_data["created"],
            prompt_used=clean_prompt,
            size=original_request.size,
            steps=original_request.steps
        )


class SDServerError(Exception):
    """Raised when SD server responds with an error."""
    
    def __init__(self, message: str, *, status_code: int, endpoint: str = "/v1/images/generations") -> None:
        super().__init__(f"SD Server {endpoint} -> {status_code}: {message}")
        self.status_code = status_code
        self.endpoint = endpoint
        self.message = message


class SDServerClient:
    """Async client for SD server image generation API."""
    
    def __init__(self) -> None:
        """Initialize with configuration from scene image config."""
        self._config = my_config.load_scene_image_config()
        self._base_url = self._config.get("sd_server_base_url")
        self._timeout = self._config.get("sd_server_timeout")
        
        if not self._base_url:
            raise ValueError("sd_server_base_url not configured")
        if not self._timeout:
            raise ValueError("sd_server_timeout not configured")
            
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout, connect=30.0),  # Total timeout, 30s connect
            headers={"Content-Type": "application/json"}
        )
        
        my_logging.system_info(f"SDServerClient initialized: {self._base_url} (timeout: {self._timeout}s)")
    
    async def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResponse:
        """Generate an image using the SD server API."""
        endpoint = "/v1/images/generations"
        url = f"{self._base_url.rstrip('/')}{endpoint}"
        
        payload = request.to_dict()
        
        my_logging.system_debug(f"SD server request: {url} with prompt length {len(request.prompt)}")
        
        try:
            response = await self._client.post(url, json=payload)
            
            # Handle error responses
            if response.status_code >= 400:
                error_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
                error_msg = error_data.get("error", f"HTTP {response.status_code}")
                raise SDServerError(error_msg, status_code=response.status_code)
            
            # Parse successful response
            response_data = response.json()
            result = ImageGenerationResponse.from_api_response(response_data, request)
            
            my_logging.system_info(f"SD server generated image: {len(result.image_data)} bytes, {result.size}")
            return result
            
        except httpx.TimeoutException as exc:
            my_logging.system_log(f"SD server timeout after {self._timeout}s: {exc}")
            raise SDServerError(f"Request timed out after {self._timeout} seconds", status_code=0) from exc
        except httpx.ConnectError as exc:
            my_logging.system_log(f"SD server connection error: {exc}")
            raise SDServerError(f"Cannot connect to SD server: {exc}", status_code=0) from exc
        except httpx.HTTPError as exc:
            my_logging.system_log(f"SD server network error: {exc}")
            raise SDServerError(f"Network error: {exc}", status_code=0) from exc
        except json.JSONDecodeError as exc:
            my_logging.system_log(f"SD server JSON decode error: {exc}")
            raise SDServerError(f"Invalid JSON response: {exc}", status_code=response.status_code) from exc