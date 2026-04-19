"""Outline schema definitions for minimal pipeline."""

from dataclasses import dataclass


@dataclass
class OutlineResult:
	"""LLM-generated outline content container."""

	raw_text: str
