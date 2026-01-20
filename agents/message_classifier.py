"""
Message Classifier for Human-Agent Communication

Classifies human messages into action types (QUERY, INFORMATION, PREFERENCE, COMMAND)
to enable appropriate response strategies and counterfactual reasoning.
"""

import json
import re
from dataclasses import dataclass
from typing import List, Optional, Any
from datetime import datetime


@dataclass
class ClassificationResult:
    """Result of message classification"""
    primary: str  # QUERY, INFORMATION, PREFERENCE, COMMAND, MIXED
    secondary: Optional[str]  # For MIXED messages
    confidence: float  # 0.0-1.0
    extracted_nodes: List[str]  # Node IDs mentioned
    extracted_colors: List[str]  # Colors mentioned
    raw_text: str  # Original message


class MessageClassifier:
    """
    Classifies human messages using LLM-based classification with few-shot examples.
    """

    def __init__(self, llm_call_function=None):
        """
        Initialize the message classifier.

        Args:
            llm_call_function: Function to call LLM with signature (prompt, max_tokens) -> str
        """
        self._llm_call = llm_call_function
        self._few_shot_examples = self._build_few_shot_examples()

    def _build_few_shot_examples(self) -> str:
        """Build few-shot examples for classification prompt"""
        examples = """
EXAMPLES:

Message: "What color is b2?"
Classification: {"primary": "QUERY", "secondary": null, "confidence": 0.95, "extracted_nodes": ["b2"], "extracted_colors": []}

Message: "Can you work with h1=red?"
Classification: {"primary": "QUERY", "secondary": null, "confidence": 0.9, "extracted_nodes": ["h1"], "extracted_colors": ["red"]}

Message: "What are my options?"
Classification: {"primary": "QUERY", "secondary": null, "confidence": 0.95, "extracted_nodes": [], "extracted_colors": []}

Message: "h1 can never be green"
Classification: {"primary": "INFORMATION", "secondary": null, "confidence": 0.95, "extracted_nodes": ["h1"], "extracted_colors": ["green"]}

Message: "b2 is currently red"
Classification: {"primary": "INFORMATION", "secondary": null, "confidence": 0.9, "extracted_nodes": ["b2"], "extracted_colors": ["red"]}

Message: "I'd like h1 to be red"
Classification: {"primary": "PREFERENCE", "secondary": null, "confidence": 0.9, "extracted_nodes": ["h1"], "extracted_colors": ["red"]}

Message: "It would help if h1 were blue"
Classification: {"primary": "PREFERENCE", "secondary": null, "confidence": 0.9, "extracted_nodes": ["h1"], "extracted_colors": ["blue"]}

Message: "How about h1=red?"
Classification: {"primary": "PREFERENCE", "secondary": null, "confidence": 0.85, "extracted_nodes": ["h1"], "extracted_colors": ["red"]}

Message: "Change b2 to green"
Classification: {"primary": "COMMAND", "secondary": null, "confidence": 0.95, "extracted_nodes": ["b2"], "extracted_colors": ["green"]}

Message: "Set b2=green"
Classification: {"primary": "COMMAND", "secondary": null, "confidence": 0.95, "extracted_nodes": ["b2"], "extracted_colors": ["green"]}

Message: "Please change b2 to green"
Classification: {"primary": "COMMAND", "secondary": null, "confidence": 0.9, "extracted_nodes": ["b2"], "extracted_colors": ["green"]}

Message: "I'd like h1=red. Can you work with that?"
Classification: {"primary": "PREFERENCE", "secondary": "QUERY", "confidence": 0.85, "extracted_nodes": ["h1"], "extracted_colors": ["red"]}

Message: "Change b2 to green and tell me your score"
Classification: {"primary": "COMMAND", "secondary": "QUERY", "confidence": 0.85, "extracted_nodes": ["b2"], "extracted_colors": ["green"]}
"""
        return examples.strip()

    def classify_message(self, text: str, dialogue_history: Optional[List[str]] = None) -> ClassificationResult:
        """
        Classify a human message into action types.

        Args:
            text: The message text to classify
            dialogue_history: Recent dialogue turns for context (last 3-6 messages)

        Returns:
            ClassificationResult with classification details
        """
        if not text or not text.strip():
            return ClassificationResult(
                primary="QUERY",
                secondary=None,
                confidence=0.5,
                extracted_nodes=[],
                extracted_colors=[],
                raw_text=text
            )

        # If no LLM available, fall back to heuristic classification
        if not self._llm_call:
            return self._heuristic_classify(text)

        # Build prompt for LLM classification
        prompt = self._build_classification_prompt(text, dialogue_history)

        try:
            # Call LLM
            response = self._llm_call(prompt, max_tokens=200)

            # Parse JSON response
            result = self._parse_llm_response(response, text)

            return result

        except Exception as e:
            print(f"[MessageClassifier] LLM classification failed: {e}, falling back to heuristic")
            return self._heuristic_classify(text)

    def _build_classification_prompt(self, text: str, dialogue_history: Optional[List[str]]) -> str:
        """Build the classification prompt for the LLM"""
        history_str = ""
        if dialogue_history and len(dialogue_history) > 0:
            recent = dialogue_history[-3:] if len(dialogue_history) > 3 else dialogue_history
            history_str = "\nRecent dialogue:\n" + "\n".join(recent)

        prompt = f"""You are classifying human messages in a graph coloring coordination task.

Categories:
- QUERY: Asking for information, options, feasibility, or current state
- INFORMATION: Stating facts, constraints, or reporting current state
- PREFERENCE: Expressing desires or suggestions without commanding (tentative, "I'd like", "How about")
- COMMAND: Direct instruction to change something (imperative, "Change X", "Set Y")
- MIXED: Multiple intents present (classify primary + secondary)

{self._few_shot_examples}
{history_str}

Message: "{text}"

Return ONLY valid JSON with this exact format:
{{"primary": "CATEGORY", "secondary": null, "confidence": 0.0, "extracted_nodes": [], "extracted_colors": []}}

Classification:"""

        return prompt

    def _parse_llm_response(self, response: str, original_text: str) -> ClassificationResult:
        """Parse LLM JSON response into ClassificationResult"""
        # Try to extract JSON from response
        json_match = re.search(r'\{[^}]+\}', response)
        if not json_match:
            raise ValueError(f"No JSON found in response: {response}")

        json_str = json_match.group(0)
        data = json.loads(json_str)

        return ClassificationResult(
            primary=data.get("primary", "QUERY"),
            secondary=data.get("secondary"),
            confidence=float(data.get("confidence", 0.7)),
            extracted_nodes=data.get("extracted_nodes", []),
            extracted_colors=data.get("extracted_colors", []),
            raw_text=original_text
        )

    def _heuristic_classify(self, text: str) -> ClassificationResult:
        """
        Fallback heuristic classification using regex patterns.
        Used when LLM is unavailable.
        """
        text_lower = text.lower()

        # Extract nodes and colors
        nodes = self._extract_nodes(text)
        colors = self._extract_colors(text)

        # Command patterns (imperative)
        command_patterns = [
            r'\b(change|set|make|switch)\s+\w+\s+(?:to|=)',
            r'\b\w+\s*=\s*\w+',
        ]
        for pattern in command_patterns:
            if re.search(pattern, text_lower):
                return ClassificationResult(
                    primary="COMMAND",
                    secondary=None,
                    confidence=0.8,
                    extracted_nodes=nodes,
                    extracted_colors=colors,
                    raw_text=text
                )

        # Query patterns (questions, requests for information)
        query_patterns = [
            r'\bwhat\b',
            r'\bcan you\b',
            r'\bhow\b',
            r'\bwhere\b',
            r'\bwhich\b',
            r'\?',
            r'\boptions\b',
        ]
        for pattern in query_patterns:
            if re.search(pattern, text_lower):
                return ClassificationResult(
                    primary="QUERY",
                    secondary=None,
                    confidence=0.7,
                    extracted_nodes=nodes,
                    extracted_colors=colors,
                    raw_text=text
                )

        # Preference patterns (tentative, suggestions)
        preference_patterns = [
            r'\bi\'?d like\b',
            r'\bwould help\b',
            r'\bhow about\b',
            r'\bpreferably\b',
            r'\bmaybe\b',
            r'\bcould we\b',
        ]
        for pattern in preference_patterns:
            if re.search(pattern, text_lower):
                return ClassificationResult(
                    primary="PREFERENCE",
                    secondary=None,
                    confidence=0.75,
                    extracted_nodes=nodes,
                    extracted_colors=colors,
                    raw_text=text
                )

        # Information patterns (stating facts, constraints)
        info_patterns = [
            r'\bcan(?:not|\'t) be\b',
            r'\bmust be\b',
            r'\bnever\b',
            r'\bis currently\b',
            r'\bhas to be\b',
            r'\bconflict\b',
        ]
        for pattern in info_patterns:
            if re.search(pattern, text_lower):
                return ClassificationResult(
                    primary="INFORMATION",
                    secondary=None,
                    confidence=0.75,
                    extracted_nodes=nodes,
                    extracted_colors=colors,
                    raw_text=text
                )

        # Default to QUERY if no clear pattern
        return ClassificationResult(
            primary="QUERY",
            secondary=None,
            confidence=0.5,
            extracted_nodes=nodes,
            extracted_colors=colors,
            raw_text=text
        )

    def _extract_nodes(self, text: str) -> List[str]:
        """Extract node IDs from text (e.g., h1, b2, a3)"""
        # Pattern: letter followed by digit(s)
        pattern = r'\b([a-zA-Z]\d+)\b'
        matches = re.findall(pattern, text)
        return list(set(matches))  # Remove duplicates

    def _extract_colors(self, text: str) -> List[str]:
        """Extract color names from text"""
        colors = ['red', 'green', 'blue', 'yellow', 'orange', 'purple']
        text_lower = text.lower()
        found = [color for color in colors if color in text_lower]
        return list(set(found))  # Remove duplicates


def log_classification(result: ClassificationResult, log_file: str = None):
    """
    Log classification result to file (for research analysis).

    Args:
        result: ClassificationResult to log
        log_file: Path to log file (if None, uses default llm_trace.jsonl)
    """
    if log_file is None:
        return  # Skip logging if no file specified

    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "event": "message_classification",
        "message": result.raw_text,
        "primary": result.primary,
        "secondary": result.secondary,
        "confidence": result.confidence,
        "extracted_nodes": result.extracted_nodes,
        "extracted_colors": result.extracted_colors
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print(f"[MessageClassifier] Failed to log classification: {e}")
