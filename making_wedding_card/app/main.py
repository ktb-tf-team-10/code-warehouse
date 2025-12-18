from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import sys
import os
import base64
import ssl

# 전역 SSL 인증서 검증 비활성화
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gemini_text_api import generate_wedding_texts
from nanobanana_api import generate_invitation_with_nanobanana
from gemini_invitation_api import generate_invitation_with_gemini
from imagen_design_api import generate_invitation_design

app = FastAPI(
    title="Wedding OS - Model API",
    description="청첩장 AI 텍스트 및 이미지 생성 API",
    version="1.0.0"
)

# 422 Unprocessable Entity 오류 상세 로깅을 위한 핸들러
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    error_details = exc.errors()
    print("❌ Validation Error Details:")
    for error in error_details:
        print(f"   - Field: {error.get('loc')}, Message: {error.get('msg')}, Type: {error.get('type')}")
    
    return JSONResponse(
        status_code=422,
        content={"success": False, "error": "Validation Error", "detail": error_details},
    )

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙 설정 (생성된 이미지 로컬 저장용)
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
generated_images_dir = os.path.join(static_dir, "generated_images")
if not os.path.exists(generated_images_dir):
    os.makedirs(generated_images_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return {
        "message": "Wedding OS Model API",
        "version": "1.0.0",
        "endpoints": [
            "GET /health - 헬스 체크",
            "POST /api/generate-text - 텍스트 생성 (Gemini)",
            "POST /api/generate-invitation - 청첩장 이미지 생성 (Gemini/Imagen)",
        ]
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/generate-text")
async def generate_text(request: dict):
    """
    청첩장 텍스트 생성 API (Gemini Flash 2.5)
    """
    try:
        result = generate_wedding_texts(
            tone=request.get("tone", "romantic"),
            groom_name=request.get("groom_name"),
            bride_name=request.get("bride_name"),
            groom_father=request.get("groom_father"),
            groom_mother=request.get("groom_mother"),
            bride_father=request.get("bride_father"),
            bride_mother=request.get("bride_mother"),
            venue=request.get("venue"),
            wedding_date=request.get("wedding_date"),
            wedding_time=request.get("wedding_time"),
            address=request.get("address", "")
        )
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/generate-invitation-test")
async def generate_invitation_test(
    model_type: str = Form("nanobanana"), # nanobanana, flash2.5, gemini3.0
    wedding_image: Optional[UploadFile] = File(None),
    style_image: Optional[UploadFile] = File(None),
    tone: Optional[str] = Form(None),
    groom_name: Optional[str] = Form(None),
    bride_name: Optional[str] = Form(None),
    venue: Optional[str] = Form(None),
    wedding_date: Optional[str] = Form(None),
    wedding_time: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    border_design_id: Optional[str] = Form("classic_gold"),
    groom_father: Optional[str] = Form(""),
    groom_mother: Optional[str] = Form(""),
    bride_father: Optional[str] = Form(""),
    bride_mother: Optional[str] = Form(""),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    prompt_override_1: Optional[str] = Form(None),
    prompt_override_2: Optional[str] = Form(None),
    prompt_override_3: Optional[str] = Form(None),
):
    """
    청첩장 이미지 생성 테스트 API (나노바나나 vs Gemini Flash 2.5 vs Gemini 3.0)
    """
    print(f"DEBUG: model_type={model_type}")
    
    try:
        wedding_image_base64 = None
        if wedding_image:
            wedding_image_bytes = await wedding_image.read()
            wedding_image_base64 = base64.b64encode(wedding_image_bytes).decode('utf-8')

        style_image_base64 = None
        if style_image:
            style_image_bytes = await style_image.read()
            style_image_base64 = base64.b64encode(style_image_bytes).decode('utf-8')

        if model_type == "nanobanana":
            # 나노바나나 대신 Imagen으로 대체 가능성 염두에 둠
            # 나노바나나 (Local Tuning Mode with Gemini)
            result = generate_invitation_with_nanobanana(
                groom_name=groom_name,
                bride_name=bride_name,
                groom_father=groom_father,
                groom_mother=groom_mother,
                bride_father=bride_father,
                bride_mother=bride_mother,
                venue=venue,
                venue_address=address,
                wedding_date=wedding_date,
                wedding_time=wedding_time,
                wedding_image_base64=wedding_image_base64,
                tone=tone,
                style_image_base64=style_image_base64,
                border_design_id=border_design_id,
                venue_latitude=latitude,
                venue_longitude=longitude,
                prompt_override_1=prompt_override_1,
                prompt_override_2=prompt_override_2,
                prompt_override_3=prompt_override_3
            )
        elif model_type == "flash2.5" or model_type == "imagen-4.0-generate":
            # Flash 2.5 또는 Imagen 4.0 시도
            # imagen_design_api.py 내부에서 fallback 로직이 작동합니다.
            processed_texts = {
                "greeting": "환영합니다",
                "invitation": "초대합니다",
                "location": "서울 어딘가",
                "closing": "감사합니다"
            }
            result = await generate_invitation_design(
                style_image_base64=style_image_base64,
                wedding_image_base64=wedding_image_base64,
                texts=processed_texts,
                venue_info={"name": venue, "address": address}
            )
        elif model_type == "gemini3.0" or model_type == "gemini-3-pro-image":
            # Gemini 3.0 (실제로는 gemini-3-pro-image-preview 사용)
            result = generate_invitation_with_gemini(
                model_name='gemini-3-pro-image-preview',
                groom_name=groom_name,
                bride_name=bride_name,
                venue=venue,
                wedding_date=wedding_date,
                wedding_time=wedding_time,
                wedding_image_base64=wedding_image_base64,
                style_image_base64=style_image_base64,
                tone=tone
            )
        else:
            return {"success": False, "error": f"지원하지 않는 모델 타입입니다: {model_type}"}

        return {"success": True, "data": result}

    except Exception as e:
        import traceback
        print(f"❌ Error during generation ({model_type}): {e}")
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


@app.post("/api/generate-invitation")
async def generate_invitation(
    wedding_image: Optional[UploadFile] = File(None),
    style_image: Optional[UploadFile] = File(None),
    tone: Optional[str] = Form(None),
    groom_name: Optional[str] = Form(None),
    bride_name: Optional[str] = Form(None),
    venue: Optional[str] = Form(None),
    wedding_date: Optional[str] = Form(None),
    wedding_time: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    border_design_id: Optional[str] = Form(None),
    groom_father: Optional[str] = Form(""),
    groom_mother: Optional[str] = Form(""),
    bride_father: Optional[str] = Form(""),
    bride_mother: Optional[str] = Form(""),
    latitude: Optional[float] = Form(None),
    longitude: Optional[float] = Form(None),
    floor_hall: Optional[str] = Form(""),
    model_name: Optional[str] = Form("models/gemini-3-pro-image-preview"), # 풀 네임으로 기본값 설정
):
    """
    청첩장 이미지 생성 API (이전 프로젝트 설정: Gemini + Imagen 3.0)
    """
    # 받은 데이터 로깅 (모델명 포함)
    print(f"DEBUG: model_name={model_name}")
    # 필수 필드 검증
    missing = []
    if not wedding_image: missing.append("wedding_image")
    if not style_image: missing.append("style_image")
    if not tone: missing.append("tone")
    if not groom_name: missing.append("groom_name")
    if not bride_name: missing.append("bride_name")
    if not venue: missing.append("venue")
    if not wedding_date: missing.append("wedding_date")
    if not wedding_time: missing.append("wedding_time")
    if not address: missing.append("address")

    if missing:
        return {"success": False, "error": f"필수 필드가 누락되었습니다: {', '.join(missing)}"}

    try:
        # 이미지 파일을 Base64로 변환
        wedding_image_bytes = await wedding_image.read()
        wedding_image_base64 = base64.b64encode(wedding_image_bytes).decode('utf-8')

        style_image_bytes = await style_image.read()
        style_image_base64 = base64.b64encode(style_image_bytes).decode('utf-8')

        # 1. 먼저 Gemini로 문구 생성
        texts_result = generate_wedding_texts(
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

        # 2. Imagen 3.0으로 이미지 생성
        processed_texts = {
            "greeting": texts_result.get("greetings", [""])[0],
            "invitation": texts_result.get("invitations", [""])[0],
            "location": texts_result.get("location", ""),
            "closing": texts_result.get("closing", [""])[0]
        }

        venue_info = {
            "name": venue,
            "address": address,
            "latitude": str(latitude) if latitude else None,
            "longitude": str(longitude) if longitude else None
        }

        # Imagen 3.0 디자인 생성 (병렬 처리, 모델명 전달)
        result = await generate_invitation_design(
            style_image_base64=style_image_base64,
            wedding_image_base64=wedding_image_base64,
            texts=processed_texts,
            venue_info=venue_info,
            model_name=model_name
        )

        # 문구 정보도 함께 반환
        result["texts"] = processed_texts

        return {"success": True, "data": result}

    except Exception as e:
        import traceback
        print(f"❌ Error during generation: {e}")
        print(traceback.format_exc())
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
