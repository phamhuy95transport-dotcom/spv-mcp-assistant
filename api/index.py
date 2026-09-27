import json
import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="SPV Telegram MCP Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxpzToUbts1X2Z1VftlAlR3tw44If9vVEmJ34KtMdXioinq60pkUtG1RXqgCbhmKis79w/exec"

# Định nghĩa 2 Tool theo chuẩn JSON-RPC của MCP
TOOLS = [
    {
        "name": "get_pending_messages",
        "description": "Lấy danh sách các tin nhắn và hình ảnh chứng từ đang chờ xử lý từ Google Sheets.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "send_reply_and_resolve",
        "description": "Gửi câu trả lời về Telegram của khách và cập nhật hoàn thành trên Google Sheets.",
        "inputSchema": {
            "type": "object",
            "required": ["user_id", "reply_text", "row_index"],
            "properties": {
                "user_id": {"type": "string", "description": "ID người nhận trên Telegram"},
                "reply_text": {"type": "string", "description": "Nội dung phản hồi cần gửi"},
                "row_index": {"type": "integer", "description": "Số dòng trên Sheet"}
            }
        }
    }
]

@app.get("/sse")
async def sse_endpoint(request: Request):
    async def event_generator():
        # Gửi endpoint nhận request RPC về cho Gemini
        endpoint_url = str(request.base_url) + "message"
        yield {"event": "endpoint", "data": endpoint_url}
    return EventSourceResponse(event_generator())

@app.post("/message")
async def handle_message(request: Request):
    data = await request.json()
    req_id = data.get("id")
    method = data.get("method")

    # 1. Bắt tay ban đầu (initialize)
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "SPV-Telegram-Assistant", "version": "1.0.0"}
            }
        }

    # 2. Báo cho Gemini biết các Tool khả dụng
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }

    # 3. Khi Gemini gọi Tool
    elif method == "tools/call":
        params = data.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})

        if name == "get_pending_messages":
            res = requests.get(f"{APPS_SCRIPT_URL}?action=get_pending_messages", timeout=15)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": res.text}]}
            }

        elif name == "send_reply_and_resolve":
            payload = {
                "action": "reply_message",
                "user_id": str(arguments.get("user_id")),
                "reply_text": arguments.get("reply_text"),
                "row_index": int(arguments.get("row_index", 0))
            }
            res = requests.post(APPS_SCRIPT_URL, json=payload, timeout=15)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": res.text}]}
            }

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}
