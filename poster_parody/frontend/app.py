import streamlit as st
import requests
import time
import base64

# FastAPI 서버 주소
API_URL = "http://localhost:8000"

st.set_page_config(page_title="영화 포스터 웨딩 합성기", layout="wide")

st.title("🎬 영화 포스터 웨딩 합성기 (Gemini Batch)")
st.markdown("커플 사진과 여러 영화 포스터를 업로드하면, **Gemini Batch API**가 합성해줍니다.")

# --- 사이드바: 파일 업로드 ---
with st.sidebar:
    st.header("1. 사진 업로드")
    couple_file = st.file_uploader("남녀 커플 사진 (1장)", type=["png", "jpg", "jpeg"])
    poster_files = st.file_uploader("합성할 영화 포스터 (여러 장)", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    
    start_btn = st.button("작업 시작 🚀", type="primary")

# --- 메인 영역 ---
if start_btn:
    if not couple_file or not poster_files:
        st.error("커플 사진과 포스터를 모두 업로드해주세요.")
    else:
        # 1. API에 작업 요청
        with st.spinner("이미지를 서버로 전송하고 작업을 생성 중입니다..."):
            files = [('couple_img', (couple_file.name, couple_file, couple_file.type))]
            for p_file in poster_files:
                files.append(('poster_imgs', (p_file.name, p_file, p_file.type)))
            
            try:
                response = requests.post(f"{API_URL}/generate", files=files)
                response.raise_for_status()
                job_data = response.json()
                job_name = job_data["job_name"]
                
                # 세션 상태 저장 (Job ID + 시작 시간 기록)
                st.session_state['current_job_name'] = job_name
                st.session_state['start_time'] = time.time()
                
                st.success(f"작업이 시작되었습니다! Job ID: {job_name}")
            except Exception as e:
                st.error(f"작업 생성 실패: {e}")

# --- 상태 모니터링 및 결과 표시 (Polling Loop) ---
if 'current_job_name' in st.session_state:
    job_name = st.session_state['current_job_name']
    start_time = st.session_state['start_time']
    
    st.divider()
    st.subheader("⏳ 작업 진행 상황")
    
    # UI 레이아웃 분할: 타이머와 상태 메시지
    col1, col2 = st.columns([1, 4])
    with col1:
        timer_placeholder = st.empty() # 타이머 표시용
    with col2:
        status_text = st.empty()     # 상태 텍스트 표시용
        
    progress_bar = st.progress(0)
    result_container = st.container()

    # 폴링 루프
    while True:
        try:
            # 1. 경과 시간 계산 및 표시 (매 루프마다 갱신)
            elapsed_seconds = int(time.time() - start_time)
            timer_placeholder.metric(label="경과 시간", value=f"{elapsed_seconds}초")

            # 2. 상태 조회
            status_res = requests.get(f"{API_URL}/status/{job_name}")
            if status_res.status_code == 200:
                state = status_res.json()["state"]
                
                if state == "JOB_STATE_PENDING":
                    status_text.info(f"상태: 대기 중 (Queueing)... 서버 자원 할당 대기 중")
                    progress_bar.progress(10)
                elif state == "JOB_STATE_RUNNING":
                    status_text.warning(f"상태: 처리 중 (Running)... 이미지 생성 중입니다.")
                    progress_bar.progress(50)
                elif state == "JOB_STATE_SUCCEEDED":
                    status_text.success("상태: 완료 (Succeeded)! 결과를 불러옵니다.")
                    progress_bar.progress(100)
                    
                    # 결과 조회 요청
                    result_res = requests.get(f"{API_URL}/result/{job_name}")
                    if result_res.status_code == 200:
                        results = result_res.json()
                        if results["status"] == "completed":
                            images = results["images"]
                            
                            with result_container:
                                st.balloons()
                                st.header("✨ 생성된 결과물")
                                
                                # 갤러리 형태로 표시 (3열)
                                cols = st.columns(3)
                                for idx, img_data in enumerate(images):
                                    with cols[idx % 3]:
                                        img_bytes = base64.b64decode(img_data["b64_data"])
                                        st.image(img_bytes, caption=f"{img_data['key']}", use_column_width=True)
                                        st.success(f"저장됨: {img_data['local_path']}")
                            
                            # 작업 완료 시 루프 종료 및 세션 데이터 정리
                            del st.session_state['current_job_name']
                            break
                            
                elif state in ["JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"]:
                    status_text.error(f"작업이 실패하거나 취소되었습니다. 상태: {state}")
                    del st.session_state['current_job_name']
                    break
            
            # 3. 대기 (1초 단위로 갱신하여 타이머가 자연스럽게 보이도록 함)
            time.sleep(1)
            
        except Exception as e:
            st.error(f"통신 오류 발생: {e}")
            break