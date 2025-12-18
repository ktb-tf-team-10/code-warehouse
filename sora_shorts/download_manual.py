import os
import requests
from pathlib import Path
from dotenv import load_dotenv

def manual_download():
    # 1. 설정 로드
    # 사용자의 실행 위치(sora_shorts/download_manual.py)를 고려하여
    # 현재 파일이 있는 폴더 내의 .env를 찾도록 수정
    current_dir = Path(__file__).parent
    env_path = current_dir / ".env"
    
    print(f"🔍 Looking for .env at: {env_path.resolve()}")

    if not env_path.exists():
        print(f"❌ Error: .env file not found at {env_path}")
        return

    load_dotenv(dotenv_path=env_path, override=True)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: API Key not found in .env variable")
        return

    # 로그에서 확인된 Video ID
    video_id = "video_6943adef39f88191b2c56e225f48cffb0f68271cb1f6775b"
    
    # Sora API 다운로드 엔드포인트
    url = f"https://api.openai.com/v1/videos/{video_id}/content"
    headers = {
        "Authorization": f"Bearer {api_key}"
    }

    print(f"📥 Downloading video: {video_id}...")
    print(f"🔗 Endpoint: {url}")

    try:
        # 스트림 모드로 다운로드
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status() 
            
            output_filename = "wedding_shorts_final.mp4"
            with open(output_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
                    
        print(f"✅ Download Complete: {output_filename}")
        print(f"📁 Saved to: {os.path.abspath(output_filename)}")

    except requests.exceptions.HTTPError as err:
        print(f"❌ HTTP Error: {err}")
        print(f"Response: {r.text}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    manual_download()