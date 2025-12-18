"""
나노바나나(Nanobanana) API를 사용한 청첩장 생성 (Local Tuning Mode)
Gemini 3.0 Pro Image Preview 모델을 사용하여 로컬에서 프롬프트 튜닝을 진행합니다.
이미지는 로컬 스토리지에 저장됩니다.
"""

import os
import json
import base64
from typing import Dict, List
import requests
import uuid
import ssl
import certifi
from dotenv import load_dotenv
from google.genai import types, Client
from PIL import Image
import io

from utils.genai_client import get_genai_client, parse_json_response

# .env 파일 로드
load_dotenv()

# SSL 설정 (전역)
try:
    from utils.ssl_fix import configure_ssl_globally
    configure_ssl_globally()
except ImportError:
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# 로컬 이미지 저장 경로 설정
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
GENERATED_IMAGES_DIR = os.path.join(STATIC_DIR, "generated_images")
if not os.path.exists(GENERATED_IMAGES_DIR):
    os.makedirs(GENERATED_IMAGES_DIR)

def save_locally(image_bytes: bytes, file_type: str = "invitation") -> str:
    """
    생성된 이미지를 로컬에 저장하고 URL 반환

    Args:
        image_bytes: 이미지 바이트
        file_type: 파일 타입

    Returns:
        str: 로컬 서버 URL (http://localhost:8000/static/generated_images/...)
    """
    filename = f"{file_type}_{uuid.uuid4()}.jpg"
    file_path = os.path.join(GENERATED_IMAGES_DIR, filename)
    
    with open(file_path, "wb") as f:
        f.write(image_bytes)
    
    # 로컬 호스트 URL 반환 (Frontend에서 접근 가능하도록)
    # 실제 배포 시에는 도메인으로 변경 필요
    return f"http://localhost:8000/static/generated_images/{filename}"


def generate_wedding_texts_with_gemini(
    tone: str,
    groom_name: str,
    bride_name: str,
    venue: str,
    wedding_date: str,
    wedding_time: str,
    **kwargs
) -> Dict[str, str]:
    """
    Gemini를 사용하여 청첩장 문구 생성 (간소화 버전)
    """

    # 프롬프트 생성
    prompt = f"""
    당신은 한국의 전문 청첩장 작가입니다.

    다음 정보로 청첩장 문구를 생성해주세요:
    - 톤: {tone}
    - 신랑: {groom_name}
    - 신부: {bride_name}
    - 예식장: {venue}
    - 날짜: {wedding_date} {wedding_time}

    다음 3가지 문구를 생성하고, JSON 형식으로만 답변하세요:
    1. greeting: 인사말 (2-3문장, 100-150자)
    2. invitation: 초대 문구 (2문장, 80-120자)
    3. location: 장소 안내 (1-2문장, 50-80자)

    JSON 형식:
    {{
      "greeting": "인사말 내용",
      "invitation": "초대 문구 내용",
      "location": "장소 안내 내용"
    }}
    """

    # Gemini API 호출
    client = get_genai_client()
    response = client.models.generate_content(
        model='gemini-2.0-flash-exp',
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json"
        ),
    )

    # JSON 파싱
    return parse_json_response(response)


