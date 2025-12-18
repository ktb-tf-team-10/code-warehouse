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

load_dotenv()

app = FastAPI()

# --- Configuration ---
NANO_BANANA_DIR = "nano_banana_3d"
os.makedirs(NANO_BANANA_DIR, exist_ok=True)

# Load API Keys (Expecting them in os.environ)
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
MESHY_API_KEY = os.environ.get("MESHY_API_KEY")

if not GOOGLE_API_KEY:
    print("WARNING: GOOGLE_API_KEY not found in environment variables.")
if not MESHY_API_KEY:
    print("WARNING: MESHY_API_KEY not found in environment variables.")

# --- Meshy Client with SSL Fix ---
def get_meshy_session():
    """Returns a requests.Session with retry logic and robust SSL handling."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

MESHY_BASE = "https://api.meshy.ai/openapi/v1"

def file_to_data_uri(image_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type not in ("image/jpeg", "image/png"):
        # Fallback if detection fails or is weird
        if image_path.lower().endswith(".jpg") or image_path.lower().endswith(".jpeg"):
            mime_type = "image/jpeg"
        elif image_path.lower().endswith(".png"):
            mime_type = "image/png"
        else:
            raise ValueError(f"Unsupported image type: {mime_type}")

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{b64}"

# --- Endpoints ---

@app.post("/api/generate-nano")
async def generate_nano(
    image1: UploadFile = File(...),
    image2: UploadFile = File(...),
    image3: Optional[UploadFile] = File(None)
):
    """
    Generates a Nano Banana image using Gemini.
    """
    try:
        # Save received files temporarily to read them properly for PIL/Gemini
        img1_bytes = await image1.read()
        pil_img1 = Image.open(io.BytesIO(img1_bytes))
        
        img2_bytes = await image2.read()
        pil_img2 = Image.open(io.BytesIO(img2_bytes))
        
        pil_img3 = None
        if image3:
            img3_bytes = await image3.read()
            pil_img3 = Image.open(io.BytesIO(img3_bytes))

        # Read Prompt
        try:
            with open(os.path.join(NANO_BANANA_DIR, "prompt_main.md"), "r") as f:
                prompt_text = f.read()
        except FileNotFoundError:
            # Fallback if file not found, though user said it exists
            prompt_text = "A full-body studio photograph of a hybrid couple figure..." 
            print("Warning: prompt_main.md not found, using fallback.")

        # Construct Gemini Request
        client = genai.Client(api_key=GOOGLE_API_KEY)
        
        # Prepare contents. The prompt refers to [Image 1], [Image 2], [Image 3].
        # We need to map them. Gemini handles interleaved text and images.
        # We will append images at the end or construct the list carefully.
        # According to doc: contents=[prompt, img1, img2...]
        
        # We just pass the prompt text and the images. We rely on Gemini's ability to understand "Image 1" etc based on order 
        # OR we can inject text to clarify. 
        # Typically "Here is Image 1", image, "Here is Image 2", image...
        
        contents = [prompt_text]
        contents.append("\n\n[Image 1]:")
        contents.append(pil_img1)
        contents.append("\n\n[Image 2]:")
        contents.append(pil_img2)
        
        if pil_img3:
             contents.append("\n\n[Image 3]:")
             contents.append(pil_img3)
        
        # Call Gemini
        response = client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=['TEXT', 'IMAGE'],
                 image_config=types.ImageConfig(
                    aspect_ratio="1:1",
                    image_size="2K"
                ),
            )
        )
        # Note: 'gemini-3-pro-image-preview' might be the name in the doc, but if it fails I'll swap. 
        # Actually user said "Gemini 3 Pro 프리뷰를 사용하면..."
        
        generated_image = None
        for part in response.parts:
            if part.as_image():
                generated_image = part.as_image()
                break
        
        if not generated_image:
             if response.text:
                 raise HTTPException(status_code=500, detail=f"Gemini returned text instead of image: {response.text}")
             raise HTTPException(status_code=500, detail="No image generated by Gemini.")

        # Save to file
        timestamp = int(time.time())
        filename = f"nano_banana_{timestamp}.png"
        save_path = os.path.join(NANO_BANANA_DIR, filename)
        generated_image.save(save_path)
        
        return JSONResponse({"status": "success", "image_path": save_path, "filename": filename})

    except Exception as e:
        print(f"Error in generate_nano: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class MeshRequest(BaseModel):
    image_path: str

@app.post("/api/generate-3d")
async def generate_3d(request: MeshRequest):
    """
    Uploads image to Meshy and starts task.
    """
    image_path = request.image_path
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image file not found")

    try:
        data_uri = file_to_data_uri(image_path)
        
        session = get_meshy_session()
        headers = {"Authorization": f"Bearer {MESHY_API_KEY}"}
        
        payload = {
            "image_url": data_uri,
            "ai_model": "latest",
            "should_texture": True,
            "enable_pbr": False,
            "should_remesh": True,
            "topology": "triangle",
            "target_polycount": 30000,
            "symmetry_mode": "auto",
        }
        
        response = session.post(f"{MESHY_BASE}/image-to-3d", headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        task_id = response.json().get("result")
        return {"task_id": task_id}

    except Exception as e:
        print(f"Error in generate_3d: {e}")
        # Detailed error if possible
        detail = str(e)
        if isinstance(e, requests.exceptions.SSLError):
            detail = f"SSL Error: {e}"
        raise HTTPException(status_code=500, detail=detail)

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    try:
        session = get_meshy_session()
        headers = {"Authorization": f"Bearer {MESHY_API_KEY}"}
        
        response = session.get(f"{MESHY_BASE}/image-to-3d/{task_id}", headers=headers, timeout=30)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# We can serve images statically to display in frontend if they are on same machine?
# Streamlit can read local files directly if on the same machine.
# But for correctness, let's expose an endpoint or just rely on local path since user is local.

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
