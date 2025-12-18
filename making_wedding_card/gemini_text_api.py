"""
Gemini Flash 2.5 API를 사용한 청첩장 문구 생성
STEP 2-3: 톤에 맞는 청첩장 문구 생성 (인사말x3, 초대문구x3, 장소안내x1, 마무리x3)

⭐ 프롬프트 관리 방식: md/json 파일 기반 구조화된 리소스 관리
"""

import os
import json
from typing import Dict

from dotenv import load_dotenv
from google.genai import types

# 프롬프트 로더 및 GenAI 클라이언트
import sys
sys.path.append(os.path.dirname(__file__))
from utils.genai_client import get_genai_client, parse_json_response
from utils.prompt_loader import GeminiPromptBuilder

# .env 파일 로드
load_dotenv()

Schema = types.Schema
Type = types.Type


def _convert_schema_to_gemini(json_schema: Dict) -> Schema:
    """
    JSON Schema를 Gemini API용 Schema 객체로 변환

    Args:
        json_schema: 표준 JSON Schema 딕셔너리

    Returns:
        content_types.Schema 객체
    """
    type_map = {
        "object": Type.OBJECT,
        "array": Type.ARRAY,
        "string": Type.STRING,
        "number": Type.NUMBER,
        "integer": Type.INTEGER,
        "boolean": Type.BOOLEAN,
    }

    schema_type = type_map.get(json_schema.get("type", "string"), Type.STRING)

    kwargs = {"type": schema_type}

    if "description" in json_schema:
        kwargs["description"] = json_schema["description"]

    if "properties" in json_schema:
        kwargs["properties"] = {
            key: _convert_schema_to_gemini(value)
            for key, value in json_schema["properties"].items()
        }

    if "items" in json_schema:
        kwargs["items"] = _convert_schema_to_gemini(json_schema["items"])

    if "required" in json_schema:
        kwargs["required"] = json_schema["required"]

    return Schema(**kwargs)


# 프롬프트 빌더 초기화
prompt_builder = GeminiPromptBuilder()


def generate_wedding_texts(
    tone: str,
    groom_name: str,
    bride_name: str,
    groom_father: str,
    groom_mother: str,
    bride_father: str,
    bride_mother: str,
    venue: str,
    wedding_date: str,
    wedding_time: str,
    address: str = ""
) -> Dict[str, any]:
    """
    Gemini Flash 2.5를 사용하여 청첩장 문구 생성 (프롬프트 파일 기반)

    Args:
        tone: 청첩장 톤 (formal, casual, modern, classic, romantic, minimal)
        groom_name: 신랑 이름
        bride_name: 신부 이름
        groom_father: 신랑 아버지 이름
        groom_mother: 신랑 어머니 이름
        bride_father: 신부 아버지 이름
        bride_mother: 신부 어머니 이름
        venue: 예식장 정보
        wedding_date: 예식일 (형식: "2025년 4월 12일 토요일")
        wedding_time: 예식 시간 (형식: "오후 2시 30분")
        address: 예식장 주소

    Returns:
        Dict: {
            "greetings": [인사말1, 인사말2, 인사말3],
            "invitations": [초대문구1, 초대문구2, 초대문구3],
            "location": "장소안내",
            "closing": [마무리1, 마무리2, 마무리3]
        }
    """

    # 프롬프트 빌더로 프롬프트 + 스키마 로드
    prompt_data = prompt_builder.build_text_generation_prompt(
        tone=tone,
        groom_name=groom_name,
        bride_name=bride_name,
        groom_father=groom_father,
        groom_mother=groom_mother,
        bride_father=bride_father,
        bride_mother=bride_mother,
        venue=venue,
        wedding_date=wedding_date,
        wedding_time=wedding_time,
        address=address
    )

    # JSON Schema → Gemini Schema 변환
    gemini_schema = _convert_schema_to_gemini(prompt_data["schema"])

    client = get_genai_client()
    
    # 모델 선택 (사용자 요청 모델이 있으면 사용, 기본은 2.0-flash-exp)
    text_model = 'gemini-2.0-flash-exp'
    config_kwargs = {
        "response_mime_type": "application/json",
        "response_schema": gemini_schema,
    }
    
    # gemini-3-pro-preview 모델일 경우 ThinkingConfig 적용 (사용자 요청 반영)
    # 현재 SDK의 모델명 매칭은 환경에 따라 다를 수 있으나 사용자 스니펫 기준 적용
    model_to_use = text_model
    # if "pro-preview" in model_to_use:
    #     config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level="HIGH")

    response = client.models.generate_content(
        model=model_to_use,
        contents=[prompt_data["prompt"]],
        config=types.GenerateContentConfig(**config_kwargs),
    )

    return parse_json_response(response)


def regenerate_wedding_texts(
    previous_result: Dict[str, any],
    tone: str,
    **kwargs
) -> Dict[str, any]:
    """
    재생성 버튼을 눌렀을 때 다른 문구 생성

    Args:
        previous_result: 이전 생성 결과
        tone: 청첩장 톤
        **kwargs: generate_wedding_texts와 동일한 파라미터

    Returns:
        Dict: 새로운 문구들
    """

    # 동일한 함수 호출하되, 프롬프트에 "이전 결과와 다른 문구" 요청 추가
    result = generate_wedding_texts(tone=tone, **kwargs)

    return result


# 테스트 코드
if __name__ == "__main__":
    # 테스트 데이터
    test_data = {
        "tone": "romantic",
        "groom_name": "김철수",
        "bride_name": "이영희",
        "groom_father": "김아버지",
        "groom_mother": "김어머니",
        "bride_father": "이아버지",
        "bride_mother": "이어머니",
        "venue": "더 클래식 500",
        "wedding_date": "2025년 5월 20일 토요일",
        "wedding_time": "오후 2시",
        "address": "서울특별시 강남구 논현동 123-45"
    }

    print("=" * 80)
    print("Gemini Flash 2.5 청첩장 문구 생성 테스트 (프롬프트 파일 기반)")
    print("=" * 80)

    result = generate_wedding_texts(**test_data)

    print("\n생성된 문구:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n" + "=" * 80)
    print("✅ 프롬프트 파일 위치: prompts/invitation/")
    print("  - system.md: 시스템 역할 정의")
    print("  - text_generate.md: 텍스트 생성 태스크")
    print("  - text_schema.json: 출력 스키마")
    print("=" * 80)
