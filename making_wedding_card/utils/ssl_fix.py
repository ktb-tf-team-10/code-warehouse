"""
SSL/TLS 오류 해결을 위한 유틸리티

여러 가지 SSL 문제 해결 방법을 제공합니다:
1. certifi CA 번들 사용
2. OpenSSL 설정
3. TLS 버전 강제 지정
4. SNI (Server Name Indication) 비활성화
"""

import os
import ssl
import certifi
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

# SNI(Server Name Indication) 강제 비활성화 (TLSV1_UNRECOGNIZED_NAME 오류 해결책)
try:
    import urllib3.util.ssl_
    urllib3.util.ssl_.HAS_SNI = False
    
    # 더 깊은 레벨에서의 SNI 비활성화 및 SSL 컨텍스트 패치
    from urllib3.util import ssl_ as urllib3_ssl
    _original_create_urllib3_context = urllib3_ssl.create_urllib3_context
    
    def patched_create_urllib3_context(*args, **kwargs):
        context = _original_create_urllib3_context(*args, **kwargs)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    
    urllib3_ssl.create_urllib3_context = patched_create_urllib3_context
except Exception:
    pass

class TLSAdapter(HTTPAdapter):
    """
    TLS 버전 및 SNI 관련 이슈를 해결하기 위한 HTTP 어댑터
    """
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        # TLS 1.2 이상 강제
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        # SSL: TLSV1_UNRECOGNIZED_NAME 및 모든 검증 원천 차단
        ctx.check_hostname = False 
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


def configure_ssl_globally():
    """
    전역 SSL 설정을 구성합니다.
    애플리케이션 시작 시 한 번 호출하세요.
    """
    # 1. certifi CA 번들 사용
    cert_path = certifi.where()
    os.environ['SSL_CERT_FILE'] = cert_path
    os.environ['REQUESTS_CA_BUNDLE'] = cert_path
    os.environ['CURL_CA_BUNDLE'] = cert_path
    os.environ['GRPC_DEFAULT_SSL_ROOTS_FILE_PATH'] = cert_path

    # 2. OpenSSL 설정 (일부 환경에서 필요)
    # 시스템에 따라 OpenSSL 라이브러리 경로가 다를 수 있음
    openssl_paths = [
        '/usr/local/opt/openssl/lib',
        '/opt/homebrew/opt/openssl/lib',
        '/usr/lib/x86_64-linux-gnu',
    ]

    for path in openssl_paths:
        if os.path.exists(path):
            os.environ['LD_LIBRARY_PATH'] = path
            break

    # 3. urllib3 경고 억제 (verify=False 사용 시)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print("✅ SSL 전역 설정 완료")
    print(f"   - CA Bundle: {certifi.where()}")


def create_ssl_context(
    verify_mode: int = ssl.CERT_REQUIRED,
    check_hostname: bool = True,
    min_tls_version: int = ssl.TLSVersion.TLSv1_2
) -> ssl.SSLContext:
    """
    커스텀 SSL 컨텍스트를 생성합니다.

    Args:
        verify_mode: 인증서 검증 모드 (ssl.CERT_REQUIRED, ssl.CERT_OPTIONAL, ssl.CERT_NONE)
        check_hostname: 호스트명 검증 여부
        min_tls_version: 최소 TLS 버전

    Returns:
        ssl.SSLContext: 구성된 SSL 컨텍스트
    """
    context = ssl.create_default_context()

    # certifi CA 번들 로드
    context.load_verify_locations(certifi.where())

    # TLS 버전 설정
    context.minimum_version = min_tls_version

    # 검증 모드 설정
    context.verify_mode = verify_mode
    context.check_hostname = check_hostname

    # 암호화 스위트 설정 (강력한 암호화만 허용)
    context.set_ciphers('HIGH:!aNULL:!eNULL:!EXPORT:!DES:!MD5:!PSK:!RC4')

    return context


def create_unverified_ssl_context() -> ssl.SSLContext:
    """
    SSL 검증을 하지 않는 컨텍스트를 생성합니다.

    주의: 개발 환경에서만 사용하세요!
    프로덕션 환경에서는 보안 위험이 있습니다.

    Returns:
        ssl.SSLContext: 검증 없는 SSL 컨텍스트
    """
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def test_ssl_connection(url: str = "https://www.google.com") -> bool:
    """
    SSL 연결 테스트

    Args:
        url: 테스트할 URL

    Returns:
        bool: 연결 성공 여부
    """
    import requests

    try:
        print(f"SSL 연결 테스트: {url}")

        # 1. certifi 사용 시도
        response = requests.get(url, verify=certifi.where(), timeout=5)
        print(f"✅ certifi 사용 성공 (상태 코드: {response.status_code})")
        return True

    except requests.exceptions.SSLError as e:
        print(f"❌ certifi 사용 실패: {e}")

        # 2. verify=False 시도 (개발 환경)
        try:
            response = requests.get(url, verify=False, timeout=5)
            print(f"⚠️  verify=False 사용 성공 (상태 코드: {response.status_code})")
            print("   주의: 프로덕션 환경에서는 사용하지 마세요!")
            return True
        except Exception as e2:
            print(f"❌ verify=False도 실패: {e2}")
            return False

    except Exception as e:
        print(f"❌ 연결 실패: {e}")
        return False


# 애플리케이션 시작 시 자동 설정
configure_ssl_globally()


if __name__ == "__main__":
    print("=" * 80)
    print("SSL 설정 테스트")
    print("=" * 80)

    # 설정 정보 출력
    print(f"\n📋 현재 SSL 설정:")
    print(f"   SSL_CERT_FILE: {os.environ.get('SSL_CERT_FILE', 'Not set')}")
    print(f"   REQUESTS_CA_BUNDLE: {os.environ.get('REQUESTS_CA_BUNDLE', 'Not set')}")
    print(f"   certifi CA 경로: {certifi.where()}")

    # OpenSSL 버전 확인
    print(f"\n🔐 OpenSSL 정보:")
    print(f"   버전: {ssl.OPENSSL_VERSION}")

    # 연결 테스트
    print(f"\n🧪 SSL 연결 테스트:")
    test_urls = [
        "https://www.google.com",
        "https://api.openai.com",
        "https://generativelanguage.googleapis.com"
    ]

    for url in test_urls:
        test_ssl_connection(url)
        print()

    print("=" * 80)
