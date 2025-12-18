"""
Gemini 모델을 사용한 청첩장 생성 (Nanobanana 대체 테스트용)
"""

import os
import base64
from typing import Dict, List, Any
import boto3
import uuid
from google.genai import types
from utils.genai_client import get_genai_client, parse_json_response

# AWS S3 설정
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

def save_locally(image_bytes: bytes, file_type: str = "invitation-gemini") -> str:
    if not os.path.exists(GENERATED_DIR):
        os.makedirs(GENERATED_DIR, exist_ok=True)
    filename = f"{file_type}_{uuid.uuid4()}.png"
    filepath = os.path.join(GENERATED_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    return f"{MODEL_SERVER_URL}/static/generated_images/{filename}"

def upload_to_s3(image_bytes: bytes, file_type: str = "invitation-gemini") -> str:
    file_key = f"{file_type}/{uuid.uuid4()}.png"
    s3_client.put_object(
        Bucket=BUCKET_NAME,
        Key=file_key,
        Body=image_bytes,
        ContentType='image/png'
    )
    return f"https://{BUCKET_NAME}.s3.ap-northeast-2.amazonaws.com/{file_key}"

def generate_invitation_with_gemini(
    model_name: str, # 'gemini-2.0-flash-exp' 또는 'gemini-3-pro-image-preview'
    groom_name: str,
    bride_name: str,
    venue: str,
    wedding_date: str,
    wedding_time: str,
    wedding_image_base64: str = None,
    style_image_base64: str = None,
    tone: str = "romantic",
    **kwargs
) -> Dict[str, Any]:
    """
    Gemini 모델을 사용하여 청첩장 이미지 및 문구 생성
    """
    client = get_genai_client()
    
    # 1. 문구 생성 (항상 2.0 Flash 사용 권장)
    prompt_text = f"""
    Create Korean wedding invitation texts for:
    Groom: {groom_name}, Bride: {bride_name}
    Venue: {venue}, Date: {wedding_date} {wedding_time}
    Tone: {tone}
    
    Return JSON with: greeting, invitation, location.
    """
    
    text_response = client.models.generate_content(
        model='gemini-2.0-flash-exp',
        contents=[prompt_text],
        config=types.GenerateContentConfig(response_mime_type="application/json")
    )
    texts = parse_json_response(text_response)
    
    # 2. 이미지 생성 (요청된 모델 사용)
    # Gemini 3 Pro Image Preview는 스트리밍 방식으로 이미지 생성 가능
    # 여기서는 단순화를 위해 generate_content 사용 (지원되는 경우)
    
    image_prompt = f"""
    Create a beautiful wedding invitation card image.
    Tone: {tone}
    Main names: {groom_name} & {bride_name}
    Venue: {venue}
    Date: {wedding_date}
    Apply a {tone} style. 
    Professional design, 3:4 aspect ratio.
    """
    
    images = []
    
    try:
        # Gemini 3 Pro Image Preview 모델을 사용하여 이미지 생성 시도
        # (gemini_image_preview.py의 로직 참고)
        
        contents = [types.Part.from_text(text=image_prompt)]
        if wedding_image_base64:
            contents.append(types.Part.from_bytes(data=base64.b64decode(wedding_image_base64), mime_type="image/png"))
        if style_image_base64:
            contents.append(types.Part.from_bytes(data=base64.b64decode(style_image_base64), mime_type="image/png"))

        print(f"Generating image with {model_name}...")
        
        # 이미지 생성 설정
        config = types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=types.ImageConfig(image_size="1K") if "image-preview" in model_name else None,
        )

        response = client.models.generate_content(
            model=model_name,
            contents=[types.Content(role="user", parts=contents)],
            config=config,
        )
        
        # 응답에서 이미지 추출
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                image_url = save_locally(part.inline_data.data, f"invitation-{model_name}")
                images.append(image_url)
                
    except Exception as e:
        print(f"Error generating image with {model_name}: {e}")
        # 이미지 생성이 실패하더라도 텍스트는 반환
        pass

    # 만약 이미지가 생성되지 않았다면 샘플 이미지 URL이라도 반환 (테스트용)
    if not images:
        images = ["https://via.placeholder.com/600x800.png?text=Gemini+Image+Generation+Placeholder"]

    pages = []
    for i, url in enumerate(images):
        pages.append({
            "page_number": i + 1,
            "image_url": url,
            "type": "cover" if i == 0 else "content"
        })

    return {
        "pages": pages,
        "texts": texts,
        "model_used": model_name
    }

