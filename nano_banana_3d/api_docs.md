최대 14개의 참조 이미지 사용
Gemini 3 Pro 프리뷰를 사용하면 최대 14개의 참조 이미지를 혼합할 수 있습니다. 이러한 14개의 이미지에는 다음이 포함될 수 있습니다.

최종 이미지에 포함할 충실도가 높은 객체의 이미지(최대 6개)
캐릭터 일관성을 유지하기 위한 최대 5개의 인물 이미지

Python
JavaScript
Go
자바
REST

from google import genai
from google.genai import types
from PIL import Image

prompt = "An office group photo of these people, they are making funny faces."
aspect_ratio = "5:4" # "1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"
resolution = "2K" # "1K", "2K", "4K"

client = genai.Client()

response = client.models.generate_content(
    model="gemini-3-pro-image-preview",
    contents=[
        prompt,
        Image.open('person1.png'),
        Image.open('person2.png'),
        Image.open('person3.png'),
        Image.open('person4.png'),
        Image.open('person5.png'),
    ],
    config=types.GenerateContentConfig(
        response_modalities=['TEXT', 'IMAGE'],
        image_config=types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=resolution
        ),
    )
)

for part in response.parts:
    if part.text is not None:
        print(part.text)
    elif image:= part.as_image():
        image.save("office.png")

