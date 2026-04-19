"""SiliconFlow API client wrapper."""

from typing import Any, Dict, List

import requests

SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"


def chat_completion(
	api_key: str,
	model: str,
	messages: List[Dict[str, str]],
	temperature: float = 0.4,
	max_tokens: int = 2000,
) -> str:
	"""Call SiliconFlow chat completion and return assistant content."""
	if not api_key:
		raise RuntimeError("请先在 .env 中配置 SILICONFLOW_API_KEY")

	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
	}
	payload: Dict[str, Any] = {
		"model": model,
		"messages": messages,
		"temperature": temperature,
		"max_tokens": max_tokens,
	}

	resp = requests.post(SILICONFLOW_URL, headers=headers, json=payload, timeout=60)
	data = resp.json()

	if resp.status_code != 200:
		raise RuntimeError(f"硅基流动请求失败: status={resp.status_code}, body={data}")
	if "choices" not in data:
		raise RuntimeError(f"硅基流动返回格式异常: {data}")

	return data["choices"][0]["message"]["content"]
