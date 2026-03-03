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

            # SAFETY: Programmatic validation — Phase 3 must not accept when penalty > 0
            if response_message.get("message_type") == "acceptance":
                can_accept = api_results.get("__can_accept_current__", False)
                if not can_accept:
                    min_pen = api_results.get("current_best_response", {}).get("penalty", "?")
                    self.log(
                        f"[TOOL] OVERRIDE: Phase 3 wrongly accepted (penalty={min_pen}). "
                        "Converting to proposal."
                    )
                    # Best assignments for current state (even if still conflicted)
                    best_assign = api_results.get("__assignments_if_accepting__", dict(self.assignments))
                    # Find which neighbor nodes conflict with best_assign
                    requested_changes = {}
                    for u, v in self.problem.edges:
                        my_node = u if u in self.nodes else (v if v in self.nodes else None)
                        nb_node = v if u in self.nodes else (u if v in self.nodes else None)
                        if my_node and nb_node and nb_node in self.neighbour_assignments:
                            my_col = best_assign.get(my_node)
                            nb_col = self.neighbour_assignments[nb_node]
                            if my_col and nb_col and my_col == nb_col:
                                # conflict: suggest a different color for the neighbor
                                for alt in self.domain:
                                    if alt != nb_col:
                                        requested_changes[nb_node] = alt
                                        break
                    sc = response_message.get("structured_content", {})
                    sc["my_assignments"] = best_assign
                    sc["requested_changes"] = requested_changes
                    if not sc.get("reason") and requested_changes:
                        node, color = next(iter(requested_changes.items()))
                        sc["reason"] = f"Could you change {node} to {color}?"
                    response_message["message_type"] = "proposal"
                    response_message["structured_content"] = sc

            # Send message if translation produced one
            if response_message.get("should_send_message"):
                # On acceptance: apply ALL my_assignments (including boundary nodes) NOW so
                # that self.assignments is in the committed state before the next step().
                # This prevents flip-flopping: we committed to a conflict-free plan, so
                # we should live in that state immediately.
                if response_message.get("message_type") == "acceptance":
                    sc = response_message.get("structured_content", {})
                    committed = sc.get("my_assignments", {})
                    for node, color in committed.items():
                        if node in self.nodes:
                            self.assignments[node] = color
                    self.log(f"[TOOL] Committed acceptance assignments: {dict(self.assignments)}")

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

"I've set h1=red, h2=blue" (announcement):
  → get_current_penalty(), get_best_response_to() [test current state first]
  → ALSO test get_best_response_to for each visible neighbor with each alternative color:
    e.g. if visible neighbors are h1=red and h4=red, also call:
    get_best_response_to({{"h1": "blue", "h4": "red"}}),
    get_best_response_to({{"h1": "green", "h4": "red"}}),
    get_best_response_to({{"h1": "red", "h4": "blue"}}),
    get_best_response_to({{"h1": "red", "h4": "green"}})
  → This ensures Phase 3 always has TESTED conflict-free alternatives to propose

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
                    # Build a unique key from the neighbor_assignments params so that
                    # multiple calls (one per alternative) don't overwrite each other.
                    neighbor_args = params.get("neighbor_assignments", {})
                    if neighbor_args:
                        suffix = "_".join(f"{n}{c[:1]}" for n, c in sorted(neighbor_args.items()))
                        key = f"best_response_{suffix}"
                    else:
                        # Fallback: count existing keys to avoid collision
                        existing = sum(1 for k in results if k.startswith("best_response"))
                        key = f"best_response_{existing}" if existing else "best_response"
                    results[key] = result
                elif method_name == "simulate_neighbor_change":
                    # Build a unique key from ALL neighbor_nodes values, not just the first key.
                    neighbor_nodes = params.get("neighbor_nodes", {})
                    if neighbor_nodes:
                        suffix = "_".join(f"{n}{c[:1]}" for n, c in sorted(neighbor_nodes.items()))
                        key = f"simulate_{suffix}"
                    else:
                        existing = sum(1 for k in results if k.startswith("simulate_"))
                        key = f"simulate_{existing}"
                    results[key] = result
                else:
                    results[method_name] = result

                self.log(f"[TOOL][PHASE2] Executed {method_name}: {str(result)[:100]}")

            except Exception as e:
                self.log(f"[TOOL][PHASE2] Error executing {method_name}: {e}")
                results[f"{method_name}_error"] = str(e)

        # --- DECISION GUIDE: always compute best response for CURRENT neighbor state ---
        # Phase 3 must check THIS field (not a dynamically-named best_response_xyz key)
        # to determine whether acceptance is valid.
        try:
            current_br = self.api.get_best_response_to()   # uses current neighbour_assignments
            results["current_best_response"] = current_br
            can_accept = current_br.get("penalty", float("inf")) < 1e-6
            results["__can_accept_current__"] = can_accept
            results["__assignments_if_accepting__"] = {
                k: v for k, v in current_br.items() if k != "penalty"
            }
            self.log(
                f"[TOOL][PHASE2] Decision guide: __can_accept_current__={can_accept}, "
                f"penalty={current_br.get('penalty')}"
            )
        except Exception as e:
            self.log(f"[TOOL][PHASE2] Could not compute decision guide: {e}")
            results["__can_accept_current__"] = False
            results["__assignments_if_accepting__"] = dict(self.assignments)

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

