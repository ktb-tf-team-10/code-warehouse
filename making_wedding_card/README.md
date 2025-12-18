# Wedding OS - Model API Specification

이 문서는 청첩장 생성 서비스(Wedding OS)의 로컬 모델 API 명세서입니다.

## 기본 정보
- **Title**: Wedding OS - Model API
- **Description**: 청첩장 텍스트 및 이미지 생성을 위한 AI 모델 연동 API Server.
- **Version**: 1.0.0
- **Base URL**: `http://localhost:8000` (로컬 실행 시)

---

## 1. 헬스 체크 (Health Check)
서버가 정상적으로 동작 중인지 확인합니다.

- **URL**: `/health`
- **Method**: `GET`
- **Response**:
  ```json
  {
    "status": "ok"
  }
  ```

---

## 2. 텍스트 생성 (Generate Text)
Gemini Flash 2.5를 사용하여 청첩장 문구를 생성합니다. 
`tone`에 따라 다른 분위기의 문구를 생성할 수 있습니다.

- **URL**: `/api/generate-text`
- **Method**: `POST`
- **Content-Type**: `application/json`

### Request Body
| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `tone` | string | No | 문구 분위기 (기본: "romantic")<br>옵션: `formal`, `casual`, `modern`, `classic`, `romantic`, `minimal` | `"romantic"` |
| `groom_name` | string | Yes | 신랑 이름 | `"이철수"` |
| `bride_name` | string | Yes | 신부 이름 | `"김영희"` |
| `groom_father` | string | No | 신랑 아버지 이름 | `"이아버지"` |
| `groom_mother` | string | No | 신랑 어머니 이름 | `"김어머니"` |
| `bride_father` | string | No | 신부 아버지 이름 | `"김아버지"` |
| `bride_mother` | string | No | 신부 어머니 이름 | `"박어머니"` |
| `venue` | string | Yes | 예식장 이름 | `"더 채플"` |
| `wedding_date` | string | Yes | 예식 날짜 | `"2025년 5월 20일"` |
| `wedding_time` | string | Yes | 예식 시간 | `"오후 2시"` |
| `address` | string | No | 예식장 주소 (지도 등 생성 시 활용) | `"서울시 강남구..."` |

### Response Structure (JSON)
```json
{
  "success": true,
  "data": {
    "greetings": [
      "저희 두 사람의 새로운 시작을 축복해 주세요.",
      "사랑으로 맺어진 저희 두 사람이 하나가 됩니다.",
      "따스한 봄날, 저희의 결혼식에 초대합니다."
    ],
    "invitations": [
      "귀한 걸음 하시어 저희의 앞날을 축복해 주시면 더없는 기쁨이겠습니다.",
      "사랑과 믿음으로 지켜온 저희의 약속을 증명하는 자리에 함께해 주세요.",
      "서로를 아끼고 사랑하며 행복하게 살겠습니다."
    ],
    "location": "강남역 1번 출구에서 셔틀버스를 운행합니다. 많은 이용 바랍니다.",
    "closing": [
      "감사합니다.",
      "행복하게 살겠습니다.",
      "저희의 첫걸음을 응원해 주세요."
    ]
  }
}
```

---

## 3. 청첩장 이미지 생성 (Generate Invitation)
Gemini(문구)와 Google Imagen/Gemini(디자인)를 조합하여 최종 청첩장 이미지들을 생성합니다.

