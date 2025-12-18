import os
import io
import time
import base64
import requests
import mimetypes
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from PIL import Image
from google import genai
from google.genai import types
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import uvicorn
from dotenv import load_dotenv

# --- 1. 환경 변수 및 설정 로드 ---
# .env 파일에서 API 키를 로드합니다. (GOOGLE_API_KEY, MESHY_API_KEY)
load_dotenv()

app = FastAPI()

# --- 2. 기본 설정 ---
# 생성된 결과물(이미지, 3D 모델)이 저장될 로컬 디렉토리 이름입니다.
NANO_BANANA_DIR = "nano_banana_3d"
# 서버 시작 시 해당 디렉토리가 없으면 자동으로 생성합니다.
os.makedirs(NANO_BANANA_DIR, exist_ok=True)

# 환경 변수에서 API 키를 가져옵니다.
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MESHY_API_KEY = os.environ.get("MESHY_API_KEY")

# API 키 누락 시 경고 메시지를 출력합니다.
if not GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY not found in environment variables.")
if not MESHY_API_KEY:
    print("WARNING: MESHY_API_KEY not found in environment variables.")

# --- 3. 유틸리티: Meshy API 통신 세션 (SSL 에러 방지용) ---
def get_meshy_session():
    """
    Meshy API와의 통신을 위한 requests.Session 객체를 생성합니다.
    SSL 연결 오류(SSLEOFError)나 일시적인 네트워크 오류에 대비하여
    재시도(Retry) 로직과 HTTPAdapter를 설정합니다.
    """
    session = requests.Session()
    # 재시도 전략 설정: 최대 5회, 백오프(대기시간) 적용, 특정 에러 코드(5xx) 및 429(Rate Limit) 대응
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    # http:// 및 https:// 요청 모두에 어댑터 적용
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

MESHY_BASE = "https://api.meshy.ai/openapi/v1"

# --- 4. 유틸리티: 이미지 -> Data URI 변환 ---
def file_to_data_uri(image_path: str) -> str:
    """
    로컬 이미지 파일을 읽어 Meshy API가 요구하는 Base64 encoded Data URI 형식으로 변환합니다.
    예: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...
    """
    # 파일 확장자를 기반으로 MIME 타입 추측 (예: image/jpeg, image/png)
    mime_type, _ = mimetypes.guess_type(image_path)
    
    # MIME 타입이 정확히 감지되지 않을 경우 확장자로 수동 할당
    if mime_type not in ("image/jpeg", "image/png"):
        if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif image_path.lower().endswith(".png"):
            mime_type = "image/png"
        else:
            raise ValueError(f"Unsupported image type: {mime_type}")

    # 파일을 바이너리 읽기 모드로 열어서 Base64 문자열로 인코딩
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{b64}"

# --- 5. API 엔드포인트 ---

