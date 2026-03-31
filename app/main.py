from __future__ import annotations

import os

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse

from app.wechat import handle_wechat_post, verify_wechat_signature
from app.tcm_agent import generate_diagnosis_report

try:
    # Auto-load environment variables from .env when present.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # If python-dotenv isn't installed or .env is absent, continue normally.
    pass

app = FastAPI(title="TcmAiAgent", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/diagnose")
async def api_diagnose(
    text: str = Form(""),
    image: UploadFile | None = File(default=None),
) -> JSONResponse:
    image_bytes: bytes | None = None
    if image is not None:
        image_bytes = await image.read()

    result = await generate_diagnosis_report(user_text=text, image_bytes=image_bytes)
    return JSONResponse({"report_md": result.report_md, "report_text": result.report_text})


@app.get("/wechat")
async def wechat_get(request: Request) -> PlainTextResponse:
    """
    WeChat verification:
    - signature
    - timestamp
    - nonce
    - echostr
    """
    query = dict(request.query_params)
    token = os.getenv("WECHAT_TOKEN", "").strip()
    if not token:
        return PlainTextResponse("Missing WECHAT_TOKEN", status_code=500)

    ok = verify_wechat_signature(
        token=token,
        timestamp=query.get("timestamp", ""),
        nonce=query.get("nonce", ""),
        signature=query.get("signature", ""),
    )
    if ok:
        return PlainTextResponse(query.get("echostr", ""))
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/wechat")
async def wechat_post(request: Request) -> PlainTextResponse:
    xml_body = await request.body()
    reply = await handle_wechat_post(xml_body)
    return PlainTextResponse(reply.xml)

