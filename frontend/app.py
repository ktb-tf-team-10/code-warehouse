import streamlit as st
import requests
import time
import os
from PIL import Image

# Configuration
API_URL = "http://127.0.0.1:8000/api"
NANO_BANANA_DIR = "nano_banana_3d"

st.set_page_config(page_title="Nano Banana 3D Generator", layout="wide")

st.title("🍌 Nano Banana 3D Generator")

# --- Step 1: Image Inputs ---
st.header("1. 참조 이미지 업로드")
col1, col2, col3 = st.columns(3)

with col1:
    img1 = st.file_uploader("Image 1 (Anatomy/Face) - 필수", type=["png", "jpg", "jpeg"])
    if img1:
        st.image(img1, caption="Anatomy Source", use_container_width=True)

with col2:
    img2 = st.file_uploader("Image 2 (Pose/Attire) - 필수", type=["png", "jpg", "jpeg"])
    if img2:
        st.image(img2, caption="Pose Source", use_container_width=True)

with col3:
    img3 = st.file_uploader("Image 3 (Style/Texture) - 선택", type=["png", "jpg", "jpeg"])
    if img3:
        st.image(img3, caption="Style Source", use_container_width=True)

# --- State Management ---
if "generated_image_path" not in st.session_state:
    st.session_state.generated_image_path = None
if "meshy_task_id" not in st.session_state:
    st.session_state.meshy_task_id = None
if "generation_status" not in st.session_state:
    st.session_state.generation_status = None # None, "generating", "completed", "failed"

# --- Step 2: Generate Nano Banana Image ---
st.header("2. Nano Banana 이미지 생성")

if st.button("이미지 생성하기", type="primary", disabled=(not img1 or not img2)):
    with st.spinner("Gemini가 이미지를 생성 중입니다..."):
        files = {
            "image1": (img1.name, img1.getvalue(), img1.type),
            "image2": (img2.name, img2.getvalue(), img2.type),
        }
        if img3:
            files["image3"] = (img3.name, img3.getvalue(), img3.type)
        
        try:
            response = requests.post(f"{API_URL}/generate-nano", files=files)
            if response.status_code == 200:
                result = response.json()
                st.session_state.generated_image_path = result["image_path"]
                st.success("이미지 생성 완료!")
                # Reset 3D state if new image generated
                st.session_state.meshy_task_id = None
                st.session_state.generation_status = None
            else:
                st.error(f"이미지 생성 실패: {response.text}")
        except Exception as e:
            st.error(f"연결 오류: {e}")

if st.session_state.generated_image_path:
    st.image(st.session_state.generated_image_path, caption="Generated Nano Banana", width=512)


# --- Step 3: Generate 3D Model ---
st.header("3. 3D 모델 생성 (Meshy AI)")

if st.session_state.generated_image_path:
    # 3D Generation Logic
    if st.button("3D 모델 생성 시작", disabled=bool(st.session_state.meshy_task_id)):
        with st.spinner("Meshy AI에 작업을 요청합니다..."):
            try:
                payload = {"image_path": st.session_state.generated_image_path}
                response = requests.post(f"{API_URL}/generate-3d", json=payload)
                if response.status_code == 200:
                    task_id = response.json()["task_id"]
                    st.session_state.meshy_task_id = task_id
                    st.session_state.generation_status = "generating"
                    st.session_state.start_time = time.time()
                    st.rerun()
                else:
                    st.error(f"3D 생성 요청 실패: {response.text}")
            except Exception as e:
                st.error(f"오류: {e}")

    # Polling & Progress
    if st.session_state.meshy_task_id and st.session_state.generation_status == "generating":
        task_id = st.session_state.meshy_task_id
        
        # Display Task ID
        st.info(f"Task ID: {task_id}")
        
        # Initialize timer if starting fresh
        if "start_time" not in st.session_state or st.session_state.start_time is None:
             st.session_state.start_time = time.time()

        progress_bar = st.progress(0)
        status_text = st.empty()
        timer_text = st.empty()
        
        while True:
            try:
                # Update Timer
                elapsed = time.time() - st.session_state.start_time
                timer_text.caption(f"경과 시간: {elapsed:.1f}초")

                status_resp = requests.get(f"{API_URL}/status/{task_id}")
                if status_resp.status_code != 200:
                    status_text.error("상태 확인 실패")
                    break
                
                data = status_resp.json()
                status = data.get("status")
                progress = data.get("progress", 0)
                
                progress_bar.progress(int(progress))
                status_text.text(f"상태: {status} ({progress}%)")
                
                if status == "SUCCEEDED":
                    st.session_state.generation_status = "completed"
                    st.success(f"3D 모델 생성 완료! (총 소요시간: {elapsed:.1f}초)")
                    # Show download link
                    glb_url = data.get("model_urls", {}).get("glb")
                    if glb_url:
                        st.markdown(f"[GLB 모델 다운로드]({glb_url})")
                        st.balloons()
                    st.session_state.start_time = None # Reset timer
                    break
                
                elif status in ["FAILED", "CANCELED"]:
                    st.session_state.generation_status = "failed"
                    st.error(f"생성 실패: {data.get('task_error', {}).get('message', '알 수 없는 오류')}")
                    st.session_state.start_time = None # Reset timer
                    break
                
                time.sleep(1) # Faster update for smooth timer
            except Exception as e:
                st.error(f"폴링 중 오류 발생: {e}")
                break

    # Regenerate Button
    if st.session_state.generation_status == "failed":
        if st.button("모델 재생성 (다시 시도)"):
            st.session_state.meshy_task_id = None
            st.session_state.generation_status = None
            st.rerun()

else:
    st.info("먼저 이미지를 생성해주세요.")
