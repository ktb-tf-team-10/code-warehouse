import streamlit as st
import requests
import time
import os
import json

# Backend URL
BACKEND_URL = "http://localhost:8000"

st.set_page_config(page_title="Wedding Shorts Creator", layout="wide")

st.title("💍 Cinematic Wedding Shorts Generator")
st.markdown("Gemini 3 Flash & Sora 2 기반 청첩장 동영상 생성기")

# --- Sidebar Inputs ---
with st.sidebar:
    st.header("1. Upload Assets")
    couple_file = st.file_uploader("커플 사진 (주인공)", type=["jpg", "png", "jpeg"])
    bg_file = st.file_uploader("배경 레퍼런스 (장소)", type=["jpg", "png", "jpeg"])

    st.header("2. Concept Settings")
    
    themes = ["Romantic & Dreamy (몽환적이고 로맨틱함)", "Modern & Chic (도시적이고 세련됨)", "Classic & Elegant (고전적이고 우아함)", "직접 입력"]
    actions = ["Walking hand in hand toward camera (손잡고 걸어옴)", "Slow dancing in the center (중앙에서 슬로우 댄스)", "Looking at each other and smiling (서로 마주보고 미소)", "직접 입력"]
    cameras = ["Wide shot panning to Close-up (와이드에서 클로즈업으로)", "Cinematic Drone Orbit (드론 회전 샷)", "Low angle slow motion (로우 앵글 슬로우 모션)", "직접 입력"]

    selected_theme = st.selectbox("테마 선택", themes)
    if selected_theme == "직접 입력":
        selected_theme = st.text_input("테마 직접 입력")
        
    selected_action = st.selectbox("액션 선택", actions)
    if selected_action == "직접 입력":
        selected_action = st.text_input("액션 직접 입력")

    selected_camera = st.selectbox("카메라 앵글", cameras)
    if selected_camera == "직접 입력":
        selected_camera = st.text_input("카메라 앵글 직접 입력")

    # [FIX] API 제약에 맞춰 4, 8, 12초만 선택 가능하도록 변경
    duration = st.select_slider(
        "영상 길이 (초)", 
        options=[4, 8, 12], 
        value=8, 
        help="Sora 2 API는 현재 4초, 8초, 12초 길이만 지원합니다."
    )

    dialogue = st.text_input("대사 (선택 사항)", placeholder="예: 우리 결혼합니다")
    additional_req = st.text_area("추가 요청 사항", placeholder="예: 벚꽃이 흩날리게 해주세요")

    generate_btn = st.button("🎬 Generate Video", type="primary")

# --- Main Logic ---

if generate_btn:
    if not couple_file or not bg_file:
        st.error("두 장의 이미지를 모두 업로드해주세요.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.image(couple_file, caption="Couple Image")
        with col2:
            st.image(bg_file, caption="Background Reference")

        with st.status("🚀 Processing...", expanded=True) as status:
            st.write("이미지 전송 및 Gemini 3 분석 중...")
            
            # Reset file pointers
            couple_file.seek(0)
            bg_file.seek(0)
            
            files = {
                "couple_image": (couple_file.name, couple_file.getvalue(), couple_file.type),
                "bg_image": (bg_file.name, bg_file.getvalue(), bg_file.type)
            }
            data = {
                "theme": selected_theme,
                "action": selected_action,
                "camera": selected_camera,
                "duration": duration, 
                "dialogue": dialogue,
                "additional_request": additional_req
            }

            try:
                response = requests.post(f"{BACKEND_URL}/generate", files=files, data=data)
                
                if response.status_code == 200:
                    job_data = response.json()
                    job_id = job_data["id"]
                    st.write(f"Sora 작업 시작됨! (ID: {job_id})")
                    
                    # Polling Loop
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    while True:
                        poll_res = requests.get(f"{BACKEND_URL}/status/{job_id}")
                        if poll_res.status_code == 200:
                            status_data = poll_res.json()
                            current_status = status_data["status"]
                            progress = status_data.get("progress", 0)
                            
                            progress_bar.progress(progress)
                            status_text.text(f"Status: {current_status} ({progress}%)")
                            
                            if current_status == "completed":
                                status.update(label="✅ 생성 완료!", state="complete", expanded=False)
                                st.success("비디오 생성이 완료되었습니다!")
                                
                                # Download Video
                                try:
                                    dl_res = requests.get(f"{BACKEND_URL}/download/{job_id}", stream=True)
                                    if dl_res.status_code == 200:
                                        content_type = dl_res.headers.get("Content-Type", "")
                                        
                                        if "application/json" in content_type:
                                            data = dl_res.json()
                                            if "url" in data:
                                                st.video(data["url"])
                                            else:
                                                st.warning("비디오 URL을 찾을 수 없습니다.")
                                        else:
                                            st.video(dl_res.content)
                                            st.download_button(
                                                label="📥 MP4 다운로드",
                                                data=dl_res.content,
                                                file_name=f"wedding_shorts_{job_id}.mp4",
                                                mime="video/mp4"
                                            )
                                    else:
                                        st.error("다운로드 실패")
                                except Exception as e:
                                    st.error(f"다운로드 중 오류: {e}")
                                
                                break
                            
                            elif current_status == "failed":
                                status.update(label="❌ 생성 실패", state="error")
                                st.error(f"오류 발생: {status_data.get('error')}")
                                break
                        else:
                            st.warning("상태 확인 중 일시적인 오류 발생...")
                        
                        time.sleep(5)

                else:
                    status.update(label="🚨 서버 오류 발생", state="error")
                    st.error(f"서버 응답 오류 (Code: {response.status_code})")
                    try:
                        error_detail = response.json()
                        st.json(error_detail)
                    except:
                        st.code(response.text)

            except Exception as e:
                status.update(label="💥 클라이언트 연결 오류", state="error")
                st.error(f"요청 중 오류 발생: {str(e)}")