3. **Human proposed conditional with MULTIPLE ALTERNATIVES** ("If h1=red I could do either blue or red for h4"):
   - The API results contain MULTIPLE best_response_* or simulate_* keys, one per alternative
   - CRITICAL: Check EACH alternative's penalty separately
   - Report which specific alternatives work: "Both work!" or "Only h4=blue works"
   - Do NOT say "current configuration works" — you are answering about FUTURE scenarios
   - Example: "I tested both options: h4=red works (I'd use a4=blue, a5=green) and h4=blue also works
     (I'd use a4=blue, a5=red). Either is fine with me!"
   - If only one works: "h4=red doesn't work for me, but h4=blue does. Could you go with h4=blue?"

4. **Human proposed single conditional** ("h4=blue if h1=green"):
   - Response: Test and answer
   - "Yes, if h1=green and h4=blue, I can set a4=red and it works!"
   - OR "No, that doesn't work because [reason]"

5. **Human announced config**:
   - Response: Acknowledge and propose/accept
   - Standard proposal or acceptance

**Your nodes**:
- Boundary nodes (coordinate with human): {", ".join(boundary_nodes)}
- Internal nodes (silent updates): {", ".join(n for n in self.nodes if n not in boundary_nodes)}

**Visible neighbor nodes**: {", ".join(visible_neighbors_list) if visible_neighbors_list else "None"}

**CRITICAL RULE — How to decide acceptance vs proposal**:

Use the pre-computed boolean `__can_accept_current__` (NOT current_penalty, NOT best_response_*):

- **`__can_accept_current__` == true**:
  → Send ACCEPTANCE. The current neighbor colors are fine.
  → Set message_type="acceptance", requested_changes={{}}
  → my_assignments = exactly `__assignments_if_accepting__` (do not invent new ones!)

- **`__can_accept_current__` == false**:
  → Even after optimally recoloring my nodes, conflicts remain with the CURRENT neighbor state.
  → I need the neighbor to change. Send PROPOSAL.
  → Look at simulate_* or best_response_* keys in the results for tested alternatives.
  → Find one where penalty==0, then propose those neighbor colors.
  → my_assignments = assignments from the TESTED scenario that gives penalty=0
  → requested_changes = the neighbor node(s) that need to change for that scenario

**Be Specific**:
- Use exact node names (e.g., "h4", not "a neighboring node")
- Use exact colors (e.g., "blue", not "a different color")

**Partial Observability**:
- ONLY mention visible neighbor nodes: {", ".join(visible_neighbors_list)}
- ONLY mention your boundary nodes: {", ".join(boundary_nodes)}
- NEVER mention internal nodes: {", ".join(n for n in self.nodes if n not in boundary_nodes)}

**Fill my_assignments**:
- For acceptance: use EXACTLY `__assignments_if_accepting__` — never invent your own
- For proposal: use assignments from the tested alternative scenario that gives penalty=0

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

STEP 1 — Identify what the human was asking about:
- Did they ask about a FUTURE scenario ("if I did X")? → answer about that scenario, NOT current state
- Did they announce their CURRENT colors? → answer about current state

STEP 2 — Identify how many scenarios were tested:
- Count keys starting with "best_response_" or "simulate_" in API results
- If there are MULTIPLE such keys → human offered alternatives; evaluate EACH one separately
- Each key's "penalty" field tells you if that specific scenario works

STEP 3 — Choose response type:
A. **Multiple alternatives tested** (multiple best_response_* keys):
   - List EACH alternative and whether it works (penalty < 0.01 = works)
   - If ALL work → "Both/all options work for me!"
   - If SOME work → "Only [option X] works; [option Y] doesn't"
   - If NONE work → negotiate with specific counter-proposal
   - Use message_type="acceptance" if at least one works and you're agreeing to an offer
   - Populate my_assignments from the first best_response_* key that has penalty < 0.01
   - Do NOT set requested_changes (empty {{}}) — this is acceptance of their offer

B. **Single scenario tested** (one best_response or simulate key):
   - If that scenario's penalty == 0 → acceptance
   - If penalty > 0 → proposal with tested alternative

C. **Current state** (announcement or config update):
   - FIRST and ONLY decision gate: `__can_accept_current__`
   - If TRUE → ACCEPT: my_assignments = `__assignments_if_accepting__`, requested_changes={{}}
   - If FALSE → PROPOSE: look for simulate_* or best_response_* alternatives with penalty=0
   - NEVER invent my_assignments — always copy from `__assignments_if_accepting__` or a tested key

STEP 4 — Use "best_response" (or best_response_*) for my_assignments

Example: multiple alternatives both work:
{{
  "best_response_h1r_h4b": {{"a4": "blue", "a5": "red", "penalty": 0.0}},
  "best_response_h1r_h4r": {{"a4": "blue", "a5": "green", "penalty": 0.0}}
}}
→ Response: "Both options work for me! If you do h1=red with h4=blue I'd use a4=blue,a5=red;
   if you do h1=red with h4=red I'd use a4=blue,a5=green."

Example: only one alternative works:
{{
  "best_response_h1r_h4b": {{"a4": "blue", "a5": "red", "penalty": 0.0}},
  "best_response_h1r_h4r": {{"a4": "blue", "a5": "green", "penalty": 2.0}}
}}
→ Response: "h4=blue works for me (I'd use a4=blue,a5=red) but h4=red doesn't work."

Example: single simulation (legacy format):
{{
  "current_penalty": 1.0,
  "simulate_h4b": {{"new_penalty": 0.0, "conflicts": []}},
  "simulate_h4g": {{"new_penalty": 0.5, "conflicts": [("a2", "h4")]}}
}}
→ Propose h4=blue (penalty=0), NOT h4=green.

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
