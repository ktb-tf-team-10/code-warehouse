"""
프롬프트 로더 유틸리티

프롬프트를 md/json 파일로 관리하고 런타임에 동적으로 로드하는 모듈
"""

import os
import json
from typing import Dict, Any
from pathlib import Path
from jinja2 import Template


class PromptLoader:
    """프롬프트 템플릿 로더"""

    def __init__(self, base_path: str = None):
        """
        Args:
            base_path: 프롬프트 파일들의 기본 경로. None이면 현재 파일 기준 ../prompts/
        """
        if base_path is None:
            current_file = Path(__file__)
            self.base_path = current_file.parent.parent / "prompts"
        else:
            self.base_path = Path(base_path)

    def load_prompt(self, path: str, variables: Dict[str, Any] = None) -> str:
        """
        프롬프트 템플릿 파일을 로드하고 변수를 치환합니다.

        Args:
            path: base_path 기준 상대 경로 (예: "invitation/text_generate.md")
            variables: 템플릿에 주입할 변수 딕셔너리

        Returns:
            변수가 치환된 최종 프롬프트 문자열

        Example:
            >>> loader = PromptLoader()
            >>> prompt = loader.load_prompt(
            ...     "invitation/text_generate.md",
            ...     {"tone": "romantic", "groom_name": "홍길동"}
            ... )
        """
        file_path = self.base_path / path

        if not file_path.exists():
            raise FileNotFoundError(f"프롬프트 파일을 찾을 수 없습니다: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        if variables:
            template = Template(template_content)
            return template.render(**variables)

        return template_content

    def load_schema(self, path: str) -> Dict[str, Any]:
        """
        JSON 스키마 파일을 로드합니다.

        Args:
            path: base_path 기준 상대 경로 (예: "invitation/text_schema.json")

        Returns:
            JSON 스키마 딕셔너리

        Example:
            >>> loader = PromptLoader()
            >>> schema = loader.load_schema("invitation/text_schema.json")
        """
        file_path = self.base_path / path

        if not file_path.exists():
            raise FileNotFoundError(f"스키마 파일을 찾을 수 없습니다: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_combined(self,
                      system_path: str,
                      task_path: str,
                      variables: Dict[str, Any] = None) -> str:
        """
        시스템 프롬프트와 태스크 프롬프트를 결합합니다.

        Args:
            system_path: 시스템 프롬프트 경로
            task_path: 태스크 프롬프트 경로
            variables: 템플릿 변수

        Returns:
            결합된 최종 프롬프트

        Example:
            >>> loader = PromptLoader()
            >>> prompt = loader.load_combined(
            ...     "invitation/system.md",
            ...     "invitation/text_generate.md",
            ...     {"tone": "romantic"}
            ... )
        """
        system_prompt = self.load_prompt(system_path)
        task_prompt = self.load_prompt(task_path, variables)

        return f"{system_prompt}\n\n---\n\n{task_prompt}"


class GeminiPromptBuilder:
    """Gemini API용 프롬프트 빌더"""

    def __init__(self, loader: PromptLoader = None):
        self.loader = loader or PromptLoader()

    def build_text_generation_prompt(self,
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
                                     address: str) -> Dict[str, Any]:
        """
        Gemini 텍스트 생성용 프롬프트와 스키마를 빌드합니다.

        Returns:
            {
                "prompt": "최종 프롬프트",
                "schema": {...}  # JSON 스키마
            }
        """
        variables = {
            "tone": tone,
            "groom_name": groom_name,
            "bride_name": bride_name,
            "groom_father": groom_father,
            "groom_mother": groom_mother,
            "bride_father": bride_father,
            "bride_mother": bride_mother,
            "venue": venue,
            "wedding_date": wedding_date,
            "wedding_time": wedding_time,
            "address": address,
        }

        prompt = self.loader.load_combined(
            "invitation/system.md",
            "invitation/text_generate.md",
            variables
        )

        schema = self.loader.load_schema("invitation/text_schema.json")

        return {
            "prompt": prompt,
            "schema": schema
        }


class NanobananaPromptBuilder:
    """Nanobanana API용 프롬프트 빌더"""

    def __init__(self, loader: PromptLoader = None):
        self.loader = loader or PromptLoader()

    def build_page1_prompt(self,
                          groom_name: str,
                          bride_name: str,
                          border_design_id: str) -> str:
        """페이지 1 (커버) 프롬프트 생성"""
        variables = {
            "groom_name": groom_name,
            "bride_name": bride_name,
            "border_design_id": border_design_id,
        }

        return self.loader.load_combined(
            "nanobanana/system.md",
            "nanobanana/page1_cover.md",
            variables
        )

    def build_page2_prompt(self,
                          greeting_text: str,
                          invitation_text: str,
                          groom_name: str,
                          bride_name: str,
                          groom_father: str,
                          groom_mother: str,
                          bride_father: str,
                          bride_mother: str,
                          border_design_id: str) -> str:
        """페이지 2 (인사말 & 초대) 프롬프트 생성"""
        variables = {
            "greeting_text": greeting_text,
            "invitation_text": invitation_text,
            "groom_name": groom_name,
            "bride_name": bride_name,
            "groom_father": groom_father,
            "groom_mother": groom_mother,
            "bride_father": bride_father,
            "bride_mother": bride_mother,
            "border_design_id": border_design_id,
        }

        return self.loader.load_combined(
            "nanobanana/system.md",
            "nanobanana/page2_content.md",
            variables
        )

    def build_page3_prompt(self,
                          wedding_date: str,
                          wedding_time: str,
                          venue: str,
                          address: str,
                          floor_hall: str,
                          border_design_id: str) -> str:
        """페이지 3 (장소 안내) 프롬프트 생성"""
        variables = {
            "wedding_date": wedding_date,
            "wedding_time": wedding_time,
            "venue": venue,
            "address": address,
            "floor_hall": floor_hall,
            "border_design_id": border_design_id,
        }

        return self.loader.load_combined(
            "nanobanana/system.md",
            "nanobanana/page3_location.md",
            variables
        )


# 편의 함수들
def load_text_generation_prompt(**kwargs) -> Dict[str, Any]:
    """
    텍스트 생성 프롬프트를 빠르게 로드하는 헬퍼 함수

    Args:
        tone: 문구 톤
        groom_name: 신랑 이름
        bride_name: 신부 이름
        ... (나머지 파라미터)

    Returns:
        {"prompt": str, "schema": dict}
    """
    builder = GeminiPromptBuilder()
    return builder.build_text_generation_prompt(**kwargs)


def load_nanobanana_prompts(page: int, **kwargs) -> str:
    """
    나노바나나 이미지 생성 프롬프트를 페이지별로 로드

    Args:
        page: 1, 2, 3 중 하나
        **kwargs: 각 페이지별 필요 파라미터

    Returns:
        프롬프트 문자열
    """
    builder = NanobananaPromptBuilder()

    if page == 1:
        return builder.build_page1_prompt(**kwargs)
    elif page == 2:
        return builder.build_page2_prompt(**kwargs)
    elif page == 3:
        return builder.build_page3_prompt(**kwargs)
    else:
        raise ValueError(f"잘못된 페이지 번호: {page} (1-3만 가능)")


if __name__ == "__main__":
    # 테스트 코드
    print("=== Prompt Loader Test ===\n")

    # 1. 텍스트 생성 프롬프트 테스트
    result = load_text_generation_prompt(
        tone="romantic",
        groom_name="홍길동",
        bride_name="김영희",
        groom_father="홍판서",
        groom_mother="김씨",
        bride_father="김판서",
        bride_mother="이씨",
        venue="더 클래식 500",
        wedding_date="2025년 4월 12일 토요일",
        wedding_time="오후 2시 30분",
        address="서울특별시 강남구 테헤란로 123"
    )

    print("📝 텍스트 생성 프롬프트 (첫 500자):")
    print(result["prompt"][:500])
    print("\n📋 스키마:")
    print(json.dumps(result["schema"], indent=2, ensure_ascii=False))

    # 2. 이미지 생성 프롬프트 테스트
    print("\n" + "="*50 + "\n")
    print("🎨 페이지 1 프롬프트 (첫 500자):")
    page1 = load_nanobanana_prompts(
        page=1,
        groom_name="홍길동",
        bride_name="김영희",
        border_design_id="border1"
    )
    print(page1[:500])
