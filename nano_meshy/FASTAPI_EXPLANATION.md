# FastAPI Backend 구조 및 작동 원리 설명 (`main.py`)

이 문서는 Nano Banana 3D 생성 프로젝트의 백엔드인 `main.py`가 어떻게 작동하는지 단계별로 상세히 설명합니다.

## 1. 초기 설정 및 라이브러리 로드

### 필수 라이브러리 및 환경 설정
- **FastAPI**: 웹 서버 및 API 엔드포인트 구축을 위한 메인 프레임워크입니다.
- **Uvicorn**: FastAPI 앱을 실행하기 위한 ASGI 서버입니다.
- **Python-dotenv**: `.env` 파일에서 API 키(`GOOGLE_API_KEY`, `MESHY_API_KEY`)를 안전하게 로드합니다.
- **Requests & URLLib3**: 외부 API(Meshy AI)와 통신하기 위해 사용됩니다. 특히 SSL 통신 오류를 방지하기 위해 `HTTPAdapter`와 `Retry` 로직이 구성되어 있습니다.
- **Google GenAI**: Google의 Gemini 모델을 사용하여 이미지를 생성하는 클라이언트입니다.

### 디렉토리 설정
- **`nano_banana_3d`**: 생성된 중간 결과물(이미지, 3D 모델)을 저장할 폴더를 서버 시작 시 자동으로 생성합니다.

---

## 2. 핵심 유틸리티 함수

### `get_meshy_session()`: 통신 안정성 확보
Meshy AI와의 통신 중 발생할 수 있는 **SSL/TLS 연결 오류(SSLEOFError)**를 방지하기 위해 커스텀 세션을 생성합니다.
- **Retry 전략**: 연결 실패 시 최대 5회까지 재시도합니다.
- **HTTP/HTTPS 어댑터**: 모든 요청에 대해 위 Retry 전략을 적용하는 어댑터를 마운트하여 네트워크 불안정에 대응합니다.

### `file_to_data_uri(image_path)`
로컬에 저장된 이미지 파일을 읽어 **Base64 encoded Data URI** 문자열로 변환합니다.
- Meshy API는 이미지 파일을 직접 업로드받는 대신, 텍스트 형태의 Data URI(`data:image/jpeg;base64,...`)를 요구하기 때문에 이 변환 과정이 필수적입니다.

---

## 3. API 엔드포인트 상세 작동 원리

### (1) `POST /api/generate-nano` (이미지 생성)
사용자가 업로드한 2~3장의 이미지를 바탕으로 "Nano Banana" 스타일의 이미지를 생성합니다.

1. **입력 수신**: 프론트엔드로부터 `image1`(해부학/얼굴), `image2`(포즈/의상), `image3`(스타일-선택) 파일을 받습니다.
2. **이미지 로드**: 받은 바이너리 데이터를 `PIL.Image` 객체로 변환하여 메모리에 로드합니다.
3. **프롬프트 준비**: `nano_banana_3d/prompt_main.md` 파일에서 텍스트 프롬프트를 읽어옵니다. 이 프롬프트는 각 이미지가 어떤 역할을 해야 하는지(구조, 포즈, 스타일) 정의합니다.
4. **Gemini 요청 구성**: 
   - 텍스트 프롬프트와 이미지 객체들을 하나의 리스트(`contents`)로 결합합니다.
   - `gemini-3-pro-image-preview` 모델을 호출합니다.
   - **설정**: 응답 형태를 `['TEXT', 'IMAGE']`로 설정하고, 1:1 비율, 2K 해상도를 요청합니다.
5. **이미지 추출 및 저장**: 응답에서 이미지를 추출하여 로컬 `nano_banana_3d` 폴더에 타임스탬프 기반 파일명으로 저장합니다.
6. **개발자 로그 생성**: 요청에 사용된 프롬프트와 Gemini의 응답 메타데이터를 로그 딕셔너리에 담습니다.
7. **응답 반환**: 성공 시 저장된 이미지 경로, 파일명, 그리고 **개발자 로그**를 반환합니다.

### (2) `POST /api/generate-3d` (3D 모델 생성 요청)
생성된 나노바나나 이미지를 Meshy AI로 전송하여 3D 모델 생성을 시작합니다.

1. **입력 수신**: 이전 단계에서 생성된 이미지의 로컬 경로(`image_path`)를 받습니다.
2. **데이터 변환**: `file_to_data_uri` 함수를 통해 이미지를 Base64 포맷으로 인코딩합니다.
3. **Meshy payload 구성**:
   - `ai_model`: "latest" (최신 모델 사용)
   - `should_remesh`: True (웹 최적화를 위해 토폴로지 재구성)
   - `topology`: "triangle" (삼각형 폴리곤 사용)
   - `target_polycount`: 30000 (폴리곤 수 제한)
4. **API 요청**: `get_meshy_session`으로 생성한 세션을 사용해 Meshy의 `/image-to-3d` 엔드포인트로 POST 요청을 보냅니다.
5. **로그 생성 & 반환**: 요청 payload(이미지 데이터 제외)와 응답 결과를 로그에 담아, 생성된 **Task ID**와 함께 반환합니다.

### (3) `GET /api/status/{task_id}` (진행 상황 확인)
3D 모델 생성은 시간이 걸리는 비동기 작업이므로, 작업 상태를 주기적으로 확인합니다.

1. **요청**: 프론트엔드에서 주기적으로(1초 간격) 이 엔드포인트를 호출합니다.
2. **Meshy 조회**: `task_id`를 사용하여 Meshy API에 현재 상태를 질의합니다.
3. **응답**:
   - `status`: ("PENDING", "IN_PROGRESS", "SUCCEEDED", "FAILED")
   - `progress`: 진행률 (0~100)
   - `model_urls`: 성공 시 다운로드 가능한 GLB 파일 URL 포함
   - `task_error`: 실패 시 에러 메시지 포함

---

## 4. 실행 흐름 요약
1. 사용자가 Streamlit에서 **"이미지 생성"** 버튼 클릭.
2. **Streamlit** -> **FastAPI (`/api/generate-nano`)**: 이미지 파일 전송.
3. **FastAPI** -> **Gemini**: 프롬프트+이미지 전송 -> 결과 이미지 로컬 저장.
4. 사용자가 **"3D 모델 생성"** 버튼 클릭.
5. **Streamlit** -> **FastAPI (`/api/generate-3d`)**: 저장된 이미지 경로 전송.
6. **FastAPI** -> **Meshy AI**: 작업을 등록하고 `task_id` 반환.
7. **Streamlit**: `task_id`를 받아 루프 진입, 1초마다 **FastAPI (`/api/status/{id}`)** 호출.
8. **FastAPI** -> **Meshy AI**: 작업 상태 확인 및 결과(3D URL) 중계.
9. 작업 완료 시 Streamlit이 URL에서 파일을 다운로드하고 화면에 렌더링.
