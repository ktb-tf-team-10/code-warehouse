"""
Google Imagen 및 Gemini API를 사용한 청첩장 디자인 생성
안정성과 속도를 위해 순차적 생성 및 최적화된 설정을 사용합니다.
"""

import os
import json
import base64
import asyncio
from typing import Dict, List, Optional, Any
import boto3
import uuid
from dotenv import load_dotenv
from google.genai import types

# 프로젝트 내부 유틸리티 사용
from utils.genai_client import get_genai_client

# .env 파일 로드
load_dotenv()

# AWS S3 설정 (현재는 로컬 저장 위주이나 유지)
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
    region_name='ap-northeast-2'
)

BUCKET_NAME = os.environ.get('S3_BUCKET_NAME', 'wedding-invitation-images')

# 로컬 저장 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
GENERATED_DIR = os.path.join(STATIC_DIR, "generated_images")
MODEL_SERVER_URL = os.environ.get('MODEL_SERVER_URL', 'http://localhost:8102')

def save_locally(image_bytes: bytes, file_type: str = "design") -> str:
    """생성된 이미지를 로컬 파일 시스템에 저장하고 URL을 반환"""
    if not os.path.exists(GENERATED_DIR):
        os.makedirs(GENERATED_DIR, exist_ok=True)
        
    filename = f"{file_type}_{uuid.uuid4()}.png"
    filepath = os.path.join(GENERATED_DIR, filename)
    
    with open(filepath, "wb") as f:
        f.write(image_bytes)
        
    return f"{MODEL_SERVER_URL}/static/generated_images/{filename}"

async def generate_invitation_design(
    style_image_base64: str,
    wedding_image_base64: str,
    texts: Dict[str, str],
    design_request: str = "",
    venue_info: Dict[str, str] = None,
    model_name: str = "models/gemini-3-pro-image-preview"
) -> Dict[str, any]:
    """
    청첩장 디자인 생성 (안정성을 위해 순차 처리)
    """
    
    # 생성할 페이지 데이터 정의
    tasks_data = [
        {
            "page_number": 1,
            "type": "cover",
            "description": "웨딩 사진 커버",
            "prompt": f"Wedding invitation cover card. Style: Reference. Content: Couple's wedding photo. {design_request}",
            "content_img": wedding_image_base64
        },
        {
            "page_number": 2,
            "type": "greeting",
            "description": "인사말",
            "prompt": f"Wedding invitation greeting page. Text in Korean: {texts.get('greeting', '')}. Elegant design.",
            "content_img": None
        },
        {
            "page_number": 3,
            "type": "invitation",
            "description": "초대 문구",
            "prompt": f"Wedding invitation main text page. Text in Korean: {texts.get('invitation', '')}. Minimalist style.",
            "content_img": None
        },
        {
            "page_number": 4,
            "type": "location",
            "description": "장소 안내",
            "prompt": f"Wedding invitation venue information page. Location: {venue_info.get('name', '') if venue_info else ''}. Text in Korean: {texts.get('location', '')}.",
            "content_img": None
        },
        {
            "page_number": 5,
            "type": "closing",
            "description": "마무리 인사",
            "prompt": f"Wedding invitation closing card. Text in Korean: {texts.get('closing', '')}. Warm feeling.",
            "content_img": None
        }
    ]
    
    pages = []
    
    # 5개를 동시에 보내면 Google API 부하로 503 에러 발생 가능성이 높음
    # 따라서 순차적으로 혹은 2개씩 나누어 실행
    for i, data in enumerate(tasks_data):
        print(f"⏳ [Page {i+1}/5] Generating {data['description']}...")
        
        # 각 페이지 생성 시도
        try:
            url = await _generate_single_page_task(
                data['prompt'], 
                data['content_img'], 
                style_image_base64, 
                model_name
            )
            
            pages.append({
                "page_number": data['page_number'],
                "image_url": url,
                "type": data['type'],
                "description": data['description']
            })
            
            # API 과부하 방지를 위한 짧은 휴식 (필요 시)
            # await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"❌ Error on Page {data['page_number']}: {e}")
            pages.append({
                "page_number": data['page_number'],
                "image_url": "https://via.placeholder.com/600x800.png?text=Generation+Error",
                "type": data['type'],
                "description": data['description']
            })

    return {
        "pages": sorted(pages, key=lambda x: x["page_number"]),
        "model_used": model_name
    }

async def _generate_single_page_task(prompt, content_img, style_img, model_name):
    """단일 페이지 생성 실행"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _generate_single_page_sync, prompt, content_img, style_img, model_name)

def _generate_single_page_sync(prompt: str, content_image_base64: Optional[str], style_image_base64: str, model_name: str) -> str:
    client = get_genai_client()
    
    # 모델명 정규화
    full_model_name = model_name if model_name.startswith("models/") else f"models/{model_name}"

    try:
        if "imagen" in full_model_name.lower():
            # Imagen 4.0 설정
            config = dict(
                number_of_images=1,
                output_mime_type="image/png",
                person_generation="ALLOW_ALL",
                aspect_ratio="3:4",
                image_size="1K",
            )
            result = client.models.generate_images(
                model=full_model_name,
                prompt=f"{prompt}. Follow the provided reference style. Professional wedding invitation.",
                config=config
            )
            if result.generated_images:
                from io import BytesIO
                img_buffer = BytesIO()
                result.generated_images[0].image.save(img_buffer, format='PNG')
                return save_locally(img_buffer.getvalue(), "design-imagen")
                
        else:
            # Gemini 3 Pro 설정 (속도 최적화를 위해 불필요한 도구 제거)
            parts = [types.Part.from_text(text=f"{prompt}. Professional design, 3:4 aspect ratio.")]
            if style_image_base64:
                parts.append(types.Part.from_bytes(data=base64.b64decode(style_image_base64), mime_type="image/png"))
            if content_image_base64:
                parts.append(types.Part.from_bytes(data=base64.b64decode(content_image_base64), mime_type="image/png"))

            # googleSearch 제거하여 속도 향상
            generate_content_config = types.GenerateContentConfig(
                response_modalities=["IMAGE"],
                image_config=types.ImageConfig(image_size="1K"),
            )

            response = client.models.generate_content(
                model=full_model_name,
                contents=[types.Content(role="user", parts=parts)],
                config=generate_content_config
            )
            
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        return save_locally(part.inline_data.data, "design-gemini")
            
    except Exception as e:
        print(f"❌ [Page] Failed with {full_model_name}: {e}")
        # Imagen 실패 시 Gemini로 최후의 시도
        if "imagen" in full_model_name.lower():
            return _generate_single_page_sync(prompt, content_image_base64, style_image_base64, "models/gemini-3-pro-image-preview")

    return "https://via.placeholder.com/600x800.png?text=Generation+Failed"