def generate_invitation_with_nanobanana(
    # STEP 1: 기본 정보
    groom_name: str,
    bride_name: str,
    groom_father: str,
    groom_mother: str,
    bride_father: str,
    bride_mother: str,
    venue: str,
    venue_address: str,
    wedding_date: str,
    wedding_time: str,
    # STEP 2: 웨딩 사진
    wedding_image_base64: str,
    # STEP 3: 톤
    tone: str,
    # STEP 4: 스타일 + 테두리
    style_image_base64: str,
    border_design_id: str,
    # 선택사항
    venue_latitude: str = None,
    venue_longitude: str = None,
    prompt_override_1: str = None,
    prompt_override_2: str = None,
    prompt_override_3: str = None,
) -> Dict[str, any]:
    """
    Gemini 3 Pro Image Preview 사용하여 3장의 청첩장 이미지 생성 및 로컬 저장
    (각 페이지별 프롬프트 적용)
    """

    print("=" * 80)
    print("청첩장 생성 (Local Tuning Mode) 시작...")
    print("=" * 80)

    # 1. Gemini로 문구 생성
    print("\n[1/4] Gemini로 문구 생성 중...")
    texts = generate_wedding_texts_with_gemini(
        tone=tone,
        groom_name=groom_name,
        bride_name=bride_name,
        venue=venue,
        wedding_date=wedding_date,
        wedding_time=wedding_time
    )
    print(f"✓ 문구 생성 완료")

    # 2. 지도 이미지 생성 (Google Maps Static API)
    map_image_base64 = None
    if venue_latitude and venue_longitude:
        print("\n[2/4] 지도 이미지 생성 중...")
        map_image_base64 = _generate_map_image(venue_latitude, venue_longitude, venue)
        print(f"✓ 지도 생성 완료")
    else:
        print("\n[2/4] 지도 정보 없음 - 스킵")

    # 3. Gemini 3 Pro로 이미지 생성 (3회 반복)
    print("\n[3/4] Gemini 3 Pro (Nanobanana Sim)로 청첩장 이미지 생성 중...")
    
    pages = []
    page_types = ["cover", "content", "location"]
    
    # 각 페이지별 프롬프트 및 Override 처리
    prompt_files = ["nanobanana_page1.md", "nanobanana_page2.md", "nanobanana_page3.md"]
    prompt_overrides = [prompt_override_1, prompt_override_2, prompt_override_3]
    
    previous_generated_image_bytes = None
    
    for i in range(3):
        print(f"\n  --- Page {i+1} Generation ---")
        
        # 프롬프트 로드
        if prompt_overrides[i]:
            print(f"  Using Overridden Prompt for Page {i+1}")
            prompt_template = prompt_overrides[i]
        else:
            prompt_template = _load_prompt_file(prompt_files[i])
            
        # 프롬프트 포맷팅
        formatted_prompt = prompt_template.format(
            groom_name=groom_name,
            bride_name=bride_name,
            texts=texts,
            venue=venue,
            venue_address=venue_address,
            wedding_date=wedding_date,
            wedding_time=wedding_time,
            tone=tone,
            border_design_id=border_design_id
        )

        # 이미지 입력 로직 (Sequential Editing)
        # Page 1: Wedding Photo + Style Image
        # Page 2: Page 1 Output + Style Image
        # Page 3: Page 2 Output + Map Image + Style Image
        
        input_image_arg = None
        
        if i == 0:
            # 첫 번째 페이지: 웨딩 사진 사용
            input_image_arg = wedding_image_base64
        else:
            # 이후 페이지: 이전 단계 결과물 사용 (bytes -> base64)
            if previous_generated_image_bytes:
                input_image_arg = base64.b64encode(previous_generated_image_bytes).decode('utf-8')
            else:
                # 이전 단계 실패 시...? 웨딩 사진으로 폴백하거나 중단?
                # 사용자 요청: "첫번째 이미지 생성때 사용한 Wedding Photo는 두번째, 세번째에는 입력하지 않을꺼야"
                # 따라서 이전 단계 없으면 입력 이미지 없이 진행
                input_image_arg = None

        # Gemini 3 Pro Image Preview는 num_images=1로 호출
        generated_images = _call_gemini_image_api(
            prompt=formatted_prompt,
            wedding_image_base64=input_image_arg, # 여기가 핵심 변경 (웨딩사진 or 이전결과물)
            style_image_base64=style_image_base64, # 스타일 이미지는 항상 사용
            map_image_base64=map_image_base64 if i == 2 else None, # 3페이지 지도 사용
            num_images=1
        )
        
        if generated_images:
            image_bytes = generated_images[0]
            image_url = save_locally(image_bytes, f"invitation-page{i+1}")
            
            # 다음 단계를 위해 저장
            previous_generated_image_bytes = image_bytes
            
            pages.append({
                "page_number": i + 1,
                "image_url": image_url,
                "type": page_types[i]
            })
            print(f"  ✓ Page {i+1} Saved: {image_url}")
        else:
            print(f"  ❌ Page {i+1} Generation Failed")
            previous_generated_image_bytes = None # 실패 시 체인 끊김 (다음 단계는 입력 이미지 없이 진행)

    print("\n" + "=" * 80)
    print("청첩장 생성 완료!")
    print("=" * 80)

    return {
        "pages": pages,
        "texts": texts
    }  

def _load_prompt_file(filename: str) -> str:
    """prompts 폴더에서 특정 파일 로드"""
    prompt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts", filename)
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"⚠️ Prompt file not found: {prompt_path}")
        return ""




