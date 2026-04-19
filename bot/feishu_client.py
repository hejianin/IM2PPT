"""Feishu API client for token, messages, group history and file upload."""

import json
import os
import time
from typing import Any, Dict, List

import requests

FEISHU_BASE = "https://open.feishu.cn/open-apis"


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
	"""Fetch tenant_access_token for internal apps."""
	url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
	resp = requests.post(
		url,
		json={"app_id": app_id, "app_secret": app_secret},
		timeout=20,
	)
	data = resp.json()
	if data.get("code") != 0:
		raise RuntimeError(f"获取 tenant_access_token 失败: {data}")
	return data["tenant_access_token"]


def send_text_message(token: str, chat_id: str, text: str) -> None:
	"""Send plain text message to chat."""
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


def upload_file(token: str, file_path: str, file_type: str = "stream") -> str:
	"""Upload a local file to Feishu and return file_key."""
	url = f"{FEISHU_BASE}/im/v1/files"
	headers = {"Authorization": f"Bearer {token}"}

	with open(file_path, "rb") as fp:
		files = {
			"file": (
				os.path.basename(file_path),
				fp,
				"application/vnd.openxmlformats-officedocument.presentationml.presentation",
			)
		}
		data = {
			"file_type": file_type,
			"file_name": os.path.basename(file_path),
		}
		resp = requests.post(url, headers=headers, data=data, files=files, timeout=60)

	payload = resp.json()
	if payload.get("code") != 0:
		raise RuntimeError(f"上传文件失败: {payload}")

	file_key = payload.get("data", {}).get("file_key")
	if not file_key:
		raise RuntimeError(f"上传文件返回缺少 file_key: {payload}")
	return file_key


def send_file_message(token: str, chat_id: str, file_key: str) -> None:
	"""Send uploaded file to chat by file_key."""
	url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type=chat_id"
	headers = {
		"Authorization": f"Bearer {token}",
		"Content-Type": "application/json; charset=utf-8",
	}
	payload = {
		"receive_id": chat_id,
		"msg_type": "file",
		"content": json.dumps({"file_key": file_key}, ensure_ascii=False),
	}

	resp = requests.post(url, headers=headers, json=payload, timeout=20)
	data = resp.json()
	if data.get("code") != 0:
		raise RuntimeError(f"发送文件消息失败: {data}")


def fetch_recent_group_messages(
	token: str,
	chat_id: str,
	minutes: int = 30,
	page_size: int = 50,
) -> List[Dict[str, Any]]:
	"""Fetch recent group messages in ascending create time."""
	now = int(time.time())
	start_time = now - minutes * 60

	url = f"{FEISHU_BASE}/im/v1/messages"
	headers = {"Authorization": f"Bearer {token}"}
	params = {
		"container_id_type": "chat",
		"container_id": chat_id,
		"start_time": str(start_time),
		"end_time": str(now),
		"sort_type": "ByCreateTimeAsc",
		"page_size": page_size,
	}

	items: List[Dict[str, Any]] = []
	while True:
		resp = requests.get(url, headers=headers, params=params, timeout=20)
		data = resp.json()
		if data.get("code") != 0:
			raise RuntimeError(f"获取群消息失败: {data}")

		page_items = data.get("data", {}).get("items", [])
		items.extend(page_items)

		has_more = data.get("data", {}).get("has_more")
		page_token = data.get("data", {}).get("page_token")
		if not has_more or not page_token:
			break

		params["page_token"] = page_token

	return items
