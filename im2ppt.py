from flask import Flask, request, jsonify
import requests, json

app = Flask(__name__)

APP_ID = "cli_a96e2d2a48781bd2"
APP_SECRET = "aAxtwGyqhlq0H1kXIERdgeOmOiH5QwPC"

def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=10
    ).json()
    return r["tenant_access_token"]

def send_text_to_chat(chat_id, text):
    token = get_token()
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}, ensure_ascii=False)
    }
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    print(resp.text)

@app.route("/callback", methods=["POST"])
def callback():
    data = request.json

    # 飞书URL验证
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})

    print("收到事件：", json.dumps(data, ensure_ascii=False))

    event = data.get("event", {})
    chat_id = event.get("message", {}).get("chat_id") or event.get("chat_id")
    if chat_id:
        send_text_to_chat(chat_id, "我收到了，你的机器人已经通了。")
    return jsonify({"code": 0})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
