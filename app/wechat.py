from __future__ import annotations

import hashlib
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

import httpx

from app.tcm_agent import generate_diagnosis_report


WECHAT_XMLNS = None


def _sha1_hex(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def verify_wechat_signature(*, token: str, timestamp: str, nonce: str, signature: str) -> bool:
    data = "".join(sorted([token, timestamp, nonce]))
    return _sha1_hex(data) == signature


async def fetch_wechat_access_token(appid: str, secret: str) -> str:
    url = "https://api.weixin.qq.com/cgi-bin/token"
    params = {"grant_type": "client_credential", "appid": appid, "secret": secret}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"WeChat token fetch failed: {data}")
    return data["access_token"]


async def download_wechat_media(*, access_token: str, media_id: str) -> bytes:
    url = "https://api.weixin.qq.com/cgi-bin/media/get"
    params = {"access_token": access_token, "media_id": media_id, "type": "image"}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.content


def parse_wechat_message(xml_body: bytes) -> dict[str, str]:
    root = ET.fromstring(xml_body)
    msg = {}
    # Common fields:
    for child in root:
        tag = child.tag.split("}")[-1]
        msg[tag] = child.text or ""
    return msg


def build_text_reply(*, to_user: str, from_user: str, content: str) -> str:
    # WeChat expects UTF-8 XML; CDATA helps keep text safe.
    create_time = int(__import__("time").time())
    xml = f"""<xml>
  <ToUserName><![CDATA[{to_user}]]></ToUserName>
  <FromUserName><![CDATA[{from_user}]]></FromUserName>
  <CreateTime>{create_time}</CreateTime>
  <MsgType><![CDATA[text]]></MsgType>
  <Content><![CDATA[{content}]]></Content>
  <FuncFlag>0</FuncFlag>
</xml>"""
    return xml


@dataclass
class WechatReply:
    xml: str


async def handle_wechat_post(xml_body: bytes) -> WechatReply:
    msg = parse_wechat_message(xml_body)

    to_user = msg.get("ToUserName", "")
    from_user = msg.get("FromUserName", "")
    msg_type = msg.get("MsgType", "")

    if msg_type == "text":
        content = msg.get("Content", "")
        result = await generate_diagnosis_report(user_text=content, image_bytes=None)
        return WechatReply(xml=build_text_reply(to_user=from_user, from_user=to_user, content=result.report_text))

    if msg_type == "image":
        media_id = msg.get("MediaId", "")
        if not media_id:
            result_text = "收到图片，但未获取到 media_id，无法继续分析。请重试。"
            return WechatReply(xml=build_text_reply(to_user=from_user, from_user=to_user, content=result_text))

        appid = os.getenv("WECHAT_APPID", "").strip()
        secret = os.getenv("WECHAT_APPSECRET", "").strip()
        if not appid or not secret:
            result_text = "服务器未配置微信应用信息（WECHAT_APPID/WECHAT_APPSECRET），无法完成图片分析。"
            return WechatReply(xml=build_text_reply(to_user=from_user, from_user=to_user, content=result_text))

        access_token = await fetch_wechat_access_token(appid=appid, secret=secret)
        image_bytes = await download_wechat_media(access_token=access_token, media_id=media_id)
        # Some image messages may not contain Caption; fall back to Content if present.
        user_text = msg.get("Caption") or msg.get("Content") or ""
        result = await generate_diagnosis_report(user_text=user_text, image_bytes=image_bytes)
        return WechatReply(xml=build_text_reply(to_user=from_user, from_user=to_user, content=result.report_text))

    # Unsupported message type:
    result_text = "目前只支持文字与图片消息。请发送文字描述或图片（如舌象/面色等）。"
    return WechatReply(xml=build_text_reply(to_user=from_user, from_user=to_user, content=result_text))

