"""通义多模态 OCR/图片理解（云端 API，无需本地模型）"""
import base64

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Provider
from app.services.llm_client import get_openai_client


class OCRService:
    def __init__(self, provider: Provider, model: str):
        self.provider = provider
        self.model = model
        self.client = get_openai_client(provider)

    def describe_image(self, image_bytes: bytes, prompt: str) -> str:
        """OpenAI 兼容视觉接口：传图片 data URL，返回文本描述"""
        b64 = base64.b64encode(image_bytes).decode("ascii")
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            max_tokens=2000,
        )
        return resp.choices[0].message.content or ""

    @classmethod
    def resolve(cls, db: Session) -> "OCRService | None":
        """按配置解析 OCR 服务商；未启用/未配置 Key 时返回 None"""
        provider = db.get(Provider, settings.ocr_provider_id)
        if not provider or not provider.enabled or not provider.api_key:
            return None
        return cls(provider, settings.ocr_model)


OCR_PROMPT = (
    "请识别这张图片。要求：1) 逐字转写图中所有文字，保留原有结构与顺序；"
    "2) 若是图表/流程图/表格，用 Markdown 表格或结构化文字描述其内容；"
    "3) 若是普通照片/示意图，简要描述画面内容。直接输出结果，不要附加解释。"
)
