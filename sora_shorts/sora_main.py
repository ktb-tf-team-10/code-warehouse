import os
import json
import logging
import asyncio
import uuid
import random
import requests
import io # [NEW] 이미지 바이너리 처리를 위해 추가
from typing import Optional
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from dotenv import load_dotenv
from PIL import Image # [NEW] 이미지 리사이징을 위해 추가

# Google Gemini SDK
from google import genai
from google.genai import types

# OpenAI SDK (for Sora)
from openai import OpenAI

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
current_dir = Path(__file__).parent
env_path = current_dir / ".env"
load_dotenv(dotenv_path=env_path, override=True)

DB_DIR = current_dir / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Sora Wedding Shorts Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Mock Data Storage ---
mock_jobs = {}

# --- Client Initialization ---
gemini_client = None
openai_client = None

def init_clients():
    global gemini_client, openai_client
    
    google_key = os.environ.get("GOOGLE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    
    if google_key:
        try:
            gemini_client = genai.Client(api_key=google_key)
            logger.info("✅ Gemini Client initialized.")
        except Exception as e:
            logger.error(f"Failed to init Gemini: {e}")
            
    if openai_key:
        try:
            openai_client = OpenAI(api_key=openai_key)
            logger.info("✅ OpenAI Client initialized.")
        except Exception as e:
            logger.error(f"Failed to init OpenAI: {e}")
    else:
        logger.warning("⚠️ OpenAI API Key missing in environment!")

init_clients()

# --- Helpers ---
def get_openai_client():
    global openai_client
    if openai_client:
        return openai_client
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        openai_client = OpenAI(api_key=key)
        return openai_client
    return None

def get_gemini_client():
    if gemini_client:
        return gemini_client
    raise HTTPException(status_code=500, detail="Google API Key is missing.")

def load_prompt(filename: str):
    try:
        path = Path(__file__).parent / "prompts" / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error loading prompt {filename}: {e}")
        raise e

# [NEW] 이미지 리사이징 헬퍼 함수
def resize_image_smart(image_bytes: bytes, target_width: int, target_height: int) -> bytes:
    """
    이미지를 target 해상도에 맞춰 비율을 유지하며 리사이징하고, 
    중앙을 기준으로 크롭(Center Crop)하여 정확한 크기를 맞춥니다.
    """
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # RGBA(투명도) 등은 RGB로 변환 (JPEG 저장을 위해)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
                
            target_ratio = target_width / target_height
            img_ratio = img.width / img.height
            
            # 비율에 맞춰 리사이징 (Cover 방식)
            if img_ratio > target_ratio:
                # 이미지가 더 넓음 -> 높이를 맞추고 가로를 자름
                new_height = target_height
                new_width = int(new_height * img_ratio)
            else:
                # 이미지가 더 좁음 -> 가로를 맞추고 세로를 자름
                new_width = target_width
                new_height = int(new_width / img_ratio)
                
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 중앙 크롭
            left = (new_width - target_width) / 2
            top = (new_height - target_height) / 2
            right = (new_width + target_width) / 2
            bottom = (new_height + target_height) / 2
            
            img = img.crop((left, top, right, bottom))
            
            # 만약 1px 오차 등이 있으면 강제 리사이즈로 보정
            if img.size != (target_width, target_height):
                 img = img.resize((target_width, target_height))
            
            # 바이트로 변환
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=95)
            return buf.getvalue()
            
    except Exception as e:
        logger.error(f"Image resize failed: {e}")
        # 실패 시 원본 반환 (API 에러 날 확률 높음)
        return image_bytes

async def analyze_images_with_gemini(couple_bytes: bytes, bg_bytes: bytes) -> dict:
    client = get_gemini_client()
    prompt_text = load_prompt("analysis_prompt.md")
    
    try:
        # Gemini 3 Flash 사용
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Content(
                    parts=[
                        types.Part(text=prompt_text),
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=couple_bytes)),
                        types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=bg_bytes))
                    ]
                )
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        if not response.text:
            raise ValueError("Empty response from Gemini")
        
        # JSON 파싱
        return json.loads(response.text)
        
    except Exception as e:
        logger.error(f"Gemini Analysis Error: {e}")
        # 실패 시 기본값 반환하여 프로세스 중단 방지
        return {
            "Task1_Subject_Identity_Extraction": "A beautiful couple in wedding attire",
            "Task2_Environmental_Metadata_Extraction": "A romantic wedding venue with soft lighting",
            "Task3_Integration_Synthesis_Strategy": "Natural blending with soft depth of field"
        }

def construct_clean_sora_prompt(analysis: dict, theme: str, action: str, camera: str, dialogue: str, req: str) -> str:
    """
    Sora가 이해할 수 있는 순수 묘사형 프롬프트 생성 함수.
    """
    subject_desc = analysis.get("Task1_Subject_Identity_Extraction", "A couple")
    env_desc = analysis.get("Task2_Environmental_Metadata_Extraction", "A beautiful background")
    
    dialogue_part = ""
    if dialogue and dialogue.strip():
        dialogue_part = f" The subjects are speaking, saying: '{dialogue}'."

    req_part = ""
    if req and req.strip():
        req_part = f" Note: {req}."

    final_prompt = (
        f"A cinematic vertical wedding video in {theme} style. "
        f"SUBJECT: {subject_desc}. "
        f"LOCATION: {env_desc}. "
        f"ACTION: {action}. "
        f"CAMERA: {camera}. "
        f"{dialogue_part}"
        f"{req_part}"
        " Highly detailed, 4k resolution, photorealistic."
    )
    
    return final_prompt

