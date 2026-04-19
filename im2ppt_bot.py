import os
import json
import time
import datetime as dt
from typing import Any, Dict, List

import requests
from flask import Flask, request
from dotenv import load_dotenv

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY")
SILICONFLOW_MODEL = os.getenv("SILICONFLOW_MODEL", "deepseek-ai/DeepSeek-V3")
SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"

load_dotenv()

app = Flask(__name__)

FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
PORT = int(os.getenv("PORT", "3000"))

FEISHU_BASE = "https://open.feishu.cn/open-apis"


# =========================
# 飞书基础能力
# =========================

def get_tenant_access_token() -> str:
    """获取 tenant_access_token"""
    url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"

    resp = requests.post(
        url,
        json={
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET,
        },
        timeout=20,
    )

    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"获取 tenant_access_token 失败: {data}")

    return data["tenant_access_token"]


def send_text_message(token: str, chat_id: str, text: str) -> None:
    """机器人向群聊发送文本消息"""
    url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type=chat_id"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    payload = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False),
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"发送消息失败: {data}")


def fetch_recent_group_messages(
    token: str,
    chat_id: str,
    minutes: int = 30,
    page_size: int = 50,
) -> List[Dict[str, Any]]:
    """
    拉取最近 N 分钟群消息。
    这里用历史消息接口，按创建时间升序拉取。
    """
    now = int(time.time())
    start_time = now - minutes * 60
    end_time = now

    url = f"{FEISHU_BASE}/im/v1/messages"

    headers = {
        "Authorization": f"Bearer {token}",
    }

    params = {
        "container_id_type": "chat",
        "container_id": chat_id,
        "start_time": str(start_time),
        "end_time": str(end_time),
        "sort_type": "ByCreateTimeAsc",
        "page_size": page_size,
    }

    all_items = []

    while True:
        resp = requests.get(url, headers=headers, params=params, timeout=20)
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"获取群消息失败: {data}")

        items = data.get("data", {}).get("items", [])
        all_items.extend(items)

        has_more = data.get("data", {}).get("has_more")
        page_token = data.get("data", {}).get("page_token")

        if not has_more or not page_token:
            break

        params["page_token"] = page_token

    return all_items


# =========================
# 消息解析与清洗
# =========================

def parse_event_message_text(message: Dict[str, Any]) -> str:
    """解析触发消息文本"""
    raw_content = message.get("content", "{}")

    try:
        content = json.loads(raw_content)
    except Exception:
        return raw_content

    return content.get("text", "")


def get_event_chat_id(event: Dict[str, Any]) -> str:
    """
    从事件中获取 chat_id。
    飞书事件结构里通常在 event.message.chat_id。
    """
    message = event.get("message", {})
    chat_id = message.get("chat_id")

    if not chat_id:
        # 兼容旧结构
        chat_id = event.get("chat_id")

    if not chat_id:
        raise ValueError(f"没有找到 chat_id，事件结构为: {event}")

    return chat_id


def is_ppt_task(text: str) -> bool:
    """判断用户是否在让机器人生成 PPT"""
    keywords = [
        "生成PPT",
        "做PPT",
        "制作PPT",
        "生成ppt",
        "做ppt",
        "制作ppt",
        "演示稿",
        "汇报",
    ]
    return any(keyword in text for keyword in keywords)


def format_time_from_ms(ms: str) -> str:
    """飞书消息 create_time 通常是毫秒时间戳"""
    try:
        timestamp = int(ms) / 1000
        return dt.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
    except Exception:
        return ""


def extract_sender_label(message: Dict[str, Any]) -> str:
    """
    简单提取发送者标识。
    当前先用 open_id / user_id，占位即可。
    后面可以再接用户信息接口换成中文名。
    """
    sender = message.get("sender", {})
    sender_id = sender.get("sender_id", {})

    if isinstance(sender_id, dict):
        return (
            sender_id.get("user_id")
            or sender_id.get("open_id")
            or sender_id.get("union_id")
            or "unknown"
        )

    if isinstance(sender_id, str):
        return sender_id

    return "unknown"


def extract_text_from_message(message: Dict[str, Any]) -> str:
    """从飞书消息中提取可读文本"""
    msg_type = message.get("msg_type") or message.get("message_type")
    body = message.get("body", {})
    raw_content = body.get("content", "")

    if msg_type == "text":
        try:
            content = json.loads(raw_content)
            return content.get("text", "").strip()
        except Exception:
            return raw_content.strip()

    if msg_type == "post":
        # 富文本消息，先做一个简化提取
        try:
            content = json.loads(raw_content)
            return extract_text_from_post(content)
        except Exception:
            return "[富文本消息]"

    if msg_type == "file":
        try:
            content = json.loads(raw_content)
            file_name = (
                content.get("file_name")
                or content.get("name")
                or "未命名文件"
            )
            return f"[文件] {file_name}"
        except Exception:
            return "[文件]"

    if msg_type == "image":
        return "[图片]"

    if msg_type == "interactive":
        return "[卡片消息]"

    return f"[{msg_type or '未知类型'}]"


