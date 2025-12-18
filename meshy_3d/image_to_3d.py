import base64
import mimetypes
import os
import time
from typing import Dict, Any, Optional

import requests

MESHY_BASE = "https://api.meshy.ai/openapi/v1"
CREATE_ENDPOINT = f"{MESHY_BASE}/image-to-3d"


def file_to_data_uri(image_path: str) -> str:
    """로컬 이미지 파일을 data URI로 변환"""
    mime_type, _ = mimetypes.guess_type(image_path)
    if mime_type not in ("image/jpeg", "image/png"):
        raise ValueError(f"지원하지 않는 이미지 형식입니다: {mime_type} (jpg/jpeg/png만 지원)")

    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{b64}"


def create_image_to_3d_task(
    api_key: str,
    image_url: str,
    *,
    ai_model: str = "latest",
    should_texture: bool = True,
    enable_pbr: bool = False,
    should_remesh: bool = True,
    topology: str = "triangle",
    target_polycount: int = 30000,
    symmetry_mode: str = "auto",
    save_pre_remeshed_model: bool = False,
    pose_mode: str = ""
) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}

    payload: Dict[str, Any] = {
        "image_url": image_url,
        "ai_model": ai_model,
        "should_texture": should_texture,
        "enable_pbr": enable_pbr,
        "should_remesh": should_remesh,
        "symmetry_mode": symmetry_mode,
        "pose_mode": pose_mode,
    }

    # remesh를 켠 경우에만 topology/polycount 옵션이 의미 있음(문서 설명)
    if should_remesh:
        payload["topology"] = topology
        payload["target_polycount"] = target_polycount
        payload["save_pre_remeshed_model"] = save_pre_remeshed_model

    resp = requests.post(CREATE_ENDPOINT, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    data = resp.json()
    task_id = data["result"]
    return task_id


def get_task(api_key: str, task_id: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"{CREATE_ENDPOINT}/{task_id}"
    resp = requests.get(url, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()


def wait_for_task(
    api_key: str,
    task_id: str,
    poll_interval: float = 3.0,
    timeout_sec: int = 600
) -> Dict[str, Any]:
    """SUCCEEDED/FAILED/CANCELED 중 하나가 될 때까지 대기"""
    start = time.time()

    while True:
        task = get_task(api_key, task_id)
        status = task.get("status")
        progress = task.get("progress", 0)

        print(f"[{task_id}] status={status} progress={progress}%")

        if status in ("SUCCEEDED", "FAILED", "CANCELED"):
            return task

        if time.time() - start > timeout_sec:
            raise TimeoutError(f"시간 초과: {timeout_sec}s 안에 작업이 끝나지 않았습니다.")

        time.sleep(poll_interval)


def download_file(url: str, save_path: str) -> None:
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


if __name__ == "__main__":
    MESHY_API_KEY = ""
    LOCAL_IMAGE_PATH = r"/Users/swoo64/Desktop/Wedding_3D/api_code/Gemini_Generated_Image_3lysjp3lysjp3lys.png"  # 로컬 이미지 경로로 변경
    OUTPUT_GLB_PATH = r"/Users/swoo64/Desktop/Wedding_3D/api_code/test_model2.glb"  # 저장 파일명/경로

    # 1) 로컬 이미지를 data URI로
    image_data_uri = file_to_data_uri(LOCAL_IMAGE_PATH)

    # 2) 청첩장 웹용 추천 옵션(가벼운 기본형)
    task_id = create_image_to_3d_task(
        api_key=YOUR_API_KEY,
        image_url=image_data_uri,
        ai_model="latest",
        should_texture=True,
        enable_pbr=False,          # 기본은 OFF (가볍게)
        should_remesh=True,        # 웹용 최적화
        topology="triangle",       # 웹/엔진 표준
        target_polycount=100000,    # 기본값 = 30000
        symmetry_mode="auto",
        save_pre_remeshed_model=False,
        pose_mode=""
    )

    print("Created task:", task_id)

    # 3) 완료될 때까지 폴링
    task = wait_for_task(YOUR_API_KEY, task_id, poll_interval=3.0, timeout_sec=1200)

    if task["status"] != "SUCCEEDED":
        # 실패/취소 시 메시지 확인(실패면 task_error.message에 들어올 수 있음)
        err = (task.get("task_error") or {}).get("message", "")
        raise RuntimeError(f"Task ended with status={task['status']} message={err}")

    # 4) GLB 다운로드
    glb_url: Optional[str] = (task.get("model_urls") or {}).get("glb")
    if not glb_url:
        raise RuntimeError("SUCCEEDED인데 model_urls.glb가 없습니다.")

    download_file(glb_url, OUTPUT_GLB_PATH)
    print("Saved GLB to:", OUTPUT_GLB_PATH)