- **URL**: `/api/generate-invitation`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`

### Request Parameters (Form Data)
| Field | Type | Required | Description |
|---|---|---|---|
| `wedding_image` | File | **Yes** | 웨딩 사진 파일 (JPG/PNG) |
| `style_image` | File | **Yes** | 스타일 참조 이미지 파일 |
| `tone` | string | **Yes** | 디자인 톤 |
| `groom_name` | string | **Yes** | 신랑 이름 |
| `bride_name` | string | **Yes** | 신부 이름 |
| `venue` | string | **Yes** | 예식장 이름 |
| `wedding_date` | string | **Yes** | 예식 날짜 |
| `wedding_time` | string | **Yes** | 예식 시간 |
| `address` | string | **Yes** | 예식장 주소 |
| `model_name` | string | No | 사용할 모델명 (기본: `models/gemini-3-pro-image-preview`) |
| `latitude` | float | No | 예식장 위도 (지도 생성용) |
| `longitude` | float | No | 예식장 경도 (지도 생성용) |
| `floor_hall` | string | No | 예식장 홀 정보 |

### Response Structure (JSON)
```json
{
  "success": true,
  "data": {
    "pages": [
      {
        "page_number": 1,
        "image_url": "http://localhost:8000/static/generated_images/design_uuid_1.png",
        "type": "cover",
        "description": "웨딩 사진 커버"
      },
      {
        "page_number": 2,
        "image_url": "http://localhost:8000/static/generated_images/design_uuid_2.png",
        "type": "greeting",
        "description": "인사말"
      },
      {
        "page_number": 3,
        "image_url": "http://localhost:8000/static/generated_images/design_uuid_3.png",
        "type": "invitation",
        "description": "초대 문구"
      },
      {
        "page_number": 4,
        "image_url": "http://localhost:8000/static/generated_images/design_uuid_4.png",
        "type": "location",
        "description": "장소 안내"
      },
      {
        "page_number": 5,
        "image_url": "http://localhost:8000/static/generated_images/design_uuid_5.png",
        "type": "closing",
        "description": "마무리 인사"
      }
    ],
    "texts": {
      "greeting": "생성된 인사말 텍스트...",
      "invitation": "생성된 초대 문구 텍스트...",
      "location": "생성된 장소 안내 텍스트...",
      "closing": "생성된 마무리 인사 텍스트..."
    },
    "model_used": "models/gemini-3-pro-image-preview"
  }
}
```

---

## 4. 청첩장 생성 테스트 (Generate Invitation Test) (Nanobanana Mode)
다양한 모델을 테스트하고 **프롬프트 오버라이드**를 통해 튜닝할 수 있는 개발용 엔드포인트입니다. Nanobanana 모드에서는 각 페이지별 프롬프트 수정이 가능합니다.

- **URL**: `/api/generate-invitation-test`
- **Method**: `POST`
- **Content-Type**: `multipart/form-data`

### Request Parameters (Form Data)
| Field | Type | Required | Description / Default |
|---|---|---|---|
| `model_type` | string | No | `nanobanana` (기본), `flash2.5`, `imagen-4.0-generate`, `gemini3.0` |
| `wedding_image` | File | No | 웨딩 사진 |
| `style_image` | File | No | 스타일 참조 사진 |
| `prompt_override_1` | string | No | (Nanobanana) 1페이지 프롬프트 덮어쓰기 |
| `prompt_override_2` | string | No | (Nanobanana) 2페이지 프롬프트 덮어쓰기 |
| `prompt_override_3` | string | No | (Nanobanana) 3페이지 프롬프트 덮어쓰기 |
| `border_design_id` | string | No | 테두리 디자인 (기본: `classic_gold`) |
| *기본 정보 필드들* | string | No | `groom_name`, `bride_name`, `venue`, `date`, `time`, `address` 등 |

### Response Structure (JSON) - Nanobanana Mode
```json
{
  "success": true,
  "data": {
    "pages": [
      {
        "page_number": 1,
        "image_url": "http://localhost:8000/static/generated_images/invitation-page1_uuid.jpg",
        "type": "cover"
      },
      {
        "page_number": 2,
        "image_url": "http://localhost:8000/static/generated_images/invitation-page2_uuid.jpg",
        "type": "content"
      },
      {
        "page_number": 3,
        "image_url": "http://localhost:8000/static/generated_images/invitation-page3_uuid.jpg",
        "type": "location"
      }
    ],
    "texts": {
      "greeting": "...",
      "invitation": "...",
      "location": "..."
    }
  }
}
```

## 에러 응답 (Common Error Response)
모든 엔드포인트 공통 오류 형식입니다.
```json
{
  "success": false,
  "error": "Error message description",
  "detail": [ ... ],
  "traceback": "..."
}
```
