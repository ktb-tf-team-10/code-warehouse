import streamlit as st
import requests
import os
from PIL import Image
import io

# 설정
API_URL = "http://localhost:8000/api/generate-invitation-test"
PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")

st.set_page_config(layout="wide", page_title="Nanobanana Tuning (3-Step)")

def load_prompt(filename):
    path = os.path.join(PROMPT_DIR, filename)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

st.title("🍌 Nanobanana Prompt Tuning (3 Pages)")

# 기본 정보 입력 (좌측)
col1, col2 = st.columns([1, 1.5])

with col1:
    st.subheader("1. Basic Info")
    groom_name = st.text_input("Groom Name", "김철수")
    bride_name = st.text_input("Bride Name", "이영희")
    
    c1, c2 = st.columns(2)
    with c1: wedding_date = st.text_input("Date", "2025년 5월 5일")
    with c2: wedding_time = st.text_input("Time", "낮 12시")
        
    venue = st.text_input("Venue", "서울 신라호텔")
    address = st.text_input("Address", "서울 중구 동호로 249")
    
    st.subheader("2. Images & Tone")
    tone = st.selectbox("Tone", ["elegant", "romantic", "modern", "traditional"], index=1)
    
    # Session State로 이미지 유지 시도 (Streamlit 특성상 file_uploader 리셋될 수 있음)
    wedding_image = st.file_uploader("Wedding Photo", type=["png", "jpg", "jpeg"], key="u_wedding")
    style_image = st.file_uploader("Style Reference (Optional)", type=["png", "jpg", "jpeg"], key="u_style")


with col2:
    st.subheader("3. Prompt Editing")
    
    # 탭으로 3개 페이지 프롬프트 관리
    tab1, tab2, tab3 = st.tabs(["Page 1 (Cover)", "Page 2 (Content)", "Page 3 (Venue)"])
    
    # 초기 로드 (Session State가 비어있으면 파일에서 로드)
    if "prompt_1" not in st.session_state: st.session_state.prompt_1 = load_prompt("nanobanana_page1.md")
    if "prompt_2" not in st.session_state: st.session_state.prompt_2 = load_prompt("nanobanana_page2.md")
    if "prompt_3" not in st.session_state: st.session_state.prompt_3 = load_prompt("nanobanana_page3.md")

    with tab1:
        prompt_1 = st.text_area("Prompt for Page 1", value=st.session_state.prompt_1, height=300, key="txt_p1")
        st.session_state.prompt_1 = prompt_1
    
    with tab2:
        prompt_2 = st.text_area("Prompt for Page 2", value=st.session_state.prompt_2, height=300, key="txt_p2")
        st.session_state.prompt_2 = prompt_2
        
    with tab3:
        prompt_3 = st.text_area("Prompt for Page 3", value=st.session_state.prompt_3, height=300, key="txt_p3")
        st.session_state.prompt_3 = prompt_3

    generate_btn = st.button("Generate Invitation (All 3 Pages)", type="primary", use_container_width=True)

    if generate_btn:
        if not wedding_image:
            st.error("Please upload a wedding photo.")
        else:
            with st.spinner("Generating 3 pages sequentially... (Approx 1 min)"):
                try:
                    # Prepare Form Data
                    files = {
                        "wedding_image": ("wedding.jpg", wedding_image.getvalue(), wedding_image.type),
                    }
                    if style_image:
                        files["style_image"] = ("style.jpg", style_image.getvalue(), style_image.type)
                    
                    data = {
                        "model_type": "nanobanana",
                        "groom_name": groom_name,
                        "bride_name": bride_name,
                        "venue": venue,
                        "wedding_date": wedding_date,
                        "wedding_time": wedding_time,
                        "address": address,
                        "tone": tone,
                        "prompt_override_1": prompt_1,
                        "prompt_override_2": prompt_2,
                        "prompt_override_3": prompt_3,
                    }
                    
                    response = requests.post(API_URL, data=data, files=files)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get("success"):
                            st.success("Generation Complete!")
                            
                            # Display Images
                            pages = result["data"]["pages"]
                            img_cols = st.columns(3)
                            
                            if not pages:
                                st.warning("No images returned.")
                            
                            for i, page in enumerate(pages):
                                with img_cols[i % 3]:
                                    st.image(page["image_url"], caption=f"Page {page['page_number']} ({page['type']})")
                                    st.markdown(f"[Download]({page['image_url']})")
                            
                            # Display Generated Texts
                            st.subheader("Generated Texts")
                            st.json(result["data"]["texts"])
                        else:
                            st.error(f"API Error: {result.get('error')}")
                    else:
                        st.error(f"HTTP Error: {response.status_code} - {response.text}")
                        
                except Exception as e:
                    st.error(f"Client Error: {e}")