def extract_text_from_post(obj: Any) -> str:
    """递归提取富文本 post 里的 text 字段"""
    texts = []

    def walk(node: Any):
        if isinstance(node, dict):
            if isinstance(node.get("text"), str):
                texts.append(node["text"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return "".join(texts).strip()


def clean_group_messages(messages: List[Dict[str, Any]]) -> str:
    """
    把群聊消息清洗成给 Agent 使用的文本：
    1. 跳过系统消息
    2. 跳过机器人自己发的消息
    3. 跳过 @机器人 生成PPT 这类触发命令
    """
    lines = []

    for message in messages:
        msg_type = message.get("msg_type") or message.get("message_type")

        if msg_type == "system":
            continue

        sender = message.get("sender", {})
        if sender.get("sender_type") == "app":
            continue

        text = extract_text_from_message(message).strip()
        if not text:
            continue

        # 去掉 @ 占位符
        for mention in message.get("mentions", []):
            key = mention.get("key")
            name = mention.get("name", "")
            if key:
                text = text.replace(key, "")
            if name:
                text = text.replace(f"@{name}", "")

        text = text.strip()

        # 跳过触发命令
        if is_ppt_task(text) and len(text) <= 20:
            continue

        # 跳过机器人回复类内容，避免递归污染上下文
        bot_reply_prefixes = [
            "收到，我正在读取",
            "我已读取到最近群聊内容",
            "处理失败",
        ]
        if any(text.startswith(prefix) for prefix in bot_reply_prefixes):
            continue

        create_time = format_time_from_ms(message.get("create_time", ""))
        sender_label = extract_sender_label(message)

        lines.append(f"[{create_time}] {sender_label}：{text}")

    return "\n".join(lines)

def generate_ppt_outline_with_siliconflow(chat_context: str, user_instruction: str) -> str:
    """
    调用硅基流动，根据群聊上下文生成 PPT 大纲。
    这一步只生成大纲，不生成 pptx 文件。
    """
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("请先在 .env 中配置 SILICONFLOW_API_KEY")

    prompt = f"""
你是一个专业的 PPT 策划助手。请根据飞书群聊记录，生成一份适合汇报的 PPT 大纲。

用户指令：
{user_instruction}

群聊记录：
{chat_context}

请严格按照下面格式输出：

PPT标题：xxx

第1页：封面
- 标题：xxx
- 副标题：xxx

第2页：项目背景
- 要点1
- 要点2
- 要点3

第3页：需求与目标
- 要点1
- 要点2
- 要点3

第4页：方案设计
- 要点1
- 要点2
- 要点3

第5页：核心流程
- 要点1
- 要点2
- 要点3

第6页：技术架构
- 要点1
- 要点2
- 要点3

第7页：实施计划
- 要点1
- 要点2
- 要点3

第8页：总结与价值
- 要点1
- 要点2
- 要点3

要求：
1. 不要编造过多群聊中没有的信息。
2. 可以基于群聊内容做合理归纳。
3. 语言简洁，适合直接放进 PPT。
4. 输出中文。
"""

    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": SILICONFLOW_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是一个擅长把会议讨论整理成汇报型 PPT 大纲的办公协同 Agent。"
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.4,
        "max_tokens": 2000,
    }

    resp = requests.post(
        SILICONFLOW_URL,
        headers=headers,
        json=payload,
        timeout=60,
    )

    data = resp.json()

    if resp.status_code != 200:
        raise RuntimeError(f"硅基流动请求失败: status={resp.status_code}, body={data}")

    if "choices" not in data:
        raise RuntimeError(f"硅基流动返回格式异常: {data}")

    return data["choices"][0]["message"]["content"]



# =========================
# 飞书事件回调
# =========================

@app.route("/callback", methods=["POST"])
def callback():
    data = request.json or {}

    print("\n========== 收到飞书事件 ==========")
    print(json.dumps(data, ensure_ascii=False, indent=2))

    # URL 验证
    if "challenge" in data:
        return {"challenge": data["challenge"]}

    try:
        event = data.get("event", {})
        message = event.get("message", {})

        text = parse_event_message_text(message)
        chat_id = get_event_chat_id(event)

        print(f"chat_id = {chat_id}")
        print(f"message text = {text}")

        # 不是 PPT 任务就先不处理
        if not is_ppt_task(text):
            return {"code": 0}

        token = get_tenant_access_token()

        send_text_message(
            token,
            chat_id,
            "收到，我正在读取最近 30 分钟的群聊消息，用于生成 PPT 输入。",
        )

        messages = fetch_recent_group_messages(
            token=token,
            chat_id=chat_id,
            minutes=30,
            page_size=50,
        )

        cleaned_text = clean_group_messages(messages)

        if not cleaned_text:
            reply = "我没有读取到最近 30 分钟内可用于生成 PPT 的文本消息。"
            send_text_message(token, chat_id, reply)
            return {"code": 0}

        send_text_message(
            token,
            chat_id,
            "我已读取到群聊内容，正在调用 AI 生成 PPT 大纲，请稍等。"
        )

        ppt_outline = generate_ppt_outline_with_siliconflow(
            chat_context=cleaned_text,
            user_instruction=text,
        )

        max_len = 3500
        reply = "我已根据最近群聊生成 PPT 大纲：\n\n" + ppt_outline[:max_len]

        if len(ppt_outline) > max_len:
            reply += "\n\n大纲内容较长，已截断显示。"

        send_text_message(token, chat_id, reply)


    except Exception as e:
        print("处理事件失败：", repr(e))

        try:
            token = get_tenant_access_token()
            event = data.get("event", {})
            chat_id = get_event_chat_id(event)
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

    app.run(host="0.0.0.0", port=PORT, debug=True)