# 5.1. Nano Banana 이미지 생성 API (Google Gemini 사용)
@app.post("/api/generate-nano")
async def generate_nano(
    image1: UploadFile = File(...), # 필수: 해부학/얼굴 참조 이미지
    image2: UploadFile = File(...), # 필수: 포즈/의상 참조 이미지
    image3: Optional[UploadFile] = File(None) # 선택: 스타일/질감 참조 이미지
):
    """
    사용자가 업로드한 2~3장의 이미지를 Gemini에게 전송하여
    Nano Banana 스타일의 합성 이미지를 생성합니다.
    """
    try:
        # 1) 업로드된 파일 읽기 및 PIL 이미지 객체로 변환
        img1_bytes = await image1.read()
        pil_img1 = Image.open(io.BytesIO(img1_bytes))
        
        img2_bytes = await image2.read()
        pil_img2 = Image.open(io.BytesIO(img2_bytes))
        
        pil_img3 = None
        if image3:
            img3_bytes = await image3.read()
            pil_img3 = Image.open(io.BytesIO(img3_bytes))

        # 2) 프롬프트 텍스트 로드
        # nano_banana_3d 폴더의 prompt_main.md 파일에서 생성 규칙을 읽어옵니다.
        try:
            with open(os.path.join(NANO_BANANA_DIR, "prompt_main.md"), "r") as f:
                prompt_text = f.read()
        except FileNotFoundError:
            prompt_text = "A full-body studio photograph of a hybrid couple figure..." 
            print("Warning: prompt_main.md not found, using fallback.")

        # 3) Gemini 클라이언트 초기화 및 요청 데이터 구성
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        # Gemini는 텍스트와 이미지를 리스트 형태로 순차적으로 입력받을 수 있습니다.
        # 프롬프트 텍스트를 먼저 넣고, 뒤이어 각 이미지를 배치합니다.
        contents = [prompt_text]
        contents.append("\n\n[Image 1]:")
        contents.append(pil_img1)
        contents.append("\n\n[Image 2]:")
        contents.append(pil_img2)
        
        if pil_img3:
             contents.append("\n\n[Image 3]:")
             contents.append(pil_img3)
        
        # 4) Gemini 모델 호출하여 이미지 생성
        # gemini-3-pro-image-preview 모델을 사용하며, 1:1 비율 / 2K 해상도를 요청합니다.
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'], # 텍스트와 이미지를 모두 반환받을 수 있도록 설정
                 image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                    image_size="2K"
                ),
            )
        )
        
        # 5) 생성된 이미지 추출
        generated_image = None
        for part in response.parts:
            if part.as_image():
                generated_image = part.as_image()
                break
        
        if not generated_image:
             if response.text:
                 raise HTTPException(status_code=500, detail=f"Gemini returned text instead of image: {response.text}")
             raise HTTPException(status_code=500, detail="No image generated by Gemini.")

        # 6) 개발자용 로그 생성 (프론트엔드 출력용)
        log_info = {
            "request_prompt": prompt_text[:200] + "...", 
            "response_text": response.text if response.text else "N/A (Image Generated)",
            "usage_metadata": str(response.usage_metadata) if hasattr(response, 'usage_metadata') else "N/A"
        }

        # 7) 이미지를 로컬 파일시스템에 저장
        timestamp = int(time.time())
        filename = f"nano_banana_{timestamp}.png"
        save_path = os.path.join(NANO_BANANA_DIR, filename)
        generated_image.save(save_path)
        
        # 8) 성공 응답 반환 (이미지 경로 및 로그 포함)
        return JSONResponse({
            "status": "success", 
            "image_path": save_path, 
            "filename": filename,
            "logs": log_info
        })

    except Exception as e:
        print(f"Error in generate_nano: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class MeshRequest(BaseModel):
    image_path: str

# 5.2. 3D 모델 생성 요청 API (Meshy AI 사용)
@app.post("/api/generate-3d")
async def generate_3d(request: MeshRequest):
    """
    생성된 이미지를 받아 Meshy AI에 3D 모델 생성을 요청합니다.
    이 작업은 비동기로 진행되며 Task ID를 반환합니다.
    """
    image_path = request.image_path
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image file not found")

    try:
        # 1) 이미지를 Data URI로 변환
        data_uri = file_to_data_uri(image_path)
        
        # 2) Meshy 세션 및 헤더 준비
        session = get_meshy_session()
        headers = {"Authorization": f"Bearer {MESHY_API_KEY}"}
        
        # 3) 요청 페이로드 구성
        # should_remesh=True, topology='triangle' 등은 웹/게임 엔진용 최적화를 위한 설정입니다.
        payload = {
            "image_url": data_uri,
            "ai_model": "latest",
            "should_texture": True,
            "enable_pbr": False,
            "should_remesh": True,      # 토폴로지 리메싱 활성화
            "topology": "triangle",     # 삼각형 토폴로지 사용
            "target_polycount": 100000,  # 목표 폴리곤 수 (사용자 설정값: 100,000)
            "symmetry_mode": "auto",    # 대칭 자동 감지
        }
        
        # 4) Meshy API 호출 (작업 등록)
        response = session.post(f"{MESHY_BASE}/image-to-3d", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        # 5) 개발자용 로그 생성 (데이터 URI는 너무 길어서 제외)
        log_info = {
            "request_payload": {k: v for k, v in payload.items() if k != "image_url"}, 
            "response": response.json()
        }
        
        # 6) Task ID 반환
        task_id = response.json().get("result")
        return {"task_id": task_id, "logs": log_info}

    except Exception as e:
        print(f"Error in generate_3d: {e}")
        detail = str(e)
        if isinstance(e, requests.exceptions.SSLError):
            detail = f"SSL Error: {e}"
        raise HTTPException(status_code=500, detail=detail)

# 5.3. 작업 상태 확인 API
@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """
    특정 Task ID에 대한 현재 진행 상태(Status)와 진행률(Progress)을 조회합니다.
    프론트엔드에서 주기적으로(Polling) 호출합니다.
    """
    try:
        session = get_meshy_session()
        headers = {"Authorization": f"Bearer {MESHY_API_KEY}"}
        
        # Meshy API에 상태 조회 요청
        response = session.get(f"{MESHY_BASE}/image-to-3d/{task_id}", headers=headers, timeout=30)
        response.raise_for_status()
        
        # 응답 JSON 자체를 반환 (프론트엔드 로그 출력용으로도 사용됨)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