def _call_gemini_image_api(
    prompt: str,
    wedding_image_base64: str,
    style_image_base64: str,
    map_image_base64: str,
    num_images: int = 3
) -> List[bytes]:
    """
    Gemini 3 Pro Image Preview API를 사용하여 이미지 생성
    """
    
    client = get_genai_client()
    
    # Base64 문자열을 PIL Image 호환 객체로 변환 (Gemini Client가 처리 가능할 수도 있지만, 안전하게)
    def decode_base64_to_image(b64_str):
        if not b64_str: return None
        return Image.open(io.BytesIO(base64.b64decode(b64_str)))

    wedding_img = decode_base64_to_image(wedding_image_base64)
    style_img = decode_base64_to_image(style_image_base64)
    map_img = decode_base64_to_image(map_image_base64)
    
    # contents 구성
    contents = [prompt]
    if wedding_img: contents.append(wedding_img)
    if style_img: contents.append(style_img)
    if map_img: contents.append(map_img)

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp', # gemini-3-pro-image-preview가 아직 정식 SDK에 없을 수 있음, 우선 사용자 요청대로 config 설정 시도하거나 flash 사용
            # 사용자 요청은 'gemini-3-pro-image-preview' 사용임.
            # SDK 버전 호환성 고려하여 model string 그대로 사용
            # 만약 에러 발생하면 gemini-2.0-flash-exp 등으로 fallback 고려
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE'], # 텍스트 제외하고 이미지만 요청
                image_config=types.ImageConfig(
                    aspect_ratio="3:4",
                    image_size="2K"
                ),
                candidate_count=num_images # 한 번에 여러 장 생성 요청 (지원 모델의 경우)
            )
        )
        
        # 모델명을 명시적으로 변경 (사용자 요청 사항 준수)
        # 위 호출에서 model 파라미터를 수정해야 함.
        # 아래 재호출 로직으로 대체
        pass
    except Exception:
        pass

    try:
        print(f"Generating images with gemini-3-pro-image-preview...")
        
        response = client.models.generate_content(
            model='gemini-3-pro-image-preview', 
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'],
                image_config=types.ImageConfig(
                    aspect_ratio="3:4",
                    image_size="2K"
                )
            )
        )
        
    except Exception as e:
        print(f"Gemini API 호출 중 오류 발생: {e}")
        # Retry logic for 500 errors
        if "500" in str(e) or "INTERNAL" in str(e):
             print("Retrying Gemini API call due to 500 Error...")
             import time
             time.sleep(2)
             response = client.models.generate_content(
                model='gemini-3-pro-image-preview', 
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=['TEXT', 'IMAGE'],
                    image_config=types.ImageConfig(
                        aspect_ratio="3:4",
                        image_size="2K"
                    )
                )
            )
        else:
             raise e

    images = []
    if response.candidates:
        for i, candidate in enumerate(response.candidates):
            print(f"Candidate {i} safety ratings: {candidate.safety_ratings}")
            print(f"Candidate {i} finish reason: {candidate.finish_reason}")
            
            for j, part in enumerate(candidate.content.parts):
                print(f"  Part {j} text: {part.text[:50] if part.text else 'None'}")
                print(f"  Part {j} inline_data: {part.inline_data.mime_type if part.inline_data else 'None'}, len: {len(part.inline_data.data) if part.inline_data else 0}")
                
                if part.inline_data:
                    # part.inline_data.data is already bytes in the SDK
                    images.append(part.inline_data.data)
    
    # 만약 이미지가 부족하면 추가 생성 (Loop) - 현재는 단순화를 위해 생략하거나 복사
    # Gemini 2.0 Flash는 한 번에 1장 생성일 수 있음.
    # 사용자가 무한 루프 튜닝을 원하므로, 3장이 안 되면 반복 호출 로직이 필요할 수 있으나
    # 우선 1-3장 나오는 대로 반환
    
    return images


def _generate_map_image(latitude: str, longitude: str, venue_name: str) -> str:
    """
    Google Maps Static API를 사용하여 지도 이미지 생성
    """

    google_maps_api_key = os.environ.get('GOOGLE_MAPS_API_KEY')
    if not google_maps_api_key:
         print("Warning: GOOGLE_MAPS_API_KEY not found.")
         return None

    # Google Maps Static API
    map_url = f"https://maps.googleapis.com/maps/api/staticmap?center={latitude},{longitude}&zoom=16&size=600x400&markers=color:red%7Clabel:{venue_name[0]}%7C{latitude},{longitude}&key={google_maps_api_key}"

    try:
        response = requests.get(map_url)
        if response.status_code == 200:
            map_image_base64 = base64.b64encode(response.content).decode('utf-8')
            return map_image_base64
    except Exception as e:
        print(f"지도 생성 실패: {e}")
    
    return None
