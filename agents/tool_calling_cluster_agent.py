"""Tool-calling agent using OpenAI LLM as translation layer.

This module implements the LLM_TOOL mode where an LLM acts as a translation layer
between human natural language and deterministic API methods. The architecture follows
the LLM_RB pattern: LLM translates, API executes.

Architecture:
    Human NL → [LLM Translator] → API Calls → [API Engine] → Results → [LLM Translator] → Human NL

Three-Phase Design:
    Phase 1 (Inbound): LLM translates human message to list of API method calls
    Phase 2 (Execution): Execute API calls deterministically, collect comprehensive results
    Phase 3 (Outbound): LLM translates API results to natural language response

The LLM never acts as a reasoning engine - it purely translates between natural language
and structured API calls. All decision-making happens in the deterministic API layer.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import os

from .cluster_agent import ClusterAgent
from .cluster_agent_api import ClusterAgentAPI


class ToolCallingClusterAgent(ClusterAgent):
    """Agent using LLM as translation layer between human NL and API calls.

    This agent implements a clean 3-phase architecture:
    1. Inbound translation: Human NL → API method calls (LLM)
    2. Execution: Run API methods deterministically (API)
    3. Outbound translation: API results → Human NL (LLM)

    Parameters
    ----------
    name : str
        Agent identifier
    problem : GraphColoring
        Graph coloring problem instance
    comm_layer : BaseCommLayer
        Communication layer for message formatting
    local_nodes : List[str]
        Nodes controlled by this agent
    owners : Dict[str, str]
        Node ownership mapping
    backend_model : str, optional
        OpenAI model for translation (default: "gpt-4-turbo")
    **kwargs
        Additional arguments passed to ClusterAgent

    Attributes
    ----------
    api : ClusterAgentAPI
        API library for graph coloring operations
    backend_llm : OpenAI
        Backend LLM client for translation
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: Any,
        local_nodes: List[str],
        owners: Dict[str, str],
        backend_model: str = "gpt-4-turbo",
        **kwargs
    ) -> None:
        super().__init__(
            name=name,
            problem=problem,
            comm_layer=comm_layer,
            local_nodes=local_nodes,
            owners=owners,
            **kwargs
        )

        # Initialize API library
        self.api = ClusterAgentAPI(self)

        # Initialize OpenAI client (REQUIRED - fail fast if not available)
        try:
            from openai import OpenAI
            api_key = self._load_api_key()
            self.backend_llm = OpenAI(api_key=api_key)
            self.backend_model = backend_model
            self.log(f"[TOOL] Translation layer initialized with {backend_model}")
        except FileNotFoundError as e:
            error_msg = f"[TOOL] FATAL: {e}\nLLM_TOOL mode requires OpenAI API key. Cannot continue."
            print(f"\n{'='*70}\nERROR: {error_msg}\n{'='*70}\n")
            raise SystemExit(error_msg)
        except Exception as e:
            error_msg = f"[TOOL] FATAL: Failed to initialize OpenAI client: {e}\nLLM_TOOL mode requires valid API key. Cannot continue."
            print(f"\n{'='*70}\nERROR: {error_msg}\n{'='*70}\n")
            raise SystemExit(error_msg)

        # Tracking
        self._last_human_text = ""
        self._received_human_message_this_turn = False

        self.log(f"[TOOL] Initialized ToolCallingClusterAgent as translation layer")

    def _load_api_key(self) -> str:
        """Load OpenAI API key from api_key.txt."""
        key_file = "api_key.txt"
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                return f.read().strip()
        else:
            raise FileNotFoundError("api_key.txt not found. Please create it with your OpenAI API key.")

    def step(self) -> None:
        """Execute one reasoning step using 3-phase translation architecture.

        Phase 1: Translate human message to API calls (LLM)
        Phase 2: Execute API calls deterministically (API)
        Phase 3: Translate API results to human NL (LLM)
        """
        self.log(f"[TOOL] step() called - phase={self._phase}, announced={self._config_announced}")

        # Handle configure phase - automatic announcement
        if self._phase == "configure" and not self._config_announced:
            self.log("[TOOL] Configure phase - sending automatic announcement")
            self._send_automatic_announcement()
            return

        # Check if we have backend LLM
        if self.backend_llm is None:
            self.log("[TOOL] No backend LLM available, falling back to algorithmic mode")
            super().step()
            return

        # Wait for human message
        if not self._received_human_message_this_turn and not any(self.received_messages):
            self.log("[TOOL] Waiting for human message")
            return

        # Early satisfaction check: If already satisfied and no new human message, don't renegotiate
        if self.satisfied and not self._received_human_message_this_turn:
            self.log("[TOOL] Already satisfied, no new message - skipping step")
            return

        # If satisfied, check if current config still works before re-negotiating
        if self.satisfied:
            # Human sent new message - re-check if we're still satisfied
            current_penalty, _ = self.api.get_current_penalty()
            if current_penalty < 1e-6:
                self.log("[TOOL] Still satisfied (penalty=0) - sending acknowledgment")
                # Send simple acknowledgment
                ack_message = {
                    "should_send_message": True,
                    "recipient": "Human",
                    "message_type": "acceptance",
                    "structured_content": {
                        "my_assignments": dict(self.assignments),
                        "reason": "That works for me. The current configuration is still good.",
                        "requested_changes": {}
                    }
                }
                self._send_translated_message(ack_message)
                self._received_human_message_this_turn = False
                return
            else:
                # No longer satisfied - continue with normal processing
                self.satisfied = False
                self.log(f"[TOOL] No longer satisfied (penalty={current_penalty}) - re-negotiating")

        try:
            # Get human message context
            human_message = self._last_human_text if self._last_human_text else "No recent message"

            # PHASE 1: Inbound Translation (LLM translates human NL to API calls)
            self.log("[TOOL] Phase 1: Translating human message to API calls")
            api_calls = self._translate_inbound(human_message)
            self.log(f"[TOOL] Phase 1 result: {len(api_calls)} API calls identified")

            # PHASE 2: Execution (Execute API calls deterministically)
            self.log("[TOOL] Phase 2: Executing API calls")
            api_results = self._execute_api_methods(api_calls)
            self.log(f"[TOOL] Phase 2 complete: {len(api_results)} results collected")

            # PHASE 3: Outbound Translation (LLM translates API results to human NL)
            self.log("[TOOL] Phase 3: Translating API results to human message")
            response_message = self._translate_outbound(api_results, human_message)
            self.log(f"[TOOL] Phase 3 result: message_type={response_message.get('message_type')}")

            # Update satisfaction based on results
            current_penalty = api_results.get("current_penalty", float('inf'))
            if current_penalty < 1e-6:
                self.satisfied = True
                self.log("[TOOL] Satisfied: penalty=0")
            else:
                self.satisfied = False
                self.log(f"[TOOL] Not satisfied: penalty={current_penalty}")

            # Send message if translation produced one
            if response_message.get("should_send_message"):
                self._send_translated_message(response_message)
                self.log("[TOOL] Message sent successfully")
            else:
                self.log("[TOOL] Translation decided not to send message")

            # Reset flag
            self._received_human_message_this_turn = False

        except Exception as e:
            self.log(f"[TOOL] Error in translation pipeline: {e}")
            import traceback
            self.log(traceback.format_exc())
            # Fail fast - don't fall back to algorithmic mode
            raise

    def _translate_inbound(self, human_message: str) -> List[Dict[str, Any]]:
        """Phase 1: Translate human natural language to API method calls.

        Uses LLM to parse human intent and identify which API methods should
        be called to respond appropriately.

        Parameters
        ----------
        human_message : str
            Human's natural language message

        Returns
        -------
        List[Dict[str, Any]]
            List of API method calls with parameters
            Example: [
                {"method": "get_current_penalty", "params": {}},
                {"method": "simulate_neighbor_change", "params": {"neighbor_nodes": {"h4": "blue"}}}
            ]
        """
        # Identify visible neighbor nodes (partial observability)
        visible_neighbor_nodes = set()
        for u, v in self.problem.edges:
            if u in self.nodes and v not in self.nodes:
                visible_neighbor_nodes.add(v)
            elif v in self.nodes and u not in self.nodes:
                visible_neighbor_nodes.add(u)

        visible_neighbors_list = sorted(visible_neighbor_nodes)

        prompt = f"""You are translating human natural language to API method calls.

**Your Role**: Translation layer (NOT reasoning engine)
**Your Task**: Parse the human message and identify which API methods to call

**Human message**: "{human_message}"

**Context**:
- Your name: {self.name}
- Your nodes: {", ".join(self.nodes)}
- Visible neighbor nodes: {", ".join(visible_neighbors_list) if visible_neighbors_list else "None"}
- Current assignments: {self.assignments}
- Neighbor assignments: {dict((k, v) for k, v in self.neighbour_assignments.items() if k in visible_neighbor_nodes)}

**Message Type Recognition**:

1. **Constraint** ("h4 can't be green", "h4 is impossible as green"):
   - Call: simulate_neighbor_change() to test ALL other colors for that node
   - Goal: Find what DOES work if constraint is true

2. **Question/Query** ("Can that work?", "Is that possible?", "Does that work?"):
   - Call: simulate_neighbor_change() OR get_best_response_to() to TEST the scenario
   - Look at previous messages for context about what "that" refers to

3. **Conditional** ("If h1=green then h4=blue", "h4 blue if h1 green"):
   - Call: get_best_response_to() with the conditional neighbor colors
   - Test if the conditional scenario works

4. **Announcement** ("I've set X", "My colors are X"):
   - Call: get_current_penalty() then get_best_response_to()

**Available API Methods** (choose which to call):

1. **get_current_penalty()** - Check current conflicts
   - No parameters
   - Use when: Need to analyze current state

2. **simulate_neighbor_change(neighbor_nodes)** - Test if neighbor changing colors helps
   - Parameters: {{"neighbor_nodes": {{"h4": "blue"}}}}
   - CRITICAL: Pass ALL known neighbor colors (change only what you're testing)
   - Parameters: {{"neighbor_nodes": {{"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}}}}
   - Use when: Testing "what if neighbor changes h4 to blue?"

3. **get_best_response_to(neighbor_assignments)** - Find optimal response to neighbor colors
   - Parameters: {{"neighbor_assignments": {{"h4": "blue"}}}} or {{}} for current
   - Use when: Need to find best configuration given neighbor colors

4. **enumerate_alternatives(nodes, max_alternatives)** - List alternative colorings
   - Parameters: {{"nodes": ["a2", "a5"], "max_alternatives": 5}}
   - Use when: Need to explore multiple options

5. **get_conflict_resolution_options(max_options)** - Get ways to resolve conflicts
   - Parameters: {{"max_options": 5}}
   - Use when: Need specific conflict resolution suggestions

6. **check_feasibility(node, color)** - Test if YOUR node can be a color
   - Parameters: {{"node": "a2", "color": "blue"}}
   - Use when: Testing your own node colors

7. **get_available_colors(node)** - Get valid colors for YOUR node
   - Parameters: {{"node": "a2"}}
   - Use when: Need list of options for your node

**CRITICAL: Always pass COMPLETE neighbor configs to simulate_neighbor_change()**:
❌ WRONG: simulate_neighbor_change({{"neighbor_nodes": {{"h4": "blue"}}}})  # Missing other neighbors!
✅ CORRECT: simulate_neighbor_change({{"neighbor_nodes": {{"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}}}})

When testing "what if h4 becomes blue?", you must include ALL known neighbors in the dict.
Only the nodes being tested should differ from current state. All other neighbors must be included with their current colors.
This ensures accurate penalty calculation.

**Translation Strategy Examples**:

"h4 can't be green" / "h4 is impossible as green":
  → [simulate_neighbor_change({{"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"}}),
     simulate_neighbor_change({{"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"}})]
  → Test what colors DO work for h4 (ALWAYS include ALL neighbors)

"Can that work?" / "Is that possible?" / "Does that work?":
  → Look at conversation context to understand "that"
  → If referring to a scenario, call get_best_response_to() with those colors
  → Example: "h4=blue if h1=green, can that work?" → get_best_response_to({{"h1": "green", "h4": "blue"}})

"If h1=green then h4=blue" / "h4 blue if h1 green":
  → get_best_response_to({{"h1": "green", "h4": "blue"}})
  → Test the conditional scenario

"I've set h1=red, h2=blue":
  → get_current_penalty(), get_best_response_to()
  → Analyze current state

Default (unclear message):
  → get_current_penalty(), get_best_response_to()
  → Basic analysis

**Output Format** (JSON only):
{{
  "api_calls": [
    {{"method": "get_current_penalty", "params": {{}}}},
    {{"method": "get_best_response_to", "params": {{}}}}
  ]
}}

**Rules**:
- ONLY mention visible neighbor nodes: {", ".join(visible_neighbors_list)}
- DON'T call methods for nodes you can't see
- Return valid JSON with "api_calls" array
- Keep params empty {{}} if no parameters needed

Return ONLY the JSON object. No explanatory text."""

        try:
            response = self.backend_llm.chat.completions.create(
                model=self.backend_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # Deterministic translation
                max_tokens=1000,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            self.log(f"[TOOL][PHASE1] LLM response: {result_text[:200]}")

            result = json.loads(result_text)
            api_calls = result.get("api_calls", [])

            # POST-PROCESS: Complete any incomplete neighbor_nodes in simulate_neighbor_change calls
            # CRITICAL: LLM might generate {"h2": "red", "h5": "blue"} without other neighbors
            # This leads to incorrect penalty calculations!
            for call in api_calls:
                if call.get("method") == "simulate_neighbor_change":
                    params = call.get("params", {})
                    neighbor_nodes = params.get("neighbor_nodes", {})

                    # Check if incomplete
                    known_neighbors = set(self.neighbour_assignments.keys())
                    provided_neighbors = set(neighbor_nodes.keys())
                    missing_neighbors = known_neighbors - provided_neighbors

                    if missing_neighbors:
                        self.log(f"[TOOL][PHASE1] WARNING: LLM generated incomplete neighbor config!")
                        self.log(f"  Provided: {sorted(provided_neighbors)}")
                        self.log(f"  Missing: {sorted(missing_neighbors)}")
                        self.log(f"  Auto-completing with current values...")

                        # Fill in missing neighbors with current values
                        complete_config = dict(self.neighbour_assignments)
                        complete_config.update(neighbor_nodes)  # Override with LLM's intended changes
                        params["neighbor_nodes"] = complete_config

                        self.log(f"  Completed: {sorted(complete_config.keys())}")

            # Log translation
            self._log_translation("inbound", human_message, api_calls)

            return api_calls

        except Exception as e:
            self.log(f"[TOOL][PHASE1] Translation failed: {e}, using enhanced fallback")

            # ENHANCED FALLBACK: Test alternatives to find what actually works
            api_calls = [
                {"method": "get_current_penalty", "params": {}},
                {"method": "get_best_response_to", "params": {}},  # Current state
            ]

            # Add calls to test alternatives for conflict resolution
            # This ensures we have TESTED options to propose
            api_calls.append({"method": "get_conflict_resolution_options", "params": {"max_options": 5}})

            # Test alternatives for each visible neighbor node
            for neighbor_node in visible_neighbor_nodes:
                current_color = self.neighbour_assignments.get(neighbor_node)
                # Test each alternative color for this neighbor
                for alt_color in self.domain:
                    if alt_color != current_color:
                        # Build COMPLETE neighbor config (all neighbors, only change one)
                        # CRITICAL: Must pass ALL neighbor assignments to get accurate penalty
                        complete_neighbor_config = dict(self.neighbour_assignments)
                        complete_neighbor_config[neighbor_node] = alt_color

                        api_calls.append({
                            "method": "simulate_neighbor_change",
                            "params": {"neighbor_nodes": complete_neighbor_config}
                        })

            self.log(f"[TOOL][PHASE1] Fallback generated {len(api_calls)} API calls to test alternatives")
            return api_calls

    def _execute_api_methods(self, api_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Phase 2: Execute API methods deterministically and collect results.

        This is the deterministic "engine" - no LLM reasoning, just execution.

        Parameters
        ----------
        api_calls : List[Dict[str, Any]]
            List of API method calls from Phase 1

        Returns
        -------
        Dict[str, Any]
            Comprehensive results from all API calls
            Example: {
                "current_penalty": 2.0,
                "current_conflicts": [("a4", "h4")],
                "best_response": {"a1": "green", "a2": "red", "penalty": 0},
                "simulation_h4_blue": {"penalty": 0, "conflicts": []}
            }
        """
        results = {}

        for call in api_calls:
            method_name = call.get("method", "")
            params = call.get("params", {})

            if not hasattr(self.api, method_name):
                self.log(f"[TOOL][PHASE2] Unknown method: {method_name}")
                continue

            try:
                method = getattr(self.api, method_name)
                result = method(**params)

                # Store result with descriptive key
                if method_name == "get_current_penalty":
                    penalty, conflicts = result
                    results["current_penalty"] = penalty
                    results["current_conflicts"] = conflicts
                elif method_name == "get_best_response_to":
                    results["best_response"] = result
                elif method_name == "simulate_neighbor_change":
                    # Use params to create descriptive key
                    neighbor_nodes = params.get("neighbor_nodes", {})
                    key = f"simulate_{list(neighbor_nodes.keys())[0] if neighbor_nodes else 'unknown'}"
                    results[key] = result
                else:
                    results[method_name] = result

                self.log(f"[TOOL][PHASE2] Executed {method_name}: {str(result)[:100]}")

            except Exception as e:
                self.log(f"[TOOL][PHASE2] Error executing {method_name}: {e}")
                results[f"{method_name}_error"] = str(e)

        return results

    def _translate_outbound(self, api_results: Dict[str, Any], original_message: str) -> Dict[str, Any]:
        """Phase 3: Translate API results to human natural language response.

        Uses LLM to convert structured API results into a natural language message.

        Parameters
        ----------
        api_results : Dict[str, Any]
            Results from Phase 2 API execution
        original_message : str
            Original human message for context

        Returns
        -------
        Dict[str, Any]
            Structured message for communication layer
            Example: {
                "should_send_message": true,
                "recipient": "Human",
                "message_type": "proposal",
                "structured_content": {
                    "my_assignments": {"a1": "green", "a2": "red"},
                    "reason": "Could you change h4 to blue? Then I can set a2 to red.",
                    "requested_changes": {"h4": "blue"}
                }
            }
        """
        # Identify visible neighbor nodes
        visible_neighbor_nodes = set()
        for u, v in self.problem.edges:
            if u in self.nodes and v not in self.nodes:
                visible_neighbor_nodes.add(v)
            elif v in self.nodes and u not in self.nodes:
                visible_neighbor_nodes.add(u)

        visible_neighbors_list = sorted(visible_neighbor_nodes)

        # Get boundary nodes
        boundary_nodes = []
        for node in self.nodes:
            for neighbor in self.problem.get_neighbors(node):
                if neighbor not in self.nodes:
                    boundary_nodes.append(node)
                    break

        prompt = f"""You are translating API results to natural language.

**Your Role**: Translation layer (NOT reasoning engine)
**Your Task**: Convert API results to human-friendly message

**CRITICAL**: The human asked you something. ANSWER THEIR QUESTION, don't ignore it!

**Context**:
- Your name: {self.name}
- Human said: "{original_message}"

**API Results**:
{json.dumps(api_results, indent=2)}

**Message Type Recognition**:

1. **Human declared constraint** ("h4 can't be green"):
   - Response: "Understood. I tested other colors for h4, and [h4=blue/red] works for me."
   - Show what alternatives DO work

2. **Human asked a question** ("Can that work?", "Is that possible?"):
   - Response: ANSWER THE QUESTION directly
   - "Yes, that works!" (if penalty=0) OR "No, that creates conflicts" (if penalty>0)
   - Then explain why or suggest alternative

3. **Human proposed conditional** ("h4=blue if h1=green"):
   - Response: Test and answer
   - "Yes, if h1=green and h4=blue, I can set a4=red and it works!"
   - OR "No, that doesn't work because [reason]"

4. **Human announced config**:
   - Response: Acknowledge and propose/accept
   - Standard proposal or acceptance

**Your nodes**:
- Boundary nodes (coordinate with human): {", ".join(boundary_nodes)}
- Internal nodes (silent updates): {", ".join(n for n in self.nodes if n not in boundary_nodes)}

**Visible neighbor nodes**: {", ".join(visible_neighbors_list) if visible_neighbors_list else "None"}

**Translation Rules**:

1. **If penalty == 0**: Send ACCEPTANCE
   - Set message_type="acceptance"
   - Set requested_changes={{}}
   - Reason: "Current configuration works!"

2. **If penalty > 0**: Send PROPOSAL
   - Set message_type="proposal"
   - Set requested_changes with SPECIFIC node-color pairs
   - Reason: "Could you change [node] from [old] to [new]?"

3. **Be Specific**:
   - Use exact node names (e.g., "h4", not "a neighboring node")
   - Use exact colors (e.g., "blue", not "a different color")
   - Template: "Could you change h4 from red to blue?"

4. **Partial Observability**:
   - ONLY mention visible neighbor nodes: {", ".join(visible_neighbors_list)}
   - ONLY mention your boundary nodes: {", ".join(boundary_nodes)}
   - NEVER mention internal nodes: {", ".join(n for n in self.nodes if n not in boundary_nodes)}

5. **Fill my_assignments**:
   - Use assignments from best_response result
   - This is YOUR plan (what you'll do)

**Output Format** (JSON only):
{{
  "should_send_message": true,
  "recipient": "Human",
  "message_type": "acceptance" | "proposal" | "rejection",
  "structured_content": {{
    "my_assignments": {{"a2": "red", "a4": "green"}},
    "reason": "Could you change h4 from red to blue? Then I can set a4 to green.",
    "requested_changes": {{"h4": "blue"}}
  }}
}}

**Decision Logic**:
1. Look at "current_penalty" in API results
2. If penalty == 0: Send acceptance message (requested_changes={{}})
3. If penalty > 0: Look for TESTED alternatives in simulation results
   - Search for keys starting with "simulation_" in API results
   - Example: "simulation_h4_blue": {{"penalty": 0.0, ...}}
   - Find simulations where penalty < 0.01 (these WORK!)
   - Extract node and color from key: "simulation_h4_blue" → node="h4", color="blue"
   - Propose the TESTED alternative in requested_changes
4. Use "best_response" for my_assignments
5. Be SPECIFIC in reason: "Could you change h4 from red to blue? I tested this and it works."

**CRITICAL**: If penalty > 0, you MUST use simulation results to find tested alternatives.
DO NOT propose arbitrary changes - only propose changes that were TESTED and have penalty=0.

Example API results with simulations:
{{
  "current_penalty": 1.0,
  "simulation_h4_blue": {{"penalty": 0.0, "conflicts": []}},
  "simulation_h4_green": {{"penalty": 0.5, "conflicts": [("a2", "h4")]}},
  "simulation_h4_red": {{"penalty": 1.0, "conflicts": [("a2", "h4")]}}
}}

In this case, you MUST propose h4=blue (penalty=0), NOT h4=green or h4=red.

Return ONLY the JSON object. No explanatory text."""

        try:
            response = self.backend_llm.chat.completions.create(
                model=self.backend_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,  # Deterministic translation
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            result_text = response.choices[0].message.content
            self.log(f"[TOOL][PHASE3] LLM response: {result_text[:200]}")

            result = json.loads(result_text)

            # Log translation
            self._log_translation("outbound", api_results, result)

            return result

        except Exception as e:
            self.log(f"[TOOL][PHASE3] Translation failed: {e}, using template fallback")

            # TEMPLATE FALLBACK: Generate message from API results
            # Extract key information
            current_penalty = api_results.get("current_penalty", 0)
            best_response = api_results.get("best_response", {})

            # Remove 'penalty' key from best_response if present
            my_assignments = {k: v for k, v in best_response.items() if k != 'penalty'}
            best_penalty = best_response.get("penalty", current_penalty)

            # Check if human asked a question
            original_lower = original_message.lower()
            is_question = any(q in original_lower for q in ["can", "work?", "possible?", "does that", "is that", "will that"])

            # Determine message type
            if is_question:
                # ANSWER THE QUESTION
                if best_penalty < 1e-6:
                    return {
                        "should_send_message": True,
                        "recipient": "Human",
                        "message_type": "acceptance",
                        "structured_content": {
                            "my_assignments": my_assignments,
                            "reason": "Yes, that works perfectly! I can make that configuration work.",
                            "requested_changes": {}
                        }
                    }
                else:
                    return {
                        "should_send_message": True,
                        "recipient": "Human",
                        "message_type": "rejection",
                        "structured_content": {
                            "my_assignments": my_assignments,
                            "reason": f"No, that doesn't work for me (penalty={current_penalty:.1f}). Let me suggest an alternative.",
                            "requested_changes": {}
                        }
                    }
            elif best_penalty < 1e-6:
                # Penalty is 0 - send acceptance
                return {
                    "should_send_message": True,
                    "recipient": "Human",
                    "message_type": "acceptance",
                    "structured_content": {
                        "my_assignments": my_assignments,
                        "reason": "The current configuration works well!",
                        "requested_changes": {}
                    }
                }
            else:
                # Penalty > 0 - send proposal based on TESTED alternatives
                # Use simulation results from Phase 1/2 to find what ACTUALLY works

                # Find all simulation results with penalty=0
                best_alternatives = []
                for key, value in api_results.items():
                    if key.startswith("simulation_") and isinstance(value, dict):
                        sim_penalty = value.get("penalty", float('inf'))
                        if sim_penalty < 1e-6:  # penalty == 0
                            # Extract node and color from key like "simulation_h4_blue"
                            parts = key.replace("simulation_", "").rsplit("_", 1)
                            if len(parts) == 2:
                                node, color = parts
                                best_alternatives.append((node, color, value))

                if best_alternatives:
                    # Use the first tested alternative that works
                    target_node, suggested_color, sim_result = best_alternatives[0]
                    current_color = self.neighbour_assignments.get(target_node, "unknown")

                    return {
                        "should_send_message": True,
                        "recipient": "Human",
                        "message_type": "proposal",
                        "structured_content": {
                            "my_assignments": my_assignments,
                            "reason": f"Could you change {target_node} from {current_color} to {suggested_color}? I tested this and it resolves the conflicts.",
                            "requested_changes": {target_node: suggested_color}
                        }
                    }

                # If no tested alternatives work, find visible neighbors
                visible_neighbor_nodes = set()
                for u, v in self.problem.edges:
                    if u in self.nodes and v not in self.nodes:
                        visible_neighbor_nodes.add(v)
                    elif v in self.nodes and u not in self.nodes:
                        visible_neighbor_nodes.add(u)

                if visible_neighbor_nodes:
                    # Pick first neighbor node and suggest a different color
                    target_node = sorted(visible_neighbor_nodes)[0]
                    current_color = self.neighbour_assignments.get(target_node, "unknown")
                    suggested_color = None
                    for c in self.domain:
                        if c != current_color:
                            suggested_color = c
                            break

                    if suggested_color:
                        return {
                            "should_send_message": True,
                            "recipient": "Human",
                            "message_type": "proposal",
                            "structured_content": {
                                "my_assignments": my_assignments,
                                "reason": f"Could you try changing {target_node} to {suggested_color}?",
                                "requested_changes": {target_node: suggested_color}
                            }
                        }

                # Fallback: generic message
                return {
                    "should_send_message": True,
                    "recipient": "Human",
                    "message_type": "proposal",
                    "structured_content": {
                        "my_assignments": my_assignments,
                        "reason": "I'm working on resolving the conflicts.",
                        "requested_changes": {}
                    }
                }

    def _send_translated_message(self, message_data: Dict[str, Any]) -> None:
        """Send message produced by outbound translation.

        Parameters
        ----------
        message_data : Dict[str, Any]
            Structured message from Phase 3
        """
        recipient = message_data.get("recipient", "Human")
        structured_content = message_data.get("structured_content", {})

        # Apply internal node assignments silently
        if "my_assignments" in structured_content:
            proposed = structured_content["my_assignments"]

            # Identify boundary nodes
            boundary_nodes = set()
            for node in self.nodes:
                for neighbor in self.problem.get_neighbors(node):
                    if neighbor not in self.nodes:
                        boundary_nodes.add(node)
                        break

            # Only apply internal nodes (non-boundary)
            for node, color in proposed.items():
                if node in self.nodes and node not in boundary_nodes:
                    self.assignments[node] = color
                    self.log(f"[TOOL] Silent update: {node} -> {color}")

        # CRITICAL: Update my_assignments to match current self.assignments before formatting
        # This ensures [report: ...] tag matches actual internal state (fixes UI inconsistency)
        structured_content["my_assignments"] = dict(self.assignments)
        message_data["structured_content"] = structured_content

        # Format via comm layer
        if hasattr(self.comm_layer, 'format_message'):
            nl_message = self.comm_layer.format_message(
                sender=self.name,
                recipient=recipient,
                message_data=message_data
            )
        else:
            # Fallback
            nl_message = structured_content.get("reason", "Configuration updated.")
            import json
            nl_message += f" [report: {json.dumps(self.assignments)}]"

        self.log(f"[TOOL] Sending to {recipient}: {nl_message[:100]}...")
        self.send(recipient, nl_message)

    def receive(self, msg: Any) -> None:
        """Handle incoming messages.

        Parameters
        ----------
        msg : Message
            Incoming message
        """
        self.log(f"[TOOL] receive() called - content: {getattr(msg, 'content', 'N/A')}")

        # Handle special tokens
        if hasattr(msg, 'content') and msg.content == "__ANNOUNCE_CONFIG__":
            self.log(f"[TOOL] Announcement trigger from {msg.sender}")
            self._handle_announce_config(msg.sender)
            return

        # Handle color update dicts
        if hasattr(msg, 'content') and isinstance(msg.content, str):
            content_str = msg.content.strip()
            if content_str.startswith('{') and content_str.endswith('}'):
                try:
                    import ast
                    color_update = ast.literal_eval(content_str)
                    if isinstance(color_update, dict):
                        self.log(f"[TOOL] Color update: {color_update}")
                        self.neighbour_assignments.update(color_update)
                        return
                except:
                    pass

        # Normal message
        super().receive(msg)
        self._received_human_message_this_turn = True

        # Store message text
        if hasattr(msg, 'content'):
            if isinstance(msg.content, str):
                self._last_human_text = msg.content
            elif isinstance(msg.content, dict):
                self._last_human_text = msg.content.get('text', '')

    def _send_automatic_announcement(self) -> None:
        """Send automatic announcement to all neighbors on first step."""
        if self._config_announced:
            return

        self.log("[TOOL] Sending automatic announcement")
        self._config_announced = True
        self._phase = "bargain"

        # CRITICAL FIX: Recompute assignments BEFORE announcing!
        # Initial assignments are random and may conflict with neighbor colors.
        # We must compute assignments that respect known neighbor constraints.
        if self.neighbour_assignments:
            self.log(f"[TOOL] Recomputing assignments to respect neighbor constraints: {self.neighbour_assignments}")
            self.assignments = self.compute_assignments()
            self.log(f"[TOOL] Recomputed assignments: {self.assignments}")
        else:
            self.log("[TOOL] WARNING: No neighbor assignments known yet - announcing with initial (possibly random) assignments")

        # Get boundary nodes
        boundary = [n for n in self.nodes
                   if any((n, ext) in self.problem.edges or (ext, n) in self.problem.edges
                         for ext in self.neighbour_assignments.keys())]

        if not boundary:
            self.log("[TOOL] No boundary nodes to announce")
            return

        # Build announcement
        report = {n: self.assignments.get(n) for n in boundary if self.assignments.get(n)}
        self.log(f"[TOOL] Announcing: {report}")

        # Send to all neighbors
        for recipient in self.neighbour_assignments.keys():
            announcement = {
                "type": "announcement",
                "data": {"assignments": report},
                "report": report
            }
            self.send(recipient, announcement)
            self.log(f"[TOOL] Announced to {recipient}")

    def _handle_announce_config(self, recipient: str) -> None:
        """Handle announcement phase."""
        self.log(f"[TOOL] _handle_announce_config for {recipient}")

        if self._config_announced:
            self.log(f"[TOOL] Already announced")
            return

        self._config_announced = True
        self._phase = "bargain"

        # CRITICAL FIX: Recompute assignments considering human's announced colors!
        # At this point, _sync_neighbour_views() has already populated neighbour_assignments
        # with the human's colors. We MUST recompute to avoid conflicts.
        if self.neighbour_assignments:
            self.log(f"[TOOL] Recomputing assignments to respect human's announced colors: {self.neighbour_assignments}")
            self.assignments = self.compute_assignments()
            self.log(f"[TOOL] Recomputed assignments: {self.assignments}")
        else:
            self.log(f"[TOOL] WARNING: No neighbor assignments available - using initial assignments")

        # Get boundary nodes
        boundary = [n for n in self.nodes
                   if any((n, ext) in self.problem.edges or (ext, n) in self.problem.edges
                         for ext in self.neighbour_assignments.keys())]

        if boundary:
            report = {n: self.assignments.get(n) for n in boundary if self.assignments.get(n)}
            announcement = {
                "type": "announcement",
                "data": {"assignments": report},
                "report": report
            }
            self.send(recipient, announcement)
            self.log(f"[TOOL] Announced to {recipient}: {report}")

    def _log_translation(self, phase: str, input_data: Any, output_data: Any) -> None:
        """Log translation for research traceability."""
        import time
        log_entry = {
            "timestamp": time.time(),
            "agent": self.name,
            "event": f"translation_{phase}",
            "input": str(input_data)[:500],
            "output": str(output_data)[:500]
        }

        try:
            trace_file = getattr(self, '_trace_file', None)
            if trace_file:
                with open(trace_file, 'a') as f:
                    f.write(json.dumps(log_entry, default=str) + '\n')
        except Exception as e:
            self.log(f"[TOOL] Failed to write trace: {e}")
