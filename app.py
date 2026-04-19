import os
import threading
import time

from dotenv import load_dotenv
from flask import Flask, request

from agents.outline_agent import generate_outline_text
from agents.ppt_agent import outline_to_plan
from bot.feishu_client import (
    fetch_recent_group_messages,
    get_tenant_access_token,
    send_file_message,
    send_text_message,
    upload_file,
)
from bot.message_parser import clean_group_messages, get_event_chat_id, is_ppt_task, parse_event_message_text
from render.pptx_renderer import render_plan_to_pptx

load_dotenv()

app = Flask(__name__)

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")
PORT = int(os.getenv("PORT", "3000"))

EVENT_TTL_SECONDS = int(os.getenv("EVENT_TTL_SECONDS", "600"))

_processed_events: dict[str, float] = {}
_inflight_chats: set[str] = set()
_guard_lock = threading.Lock()


def _prune_processed_events(now: float) -> None:
    expired = [k for k, ts in _processed_events.items() if now - ts > EVENT_TTL_SECONDS]
    for key in expired:
        _processed_events.pop(key, None)


def _build_event_key(data: dict, event: dict, message: dict, chat_id: str) -> str:
    header = data.get("header", {})
    event_id = header.get("event_id")
    if event_id:
        return f"event:{event_id}"

    message_id = message.get("message_id")
    if message_id:
        return f"message:{message_id}"

    create_time = message.get("create_time", "")
    sender_id = message.get("sender", {}).get("sender_id", {})
    if isinstance(sender_id, dict):
        sender_id = sender_id.get("open_id") or sender_id.get("user_id") or sender_id.get("union_id") or ""
    return f"fallback:{chat_id}:{create_time}:{sender_id}"


def _acquire_event_once(event_key: str) -> bool:
    now = time.time()
    with _guard_lock:
        _prune_processed_events(now)
        if event_key in _processed_events:
            return False
        _processed_events[event_key] = now
        return True


def _acquire_chat_lock(chat_id: str) -> bool:
    with _guard_lock:
        if chat_id in _inflight_chats:
            return False
        _inflight_chats.add(chat_id)
        return True


def _release_chat_lock(chat_id: str) -> None:
    with _guard_lock:
        _inflight_chats.discard(chat_id)


def _process_ppt_task(event: dict, message: dict, text: str, chat_id: str) -> None:
    if not _acquire_chat_lock(chat_id):
        return

    try:
        token = get_tenant_access_token(FEISHU_APP_ID, FEISHU_APP_SECRET)
        send_text_message(token, chat_id, "收到，我正在读取最近 30 分钟的群聊消息，用于生成 PPT 输入。")

        messages = fetch_recent_group_messages(token=token, chat_id=chat_id, minutes=30, page_size=50)
        cleaned_text = clean_group_messages(messages)

        if not cleaned_text:
            send_text_message(token, chat_id, "我没有读取到最近 30 分钟内可用于生成 PPT 的文本消息。")
            return

        send_text_message(token, chat_id, "我已读取到群聊内容，正在调用 AI 生成 PPT 大纲，请稍等。")

        outline_text = generate_outline_text(
            chat_context=cleaned_text,
            user_instruction=text,
            api_key=SILICONFLOW_API_KEY,
            model=SILICONFLOW_MODEL,
        )
        plan = outline_to_plan(outline_text)

        send_text_message(token, chat_id, "大纲已生成，正在渲染 PPT 文件并上传飞书，请稍等。")
        pptx_path = render_plan_to_pptx(plan, output_dir="temp")
        file_key = upload_file(token, pptx_path)
        send_file_message(token, chat_id, file_key)

        send_text_message(token, chat_id, f"PPT 已生成并发送，共 {len(plan.slides)} 页。")

    except Exception as e:
        print("处理事件失败：", repr(e))
        try:
            token = get_tenant_access_token(FEISHU_APP_ID, FEISHU_APP_SECRET)
            send_text_message(token, chat_id, f"处理失败：{str(e)}")
        except Exception as inner_e:
            print("发送错误消息也失败：", repr(inner_e))
    finally:
        _release_chat_lock(chat_id)


@app.route("/callback", methods=["POST"])
def callback():
    data = request.json or {}

    if "challenge" in data:
        return {"challenge": data["challenge"]}

    try:
        event = data.get("event", {})
        message = event.get("message", {})
        text = parse_event_message_text(message)
        chat_id = get_event_chat_id(event)

        if not is_ppt_task(text):
            return {"code": 0}

        event_key = _build_event_key(data, event, message, chat_id)
        if not _acquire_event_once(event_key):
            return {"code": 0}

        worker = threading.Thread(
            target=_process_ppt_task,
            args=(event, message, text, chat_id),
            daemon=True,
        )
        worker.start()

    except Exception as e:
        print("处理事件失败：", repr(e))
        try:
            event = data.get("event", {})
            chat_id = get_event_chat_id(event)
            token = get_tenant_access_token(FEISHU_APP_ID, FEISHU_APP_SECRET)
            send_text_message(token, chat_id, f"处理失败：{str(e)}")
        except Exception as inner_e:
            print("发送错误消息也失败：", repr(inner_e))

    return {"code": 0}


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise RuntimeError("请先在 .env 中配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
