from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI


@dataclass
class TcmDiagnosisResult:
    report_md: str
    report_text: str


def _strip_yaml_frontmatter(markdown: str) -> str:
    """
    移除开头的 YAML frontmatter 区块（--- ... ---）
    """
    return re.sub(r"(?s)^---\s*\n.*?\n---\s*\n?", "", markdown, count=1)


def load_skill_prompt(skill_rel_path: str = ".cursor/skills/tcm-diagnosis/SKILL.md") -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, skill_rel_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        return _strip_yaml_frontmatter(raw).strip()
    except FileNotFoundError:
        # Fall back to a minimal prompt if the skill file is missing.
        return (
            "你是专业的中医辨证分析助手。根据用户提供的文字与图片线索（如舌象、面色、症状描述），"
            "从阴阳五行与五运六气等角度进行辨证分析，并输出包含：辨证结论、证候要点、可能原因、调理建议、"
            "注意事项（不替代就医）。"
        )


def _rule_based_analysis(user_text: str) -> str:
    """
    规则版兜底分析：仅基于文字描述，不对图片做推断，
    避免对大模型依赖过强时服务不可用。
    """
    text = (user_text or "").strip()
    if not text:
        return "未收到有效的文字描述。请补充：主要不适、持续时间、诱因、伴随症状（如口苦/口干/便秘/腹泻/怕冷怕热等）。"

    # Extremely small heuristic mapping for first-pass diagnosis.
    heat_markers = ["上火", "口苦", "口臭", "便秘", "口干", "咽干", "舌红", "舌苔黄", "痘", "烦躁", "睡不着"]
    cold_markers = ["怕冷", "畏寒", "手脚冰冷", "腹泻", "腹痛", "舌淡", "舌苔白", "胃寒"]
    damp_markers = ["困重", "黏腻", "油腻", "痰多", "容易湿疹", "身体沉重", "水肿", "舌苔腻", "腹胀"]

    heat_hit = any(m in text for m in heat_markers)
    cold_hit = any(m in text for m in cold_markers)
    damp_hit = any(m in text for m in damp_markers)

    # Choose a simple pattern.
    if heat_hit and not cold_hit:
        pattern = "偏热（可见：口苦/口干/便秘/舌红或苔黄等）"
        key = "多与心火、肝火上炎或胃火炽盛相关；亦可能夹湿热。"
        rec = "清热利火、疏肝解郁、兼顾祛湿。可调整作息与饮食，少辛辣油腻，避免熬夜。"
    elif cold_hit and not heat_hit:
        pattern = "偏寒（可见：怕冷/畏寒/腹泻等）"
        key = "多与阳气不足、寒邪内侵或脾阳受损相关。"
        rec = "温中散寒、健脾助运。注意保暖，减少生冷食物，适度运动以助阳。"
    elif damp_hit and not (heat_hit or cold_hit):
        pattern = "偏湿（可见：困重/痰湿/舌苔腻等）"
        key = "多与脾失健运、湿阻中焦或痰湿内生相关。"
        rec = "健脾化湿、通利气机。规律饮食，减少甜腻与酒类，保证睡眠。"
    else:
        pattern = "证候尚需进一步辨证（文字线索不够明确）"
        key = "建议补充舌象（舌色、舌苔厚薄与颜色、是否腻）、脉象（如描述：脉沉/细/弦/滑）、大便与小便情况。"
        rec = "先从作息与饮食调理入手：清淡、规律、适量运动；若不适持续或加重请尽快就医。"

    # Yin-yang / five-elements framing (still generic).
    yinyang = "多见“阴阳失衡”的倾向：偏热则阳偏亢、偏寒则阳不足、偏湿则运化失司。"
    five_elements = "五行角度可参考：肝木疏泄、脾土运化、心火通明、肾水封藏等。结合症状偏向进一步定位。"

    return (
        "# 辨证分析（规则版，基于文字）\n"
        f"## 辨证结论\n{pattern}\n\n"
        "## 证候要点\n"
        f"- {key}\n"
        f"- {yinyang}\n"
        f"- {five_elements}\n\n"
        "## 可能原因（参考）\n"
        "- 作息不规律、饮食偏嗜、情绪波动、季节气候变化等可能促发。\n\n"
        "## 调理建议\n"
        f"- {rec}\n"
        "- 可增加温热规律饮食与轻度出汗运动（如散步），避免强刺激。\n\n"
        "## 注意事项\n"
        "- 本报告仅供健康管理与参考，不能替代医生诊断与治疗。\n"
        "- 若出现高热、持续剧烈疼痛、呕血/便血、明显呼吸困难等，请及时就医。\n"
    )


def _format_for_wechat(report_md: str) -> str:
    # 将 Markdown 报告转换为微信更易读的纯文本格式。
    text = report_md
    text = re.sub(r"#+\s*", "", text)  # headings
    text = re.sub(r"\*\*", "", text)  # bold
    text = text.replace("- ", "• ")
    text = text.replace("\n\n", "\n")
    return text.strip()


def _derive_base_url(api_url: str) -> str:
    """
    将 OpenAI 兼容的 chat completions 地址转换为 LangChain 可用的基础 base_url。

    例如：
      https://api.deepseek.com/v1/chat/completions -> https://api.deepseek.com
    """
    api_url = (api_url or "").strip().rstrip("/")
    if not api_url:
        return api_url
    if "/v1/" in api_url:
        return api_url.split("/v1/")[0]
    if api_url.endswith("/v1"):
        return api_url[: -len("/v1")]
    return api_url


async def _call_llm_langchain(
    *,
    api_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_text: str,
    image_bytes: Optional[bytes],
) -> str:
    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=_derive_base_url(api_url),
        temperature=0.4,
    )

    text = user_text or "（无文字输入）"
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"
        human = HumanMessage(
            content=[
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        )
    else:
        human = HumanMessage(content=text)

    resp = await llm.ainvoke([SystemMessage(content=system_prompt), human])
    return getattr(resp, "content", str(resp))


async def generate_diagnosis_report(user_text: str, image_bytes: bytes | None) -> TcmDiagnosisResult:
    system_prompt = load_skill_prompt()

    api_key = (os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("LLM_API_KEY", "")).strip()
    api_url = (
        os.getenv("DEEPSEEK_API_URL", "") or os.getenv("LLM_API_URL", "") or "https://api.deepseek.com/v1/chat/completions"
    ).strip()
    model = (os.getenv("DEEPSEEK_MODEL", "") or os.getenv("LLM_MODEL", "") or "deepseek-chat").strip()
    vision_model = (os.getenv("DEEPSEEK_VISION_MODEL", "") or model).strip()

    if not api_key:
        report_md = _rule_based_analysis(user_text)
        return TcmDiagnosisResult(report_md=report_md, report_text=_format_for_wechat(report_md))

    try:
        # When image exists, try a vision-capable model first. If it fails, fall back to text-only.
        report_md = await _call_llm_langchain(
            api_url=api_url,
            api_key=api_key,
            model=vision_model if image_bytes else model,
            system_prompt=system_prompt,
            user_text=user_text,
            image_bytes=image_bytes,
        )
    except Exception:
        try:
            report_md = await _call_llm_langchain(
                api_url=api_url,
                api_key=api_key,
                model=model,
                system_prompt=system_prompt,
                user_text=user_text,
                image_bytes=None,
            )
        except Exception:
            report_md = _rule_based_analysis(user_text)
    return TcmDiagnosisResult(report_md=report_md, report_text=_format_for_wechat(report_md))

