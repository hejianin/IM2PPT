"""PPT planning agent with soft normalization for outline text."""

from typing import List, Optional

from schemas.ppt_plan_schema import PPTPlan, PPTSlide


def _extract_lines(raw_outline: str) -> List[str]:
	return [line.strip() for line in raw_outline.splitlines() if line.strip()]


def outline_to_plan(raw_outline: str, fallback_title: str = "群聊汇报") -> PPTPlan:
	"""Convert free-text outline into a minimal PPT plan with soft fallback."""
	lines = _extract_lines(raw_outline)
	title = fallback_title
	slides: List[PPTSlide] = []

	current_slide: Optional[PPTSlide] = None

	for line in lines:
		if line.startswith("PPT标题"):
			_, _, maybe_title = line.partition("：")
			title = maybe_title.strip() or title
			continue

		if line.startswith("第") and "页" in line and "：" in line:
			if current_slide:
				slides.append(current_slide)
			_, _, slide_title = line.partition("：")
			current_slide = PPTSlide(title=slide_title.strip() or "未命名页")
			continue

		if line.startswith("-"):
			bullet = line.lstrip("-").strip()
			if bullet and current_slide:
				current_slide.bullets.append(bullet)

	if current_slide:
		slides.append(current_slide)

	if not slides:
		slides = [
			PPTSlide(title="封面", bullets=[title]),
			PPTSlide(title="核心内容", bullets=lines[:5] if lines else ["暂无可用内容"]),
		]

	return PPTPlan(title=title, slides=slides)