# --- Models ---
class VideoStatus(BaseModel):
    id: str
    status: str
    progress: Optional[int] = 0
    error: Optional[str] = None

# --- Mock Logic ---
def create_mock_job():
    job_id = f"mock_{uuid.uuid4().hex[:8]}"
    mock_jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "created_at": datetime.now(),
        "video_url": "https://www.w3schools.com/html/mov_bbb.mp4" 
    }
    return job_id

async def update_mock_progress(job_id: str):
    if job_id not in mock_jobs:
        return
    
    job = mock_jobs[job_id]
    if job["status"] == "completed":
        return

    if job["status"] == "queued":
        job["status"] = "processing"
        job["progress"] = 10
    elif job["status"] == "processing":
        job["progress"] += random.randint(10, 30)
        if job["progress"] >= 100:
            job["progress"] = 100
            job["status"] = "completed"
    
    mock_jobs[job_id] = job

# --- Endpoints ---

@app.post("/generate", response_model=VideoStatus)
async def generate_video(
    couple_image: UploadFile = File(...),
    bg_image: UploadFile = File(...),
    theme: str = Form(...),
    action: str = Form(...),
    camera: str = Form(...),
    duration: int = Form(8),
    dialogue: str = Form(""),
    additional_request: str = Form("")
):
    client = get_openai_client()
    
    try:
        # 이미지를 메모리에 읽음
        couple_bytes_raw = await couple_image.read()
        bg_bytes = await bg_image.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File read error: {e}")

    # 1. Gemini로 이미지 분석 (원본 이미지 사용 추천 - 분석엔 원본이 좋음)
    logger.info("Analyzing images with Gemini...")
    analysis = await analyze_images_with_gemini(couple_bytes_raw, bg_bytes)
    
    # 2. Sora용 클린 프롬프트 생성
    logger.info("Constructing Sora prompt...")
    final_prompt = construct_clean_sora_prompt(analysis, theme, action, camera, dialogue, additional_request)
    
    # 3. [NEW] Sora 입력용 이미지 리사이징 (720x1280 강제 맞춤)
    logger.info("Resizing image for Sora (720x1280)...")
    resized_couple_bytes = resize_image_smart(couple_bytes_raw, 720, 1280)
    
    try:
        if not client:
            raise Exception("OpenAI Client not available")

        logger.info(f"Sending request to Sora API (Duration: {duration}s)...")
        
        response = client.videos.create(
            model="sora-2",
            prompt=final_prompt,
            size="720x1280",
            seconds=str(duration),
            # [수정] 리사이징된 이미지 바이트 사용
            input_reference=("resized_ref.jpg", resized_couple_bytes, "image/jpeg") 
        )
        
        logger.info(f"Sora Job Created: {response.id}")
        return VideoStatus(id=response.id, status=response.status)

    except Exception as e:
        error_str = str(e)
        # 에러 발생 시 Mock 처리
        if any(x in error_str.lower() for x in ["billing", "rate limit", "400", "401", "403", "verified", "inpaint image"]):
            logger.warning(f"⚠️ OpenAI API Error ({e}). Falling back to MOCK MODE.")
            mock_id = create_mock_job()
            return VideoStatus(id=mock_id, status="queued", progress=0)
        
        logger.error(f"Critical Sora API Error: {e}")
        raise HTTPException(status_code=500, detail=f"Sora Generation Failed: {e}")

@app.get("/status/{video_id}", response_model=VideoStatus)
async def get_status(video_id: str):
    # Mock Status
    if video_id.startswith("mock_"):
        if video_id in mock_jobs:
            await update_mock_progress(video_id)
            job = mock_jobs[video_id]
            return VideoStatus(
                id=video_id,
                status=job["status"],
                progress=job["progress"]
            )
        else:
            raise HTTPException(status_code=404, detail="Mock video not found")

    # Real Status
    client = get_openai_client()
    try:
        video = client.videos.retrieve(video_id)
        return VideoStatus(
            id=video.id,
            status=video.status,
            progress=getattr(video, "progress", 0),
            error=str(video.error) if hasattr(video, "error") else None
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="Video not found")

@app.get("/download/{video_id}")
async def download_video(video_id: str):
    # Mock Download
    if video_id.startswith("mock_"):
        if video_id in mock_jobs and mock_jobs[video_id]["status"] == "completed":
            return {"status": "completed", "url": mock_jobs[video_id]["video_url"]}
        return {"status": "processing"}

    # Real Download
    client = get_openai_client()
    file_path = DB_DIR / f"{video_id}.mp4"
    
    try:
        if file_path.exists():
            with open(file_path, "rb") as f:
                content = f.read()
            return Response(content=content, media_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={video_id}.mp4"})

        video = client.videos.retrieve(video_id)
        if video.status != "completed":
            return {"status": video.status}
            
        logger.info(f"Downloading real video {video_id} to DB...")
        
        # [Manual Download via requests]
        api_key = os.environ.get("OPENAI_API_KEY")
        url = f"https://api.openai.com/v1/videos/{video_id}/content"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        
        with open(file_path, "rb") as f:
            content = f.read()
            
        return Response(content=content, media_type="video/mp4", headers={"Content-Disposition": f"attachment; filename={video_id}.mp4"})
        
    except Exception as e:
         logger.error(f"Download Error: {e}")
         raise HTTPException(status_code=404, detail=f"Failed to download video: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)