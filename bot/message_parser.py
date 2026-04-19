"""Message parsing and cleaning helpers for Feishu events."""

import datetime as dt
import json
from typing import Any, Dict, List


def parse_event_message_text(message: Dict[str, Any]) -> str:
	"""Parse text from event message.content JSON."""
	raw_content = message.get("content", "{}")
	try:
		content = json.loads(raw_content)
	except Exception:
		return raw_content
	return content.get("text", "")


def get_event_chat_id(event: Dict[str, Any]) -> str:
	"""Get chat_id from standard or legacy event structure."""
	message = event.get("message", {})
	chat_id = message.get("chat_id") or event.get("chat_id")
	if not chat_id:
		raise ValueError(f"没有找到 chat_id，事件结构为: {event}")
	return chat_id


def is_ppt_task(text: str) -> bool:
	"""Detect whether message asks for PPT generation."""
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
	"""Format Feishu message create_time milliseconds to HH:MM:SS."""
	try:
		timestamp = int(ms) / 1000
		return dt.datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
	except Exception:
		return ""


def extract_sender_label(message: Dict[str, Any]) -> str:
	"""Extract sender id fallback chain."""
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


def extract_text_from_post(obj: Any) -> str:
	"""Recursively extract text values from post content."""
	texts: List[str] = []

	def walk(node: Any) -> None:
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


def extract_text_from_message(message: Dict[str, Any]) -> str:
	"""Normalize different message types into readable text."""
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
		try:
			content = json.loads(raw_content)
			return extract_text_from_post(content)
		except Exception:
			return "[富文本消息]"

	if msg_type == "file":
		try:
			content = json.loads(raw_content)
			file_name = content.get("file_name") or content.get("name") or "未命名文件"
			return f"[文件] {file_name}"
		except Exception:
			return "[文件]"

	if msg_type == "image":
		return "[图片]"
	if msg_type == "interactive":
		return "[卡片消息]"

	return f"[{msg_type or '未知类型'}]"


def clean_group_messages(messages: List[Dict[str, Any]]) -> str:
	"""Clean group message list into compact context string for agents."""
	lines: List[str] = []
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

		for mention in message.get("mentions", []):
			key = mention.get("key")
			name = mention.get("name", "")
			if key:
				text = text.replace(key, "")
			if name:
				text = text.replace(f"@{name}", "")

		text = text.strip()
		if is_ppt_task(text) and len(text) <= 20:
			continue

		if text.startswith(("收到，我正在读取", "我已读取到最近群聊内容", "处理失败")):
			continue

		create_time = format_time_from_ms(message.get("create_time", ""))
		sender_label = extract_sender_label(message)
		lines.append(f"[{create_time}] {sender_label}：{text}")

	return "\n".join(lines)
