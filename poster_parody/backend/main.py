import os
import json
import time
import base64
import logging
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException
from dotenv import load_dotenv
from google import genai
from google.genai import types

# 환경 변수 로드
load_dotenv()

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("BatchBackend")

app = FastAPI()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

# --- [수정됨] 로컬 저장소 설정 (절대 경로) ---
# main.py가 위치한 폴더의 절대 경로를 구합니다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 항상 backend/generated_images 폴더에 저장되도록 설정합니다.
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_images")
os.makedirs(OUTPUT_DIR, exist_ok=True)
logger.info(f"✅ Local output directory set to: {OUTPUT_DIR}")

# 프롬프트 로드 함수
def load_prompt():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    prompt_path = os.path.join(current_dir, "prompts.md")
    
    if not os.path.exists(prompt_path):
        logger.warning("prompts.md not found. Using default prompt.")
        return "Combine the couple into the movie poster naturally."
        
    with open(prompt_path, "r", encoding="utf-8") as f:
        content = f.read()
        logger.info(f"Loaded prompt from {prompt_path} (Length: {len(content)})")
        return content

@app.post("/generate")
async def create_batch_job(
    couple_img: UploadFile = File(...),
    poster_imgs: List[UploadFile] = File(...)
):
    """
    1. 이미지를 Google File API에 업로드
    2. JSONL 파일 생성 및 업로드
    3. Batch Job 생성
    """
    job_start_time = time.time()
    logger.info(f"Received generation request. Couple: {couple_img.filename}, Posters: {len(poster_imgs)}EA")

    try:
        # 1. 파일 업로드 (Couple)
        logger.info(f"Uploading couple image: {couple_img.filename}")
        couple_content = await couple_img.read()
        # 임시 파일도 generated_images 폴더 내에 잠시 만들었다가 지웁니다 (경로 문제 방지)
        temp_couple_path = os.path.join(OUTPUT_DIR, f"temp_{int(time.time())}_{couple_img.filename}")
        with open(temp_couple_path, "wb") as f:
            f.write(couple_content)
        
        uploaded_couple = client.files.upload(
            file=temp_couple_path,
            config=types.UploadFileConfig(mime_type=couple_img.content_type)
        )
        os.remove(temp_couple_path)
        logger.info(f"Couple image uploaded successfully. URI: {uploaded_couple.uri}")

        # 2. 파일 업로드 (Posters) 및 JSONL 요청 구성
        requests = []
        prompt_text = load_prompt()
        
        for idx, poster in enumerate(poster_imgs):
            logger.info(f"Uploading poster image [{idx+1}/{len(poster_imgs)}]: {poster.filename}")
            poster_content = await poster.read()
            temp_poster_path = os.path.join(OUTPUT_DIR, f"temp_{int(time.time())}_{idx}_{poster.filename}")
            with open(temp_poster_path, "wb") as f:
                f.write(poster_content)
                
            uploaded_poster = client.files.upload(
                file=temp_poster_path,
                config=types.UploadFileConfig(mime_type=poster.content_type)
            )
            os.remove(temp_poster_path)
            logger.info(f"Poster image uploaded. URI: {uploaded_poster.uri}")

            # JSONL 라인 생성
            request_entry = {
                "key": f"poster-{idx}",
                "request": {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt_text},
                                {"file_data": {"file_uri": uploaded_couple.uri, "mime_type": uploaded_couple.mime_type}},
                                {"file_data": {"file_uri": uploaded_poster.uri, "mime_type": uploaded_poster.mime_type}}
                            ]
                        }
                    ],
                    "generation_config": {
                        "response_modalities": ["IMAGE"], 
                    }
                }
            }
            requests.append(request_entry)

        # 3. JSONL 파일 생성 및 업로드
        jsonl_filename = os.path.join(OUTPUT_DIR, f"batch_input_{int(time.time())}.jsonl")
        with open(jsonl_filename, "w") as f:
            for req in requests:
                f.write(json.dumps(req) + "\n")
        
        uploaded_jsonl = client.files.upload(
            file=jsonl_filename,
            config=types.UploadFileConfig(mime_type="application/jsonl")
        )
        os.remove(jsonl_filename)
        logger.info(f"Batch input JSONL uploaded. URI: {uploaded_jsonl.uri}")

        # 4. Batch Job 생성
        model_name = "gemini-3-pro-image-preview"
        logger.info(f"Creating batch job with model: {model_name}")
        batch_job = client.batches.create(
            model=model_name, 
            src=uploaded_jsonl.name,
            config={"display_name": f"wedding_poster_batch_{int(time.time())}"}
        )

        elapsed = time.time() - job_start_time
        logger.info(f"Batch job created successfully! Job Name: {batch_job.name} (Took {elapsed:.2f}s)")
        return {"job_name": batch_job.name, "message": "Batch job started successfully"}

    except Exception as e:
        logger.error(f"Failed to create batch job: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status/{job_name:path}")
