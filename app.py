import json
import requests
from flask import Flask, request

app = Flask(__name__)

# ========= 配置 =========
APP_ID = "cli_a96e2d2a48781bd2"
APP_SECRET = "aAxtwGyqhlq0H1kXIERdgeOmOiH5QwPC"

# 大模型（你可以换成OpenAI / DeepSeek / 通义等）
LLM_API = "https://api.openai.com/v1/chat/completions"
LLM_KEY = "你的_llm_key"

# ========= 工具函数 =========

def get_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(url, json={
        "app_id": APP_ID,
        "app_secret": APP_SECRET
    }).json()
    return res["tenant_access_token"]


def send_message(token, chat_id, text):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}

    data = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text})
    }

    requests.post(url + "?receive_id_type=chat_id",
                  headers=headers, json=data)


def get_messages(token, chat_id):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}

    params = {
        "container_id_type": "chat",
        "container_id": chat_id,
        "page_size": 20
    }

    res = requests.get(url, headers=headers, params=params).json()
    return res.get("data", {}).get("items", [])


def clean_messages(messages):
    texts = []
    for m in messages:
        if m.get("msg_type") == "text":
            content = json.loads(m["body"]["content"])
            texts.append(content.get("text", ""))
    return "\n".join(texts)


def call_llm(text):
    prompt = f"""
请根据以下讨论生成一个PPT结构：
每页包含标题+要点

内容：
{text}
"""

    headers = {
        "Authorization": f"Bearer {LLM_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    res = requests.post(LLM_API, headers=headers, json=data).json()
    return res["choices"][0]["message"]["content"]


def create_ppt(token):
    url = "https://open.feishu.cn/open-apis/slides/v1/presentations"
    headers = {"Authorization": f"Bearer {token}"}

    res = requests.post(url, headers=headers).json()
    return res["data"]["presentation_id"]


# ========= 回调入口 =========

@app.route("/callback", methods=["POST"])
def callback():
    data = request.json

    # 飞书验证
    if "challenge" in data:
        return {"challenge": data["challenge"]}

    event = data.get("event", {})
    message = event.get("message", {})
    chat_id = event.get("chat_id")

    # 获取文本
    content = json.loads(message.get("content", "{}"))
    text = content.get("text", "")

    if "生成PPT" in text:
        token = get_token()

        # 1️⃣ 获取群消息
        msgs = get_messages(token, chat_id)
        chat_text = clean_messages(msgs)

        # 2️⃣ 调用AI
        ppt_text = call_llm(chat_text)

        # 3️⃣ 创建PPT
        ppt_id = create_ppt(token)

        ppt_link = f"https://feishu.cn/slides/{ppt_id}"

        # 4️⃣ 返回
        send_message(token, chat_id,
                     f"已生成PPT结构👇\n{ppt_text}\n\n点击查看：{ppt_link}")

    return {"code": 0}


if __name__ == "__main__":
    app.run(port=3000)
