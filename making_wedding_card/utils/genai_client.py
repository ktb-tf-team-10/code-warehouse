"""
Google GenAI 클라이언트 유틸리티

SSL 인증서 오류 해결을 위한 설정 포함
"""

import json
import os
import ssl
from functools import lru_cache
from typing import Any, Dict

from google import genai


class MissingGeminiKeyError(RuntimeError):
    """Raised when GEMINI_API_KEY is not configured."""


def _get_api_key() -> str:
    """환경 변수에서 Gemini API 키를 가져옵니다."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise MissingGeminiKeyError(
            "GEMINI_API_KEY 환경 변수가 설정되어 있지 않습니다. .env 파일을 확인하세요."
        )
    return api_key


@lru_cache(maxsize=1)
def _build_client(api_key: str) -> genai.Client:
    """
    Google GenAI 클라이언트를 생성합니다.

    SSL 인증서 검증 우회 설정 포함 (개발 환경용)
    """
    import certifi
    import os
    import ssl

    # 1. SSL 검증 완전히 무시 설정 (사용자 요청: verify=False 방식의 전역 적용)
    # macOS 및 특정 환경에서 SSL 오류를 방지하기 위해 검증을 비활성화합니다.
    try:
        if not os.environ.get('PYTHONHTTPSVERIFY', ''):
            os.environ['PYTHONHTTPSVERIFY'] = '0'
        ssl._create_default_https_context = ssl._create_unverified_context
    except Exception:
        pass

    # 2. 인증서 경로 설정
    cert_path = certifi.where()
    os.environ['SSL_CERT_FILE'] = cert_path
    os.environ['REQUESTS_CA_BUNDLE'] = cert_path
    os.environ['GRPC_DEFAULT_SSL_ROOTS_FILE_PATH'] = cert_path
    
    print(f"🔧 Gemini Client initializing (SSL Verification Disabled)")

    # 3. HTTP 클라이언트 설정
    # v1alpha에서 일부 모델(imagen-3.0-generate-002 등)이 404가 발생할 수 있어
    # 더 넓은 모델 범위를 지원하는 v1beta 또는 기본 설정을 고려합니다.
    # gemini-2.0-flash-exp의 responseMimeType 등을 위해 v1beta를 사용합니다.
    http_options = {
        "api_version": "v1beta", 
    }

    return genai.Client(
        api_key=api_key,
        http_options=http_options
    )


def get_genai_client() -> genai.Client:
    """캐시된 Google GenAI 클라이언트를 반환합니다."""
    return _build_client(_get_api_key())


def extract_text_response(response: Any) -> str:
    """
    Gemini 응답 객체에서 텍스트를 추출합니다.

    SDK 버전에 따라 text/output_text 속성 혹은 candidates 목록에
    텍스트가 들어있을 수 있어 안전하게 처리합니다.

    Args:
        response: Gemini API 응답 객체

    Returns:
        str: 추출된 텍스트

    Raises:
        ValueError: 텍스트를 추출할 수 없는 경우
    """
    # 직접 text 속성이 있는 경우
    text = getattr(response, "text", None)
    if text:
        return text

    # output_text 속성이 있는 경우
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    # candidates 목록에서 추출
    candidates = getattr(response, "candidates", None) or []
    texts = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            continue
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                texts.append(part_text)

    if texts:
        return "\n".join(texts)

    raise ValueError("Gemini 응답에서 텍스트를 추출할 수 없습니다.")


def parse_json_response(response: Any) -> Dict[str, Any]:
    """
    Gemini 응답에서 JSON 객체를 파싱합니다.

    - ```json ... ``` 형식의 코드 블록 제거
    - 리스트를 반환하면 딕셔너리로 병합
    - 여러 JSON 객체를 병합

    Args:
        response: Gemini API 응답 객체

    Returns:
        Dict[str, Any]: 파싱된 JSON 객체

    Raises:
        ValueError: JSON 파싱에 실패한 경우
    """
    raw = extract_text_response(response).strip()

    # 코드 블록 제거 (```json ... ```)
    if raw.startswith("```"):
        raw = raw.strip("`\n ")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    def attempt_load(text: str) -> Dict[str, Any]:
        """JSON 로드 시도"""
        return json.loads(text)

    def split_objects(text: str):
        """여러 JSON 객체를 분리"""
        objs = []
        depth = 0
        buffer = []
        for ch in text:
            if ch == '{':
                depth += 1
            if depth > 0:
                buffer.append(ch)
            if ch == '}':
                depth -= 1
                if depth == 0 and buffer:
                    objs.append(''.join(buffer))
                    buffer = []
        return objs

    try:
        data = attempt_load(raw)
    except json.JSONDecodeError:
        # 괄호 범위 재조정
        start = raw.find("{")
        end = raw.rfind("}") + 1
        cleaned = raw[start:end] if start != -1 and end != -1 else raw
        try:
            data = attempt_load(cleaned)
        except json.JSONDecodeError:
            # 여러 객체 분리 시도
            objects = split_objects(cleaned)
            if objects:
                merged: Dict[str, Any] = {}
                for obj in objects:
                    try:
                        parsed = json.loads(obj)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        merged.update(parsed)
                    else:
                        merged[str(len(merged))] = parsed
                data = merged
            else:
                raise

    # 리스트를 딕셔너리로 변환
    if isinstance(data, list):
        merged: Dict[str, Any] = {}
        for idx, item in enumerate(data):
            if isinstance(item, dict):
                merged.update(item)
            else:
                merged[str(idx)] = item
        data = merged

    if not isinstance(data, dict):
        raise ValueError("Gemini 응답이 JSON 객체가 아닙니다.")

    return data