async def get_job_status(job_name: str):
    """Batch 작업 상태 확인 (Polling용)"""
    try:
        # 상태 조회 로그 (너무 빈번하면 주석 처리 가능)
        # logger.info(f"Checking status for Job: {job_name}")
        batch_job = client.batches.get(name=job_name)
        
        current_state = batch_job.state.name
        # 상태 변화가 있을 때만 로그를 찍는 것이 좋으나, 확인을 위해 매번 출력
        logger.info(f"Job: {job_name} | State: {current_state}")
        
        return {"state": current_state}
    except Exception as e:
        logger.error(f"Error checking status for {job_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/result/{job_name:path}")
async def get_job_result(job_name: str):
    """
    작업 완료 시 결과 다운로드, 이미지 파싱, 로컬 저장 및 반환
    """
    logger.info(f"Result retrieval requested for Job: {job_name}")
    try:
        batch_job = client.batches.get(name=job_name)
        
        if batch_job.state.name != 'JOB_STATE_SUCCEEDED':
             logger.warning(f"Job is not succeeded yet. Current state: {batch_job.state.name}")
             return {"status": "not_ready", "message": "Job is not finished yet."}

        # 결과 파일 다운로드
        if not batch_job.dest or not batch_job.dest.file_name:
             logger.error("Job succeeded but no output file found.")
             return {"status": "error", "message": "No output file found."}

        result_filename = batch_job.dest.file_name
        logger.info(f"Downloading result file: {result_filename}")
        file_content = client.files.download(file=result_filename)
        
        decoded_content = file_content.decode('utf-8')
        saved_images = []
        
        line_count = len(decoded_content.splitlines())
        logger.info(f"Parsing {line_count} lines from result file.")

        # JSONL 파싱 및 이미지 저장
        for line in decoded_content.splitlines():
            if not line: continue
            data = json.loads(line)
            
            # key로 포스터 구분 (ex: poster-0)
            req_key = data.get("key", "unknown")
            
            # 응답에서 이미지 데이터 추출
            if "response" in data and "candidates" in data["response"]:
                candidate = data["response"]["candidates"][0]
                content_parts = candidate["content"]["parts"]
                
                for part in content_parts:
                    if "inlineData" in part:
                        img_b64 = part["inlineData"]["data"]
                        img_mime = part["inlineData"]["mimeType"]
                        img_bytes = base64.b64decode(img_b64)
                        
                        # --- [수정됨] 로컬 파일 저장 ---
                        safe_job_name = job_name.replace("/", "_")
                        save_name = f"{safe_job_name}_{req_key}.png"
                        # 위에서 설정한 절대 경로(OUTPUT_DIR) 사용
                        save_path = os.path.join(OUTPUT_DIR, save_name)
                        
                        with open(save_path, "wb") as img_f:
                            img_f.write(img_bytes)
                        
                        logger.info(f"✅ Image saved locally at: {save_path}")
                        
                        saved_images.append({
                            "key": req_key,
                            "mime_type": img_mime,
                            "b64_data": img_b64,
                            "local_path": save_path
                        })
            elif "error" in data:
                 logger.error(f"Error in specific request {req_key}: {data['error']}")

        logger.info(f"Returning {len(saved_images)} images to frontend.")
        return {"status": "completed", "images": saved_images}

    except Exception as e:
        logger.error(f"Error getting result for {job_name}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # 터미널 로그 레벨 설정
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")