"""PPT plan schema definitions for renderer handoff."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class PPTSlide:
	"""Single slide plan entry."""

	title: str
	bullets: List[str] = field(default_factory=list)


@dataclass
class PPTPlan:
	"""Renderer-ready plan."""

	title: str
	slides: List[PPTSlide] = field(default_factory=list)
