"""Rule registry. Future WCAG rules: create a file here and append to RULES."""

from .base import CaptureContext, Rule
from .node_heuristics import NodeHeuristicsRule
from .text_scale import TextScaleRule

RULES: list[Rule] = [NodeHeuristicsRule(), TextScaleRule()]

__all__ = ["CaptureContext", "Rule", "RULES"]
