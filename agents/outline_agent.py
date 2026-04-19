"""Outline agent: group context to outline text."""

from agents.siliconflow_client import chat_completion


def generate_outline_text(
	chat_context: str,
	user_instruction: str,
	api_key: str,
	model: str,
) -> str:
	"""Generate PPT outline from group chat context."""
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

	return chat_completion(
		api_key=api_key,
		model=model,
		messages=[
			{
				"role": "system",
				"content": "你是一个擅长把会议讨论整理成汇报型 PPT 大纲的办公协同 Agent。",
			},
			{"role": "user", "content": prompt},
		],
		temperature=0.4,
		max_tokens=2000,
	)
