"""ReAct agent using Reasoning and Acting pattern for backend reasoning.

This module implements the LLM_REACT mode where a backend LLM uses the ReAct
(Reasoning and Acting) pattern to solve graph coloring. The agent alternates
between thinking (reasoning about the problem) and acting (calling API functions),
building up a thought→action→observation trajectory until ready to respond.

Architecture:
    Speech LLM ↔ Backend LLM (ReAct loop) ↔ API Library

The ReAct pattern makes the agent's reasoning explicit and traceable, which is
valuable for research into human-AI coordination.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import os
import re

from .cluster_agent import ClusterAgent
from .cluster_agent_api import ClusterAgentAPI


class ReActClusterAgent(ClusterAgent):
    """Agent using ReAct pattern for backend reasoning.

    This agent uses a backend LLM with the ReAct (Reasoning and Acting) pattern
    to reason about graph coloring decisions. The LLM alternates between:
    - Thought: Reasoning about the current situation
    - Action: Calling an API function
    - Observation: Processing the function result

    After several thought-action-observation cycles, the LLM provides a
    Final Answer with its decision.

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
        OpenAI model for backend reasoning (default: "gpt-4-turbo")
    max_react_iterations : int, optional
        Maximum ReAct iterations per step (default: 10)
    **kwargs
        Additional arguments passed to ClusterAgent

    Attributes
    ----------
    api : ClusterAgentAPI
        API library for graph coloring operations
    backend_llm : OpenAI
        Backend LLM client
    react_prompt : str
        ReAct system prompt with examples
    max_react_iterations : int
        Maximum iterations per reasoning loop
    """

    def __init__(
        self,
        name: str,
        problem: Any,
        comm_layer: Any,
        local_nodes: List[str],
        owners: Dict[str, str],
        backend_model: str = "gpt-4-turbo",
        max_react_iterations: int = 10,
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
            self.log(f"[REACT] Backend LLM initialized successfully")
        except FileNotFoundError as e:
            error_msg = f"[REACT] FATAL: {e}\nLLM_REACT mode requires OpenAI API key. Cannot continue."
            print(f"\n{'='*70}\nERROR: {error_msg}\n{'='*70}\n")
            raise SystemExit(error_msg)
        except Exception as e:
            error_msg = f"[REACT] FATAL: Failed to initialize OpenAI client: {e}\nLLM_REACT mode requires valid API key. Cannot continue."
            print(f"\n{'='*70}\nERROR: {error_msg}\n{'='*70}\n")
            raise SystemExit(error_msg)

        # Load ReAct prompt
        self.react_prompt = self._load_react_prompt()
        self.max_react_iterations = max_react_iterations

        # Flag to generate first message after announcement
        self._should_generate_first_message = False

        self.log(f"[REACT] Initialized ReActClusterAgent with model={backend_model}, max_iterations={max_react_iterations}")

    def _load_api_key(self) -> str:
        """Load OpenAI API key from api_key.txt."""
        key_file = "api_key.txt"
        if os.path.exists(key_file):
            with open(key_file, "r") as f:
                return f.read().strip()
        else:
            raise FileNotFoundError("api_key.txt not found. Please create it with your OpenAI API key.")

    def _load_react_prompt(self) -> str:
        """Load ReAct system prompt with examples.

        Returns
        -------
        str
            ReAct system prompt
        """
        return """You are a graph coloring agent using the ReAct (Reasoning and Acting) pattern.

**Your format**:
- Thought: [your reasoning about the current situation]
- Action: [function_name(arguments)]
- [System provides Observation: [result]]

After several thought-action-observation cycles, when ready to make a decision:
- Thought: [final reasoning]
- Final Answer: [JSON with your decision]

**Available actions** (use the RIGHT action for each task):

**For analyzing current state**:
- get_current_penalty(): Check which edges have conflicts (use this FIRST!)
- get_conflict_resolution_options(max_options=5): Get solutions for conflicts

**For testing YOUR nodes**:
- compute_assignments(): Run exhaustive solver on your nodes (finds optimal solution)
- test_configuration(assignments={...}): Test if YOUR assignments work
- check_feasibility(node="a4", color="blue"): Test if YOUR node can be a color
- get_available_colors(node="a4"): Get valid colors for YOUR node

**For testing NEIGHBOR node changes** (CRITICAL FOR NEGOTIATION):
- simulate_neighbor_change(neighbor_nodes={"h4": "blue"}): Test if neighbor changing h4 to blue resolves conflicts
  * This is THE action to use when testing "what if the human changes h4 to blue?"
  * Returns penalty with that hypothetical change
  * Example: simulate_neighbor_change(neighbor_nodes={"h4": "blue", "h1": "green"})
- get_best_response_to(neighbor_assignments={"h4": "blue"}): Get your best response if neighbor uses these colors

**CRITICAL**: DON'T use check_feasibility() for neighbor nodes - use simulate_neighbor_change() instead!

**Example 1** (ALWAYS CHECK ACCEPTANCE FIRST):
Thought: First, I should check if I can achieve penalty=0 with the human's CURRENT settings. I must use ALL neighbor nodes I know about - h1, h2, h3, h4, h5 from their announcement.
Action: get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"})
Observation: {"a1": "green", "a2": "red", "a3": "red", "a4": "blue", "penalty": 0}

Thought: Perfect! I can achieve penalty=0 with their current settings (using ALL neighbor colors). I should accept this!
Final Answer: {
  "should_send_message": true,
  "recipient": "Human",
  "message_type": "acceptance",
  "structured_content": {
    "my_assignments": {"a1": "green", "a2": "red", "a3": "red", "a4": "blue"},
    "reason": "Great! With your current settings, I can achieve penalty=0.",
    "requested_changes": {}
  }
}

**Example 2** (negotiation if current config doesn't work):
Thought: I need to check if my current assignment has any conflicts with the human's boundary nodes.
Action: get_current_penalty()
Observation: {"penalty": 20, "conflicts": [("a4", "h4"), ("a2", "h1")]}

Thought: Let me check if I can find a penalty-free solution with their CURRENT colors first. I must use ALL neighbor colors from their announcement.
Action: get_best_response_to(neighbor_assignments={"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"})
Observation: {"a1": "green", "a2": "blue", "a3": "red", "a4": "blue", "penalty": 20}

Thought: Still penalty=20, so I need to request changes. Let me test if changing h4 to blue would help. CRITICAL: I must pass ALL neighbor colors, not just h4!
Action: simulate_neighbor_change(neighbor_nodes={"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"})
Observation: {"penalty": 10, "conflicts": [("a2", "h1")], "feasible": false}

Thought: That only partially helps. Let me test changing both h4 to blue AND h1 to green. Again, I must include ALL neighbors.
Action: simulate_neighbor_change(neighbor_nodes={"h1": "green", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"})
Observation: {"penalty": 0, "conflicts": [], "feasible": true}

Thought: Perfect! Now I need to get MY PLAN - what assignments I'll use if they accept.
Action: get_best_response_to(neighbor_assignments={"h4": "blue", "h1": "green"})
Observation: {"a1": "green", "a2": "red", "a3": "red", "a4": "green"}

Thought: Great! Now I have a complete package deal: they change h4 and h1, I change a2 and a4. Let me make the proposal.
Final Answer: {
  "should_send_message": true,
  "recipient": "Human",
  "message_type": "proposal",
  "structured_content": {
    "my_assignments": {"a1": "green", "a2": "red", "a3": "red", "a4": "green"},
    "reason": "Could you change h4 from red to blue and h1 from red to green? Then I'll set a2=red and a4=green, giving us penalty=0.",
    "requested_changes": {"h4": "blue", "h1": "green"}
  }
}

**CRITICAL**: Notice the example uses simulate_neighbor_change() for testing neighbor nodes, NOT check_feasibility()!

**Workflow** (ALWAYS follow this order):
1. **ALWAYS check acceptance FIRST**: Call get_best_response_to() with **ALL** CURRENT neighbor assignments
   - **CRITICAL**: Must include ALL neighbor nodes you know about (e.g., all of h1, h2, h3, h4, h5)
   - **WRONG**: get_best_response_to({"h4": "red"}) - incomplete!
   - **CORRECT**: get_best_response_to({"h1": "red", "h2": "blue", "h3": "green", "h4": "red", "h5": "green"}) - all neighbors!
2. If penalty=0 → SET should_send_message=true, message_type="acceptance", requested_changes={{}}, reason="Current configuration works perfectly!"
3. If penalty > 0 → Negotiate (test alternatives with simulate_neighbor_change), then SET should_send_message=true, message_type="proposal" with specific requested_changes

**Guidelines**:
1. Think step-by-step before acting
2. Use actions to gather information (don't guess)
3. **CRITICAL**: ALWAYS check if current config works before asking for changes!
4. When conflicts exist with BOUNDARY NODES, ASK the neighbor to change them
5. Only change your own nodes if the neighbor explicitly requests it
6. Be collaborative: focus on what the NEIGHBOR needs to change, not your own nodes
7. **PARTIAL OBSERVABILITY**: You can ONLY see neighbor nodes with edges to your cluster!

**Node types**:
- **Internal nodes**: Your nodes with no external edges (you can freely modify these)
- **Boundary nodes**: Your nodes with edges to other clusters (coordinate these with neighbors)
- **Visible neighbor nodes**: Neighbor nodes with edges to your cluster (you can see and mention these)
- **Invisible neighbor nodes**: Neighbor nodes with NO edges to your cluster (you CANNOT see or mention these!)

**Strategy**:
1. Think: Identify conflicts and potential solutions
2. Action: Call get_current_penalty() to see WHICH edges conflict
3. **Action: Call simulate_neighbor_change() to TEST MULTIPLE solutions** (CRITICAL):
   - **ALWAYS pass COMPLETE neighbor assignments (all known neighbors)**
   - Only CHANGE the nodes you're testing, KEEP others at current colors
   - Example: If testing h4=blue and you know 5 neighbors, pass ALL 5:
     simulate_neighbor_change(neighbor_nodes={"h1": "red", "h2": "blue", "h3": "green", "h4": "blue", "h5": "green"})
   - Test multiple alternatives with complete configs
   - **ONLY propose alternatives where penalty=0 (or very close to 0)**
   - **DO NOT propose untested alternatives - always simulate first!**
4. **Action: Call get_best_response_to() to get YOUR PLAN**:
   - Example: get_best_response_to(neighbor_assignments={"h4": "blue"})
   - This returns YOUR optimal assignments if h4 becomes blue
   - **CRITICAL**: This is YOUR commitment - what YOU'LL do if request is accepted!
5. Action: Modify internal nodes silently to resolve local conflicts
6. Think: Choose the BEST specific solution (penalty=0 from simulations)
7. **MANDATORY**: If penalty > 0, you MUST:
   - Find a simulation with penalty=0
   - Include those tested node-color pairs in requested_changes
   - Do NOT propose arbitrary changes - only TESTED ones!
8. Final Answer: Make SPECIFIC request with YOUR PLAN (package deal: "You do X, I'll do Y")

**When to send a message**:
- **acceptance**: You checked get_best_response_to() with CURRENT neighbor colors and found penalty=0 → ALWAYS SEND acceptance message! Set message_type="acceptance", requested_changes={{}} (empty)
- **proposal**: You have a concrete request (change h4 to blue) with a plan → SEND proposal message
- **rejection**: Neighbor's suggestion doesn't work, offer alternative → SEND rejection message
- NEVER send "still working" or "analyzing" messages - these are useless!
- ONLY set should_send_message=false if you literally have nothing to report (this should be rare!)

**Final Answer format** (**CRITICAL**: Must be valid JSON, not plain text!):
**YOU MUST OUTPUT**: Final Answer: {{ valid JSON object }}

Format:
{{
  "should_send_message": true/false,  // FALSE if you have nothing concrete to say
  "recipient": "Human" or neighbor name,
  "message_type": "proposal" | "question" | "acceptance" | "rejection" | "info",
  "structured_content": {{
    "my_assignments": {{"a1": "red", "a3": "blue", "a4": "green"}},  // YOUR PLAN from get_best_response_to()!
    "reason": "Could you change h4 from red to blue? Then I can set a4=green, giving us penalty=0.",
    "requested_changes": {{"h4": "blue"}}  // REQUIRED: Exact node names and target colors!
  }}
}}

**DO NOT write explanatory text after tool observations - go straight to Final Answer with JSON!**

**CRITICAL REQUIREMENTS FOR "reason" FIELD**:
1. Must use TEMPLATE: "Could you change [exact_node] from [current_color] to [new_color]?"
2. Or IF-THEN: "If you set [node]=[color], then I can set [my_boundary]=[color]"
3. Must specify EXACT node names (e.g., "h4", not "a neighboring node")
4. Must specify EXACT colors (e.g., "blue", not "a different color")
5. Only mention your boundary nodes and visible neighbor nodes
6. NEVER say "make a change" or "adjust colors" - always specify exact node and color!

**CRITICAL REQUIREMENTS FOR "my_assignments" FIELD**:
1. **REQUIRED**: Must be from get_best_response_to(neighbor_assignments={...})
2. This is YOUR PLAN - what YOU will do if requested_changes is accepted
3. Example: If requesting h4=blue, call get_best_response_to({"h4": "blue"}) to get your plan
4. This makes it a PACKAGE DEAL: "You do X, I'll do Y, we both win"

**CRITICAL REQUIREMENTS FOR "requested_changes" FIELD**:
1. **REQUIRED**: Cannot be empty if penalty > 0 and message_type is "proposal" or "info"
2. Must contain at least one specific node-color pair when making requests
3. **CRITICAL**: Must contain ONLY NEIGHBOR nodes (NOT your own nodes!)
4. Example GOOD: {"h4": "blue", "h1": "green"} (exact nodes, exact colors)
5. Example BAD: {}  ❌ INVALID - empty when conflicts exist!
6. Example BAD: {"a5": "green"}  ❌ INVALID - a5 is YOUR node, not neighbor's!

**VALIDATION CHECKLIST** (before Final Answer):
- [ ] If penalty > 0: Does requested_changes contain at least one node-color pair?
- [ ] Have I tested alternatives with simulate_neighbor_change()?
- [ ] **Have I called get_best_response_to() to get my_assignments?** ← CRITICAL!
- [ ] **Are ALL nodes in requested_changes NEIGHBOR nodes?** ← CRITICAL!
- [ ] Does reason field use exact node names (not "a neighboring node")?
- [ ] Does reason field use exact colors (not "a different color")?
- [ ] Do I have something concrete to say? (If not, set should_send_message=false!)
- [ ] If requested_changes contains YOUR OWN nodes: REMOVE them! Only request NEIGHBOR nodes!

Begin your reasoning with: Thought: [your first thought]
"""

    def _build_context(self) -> str:
        """Build context string with current graph state.

        Returns
        -------
        str
            Context description
        """
        penalty, conflicts = self.api.get_current_penalty()
        boundary_nodes = self.api.get_boundary_nodes()
        internal_nodes = [n for n in self.nodes if n not in boundary_nodes]

        # CRITICAL: Identify VISIBLE neighbor nodes (partial observability)
        # Only show neighbor nodes that have edges to this agent's cluster
        visible_neighbor_nodes = set()
        for u, v in self.problem.edges:
            if u in self.nodes and v not in self.nodes:
                visible_neighbor_nodes.add(v)
            elif v in self.nodes and u not in self.nodes:
                visible_neighbor_nodes.add(u)

        # Filter neighbor assignments to only visible nodes
        visible_neighbor_assignments = {
            node: color for node, color in self.neighbour_assignments.items()
            if node in visible_neighbor_nodes
        }

        # Build conversation history
        conversation_history = ""
        recent_messages = list(self.received_messages[-4:]) + list(self.sent_messages[-4:])
        recent_messages.sort(key=lambda m: getattr(m, 'timestamp', 0) if hasattr(m, 'timestamp') else 0)

        if recent_messages:
            conversation_history = "\n**Recent Conversation History**:\n"
            for msg in recent_messages:
                sender = getattr(msg, 'sender', 'Unknown')
                content_preview = str(getattr(msg, 'content', ''))[:150]
                conversation_history += f"- {sender}: {content_preview}\n"
            conversation_history += "\n**IMPORTANT**: Human messages include current config in [config: {...}] tag.\n"
            conversation_history += "This tells you their CURRENT state. Extract and use this information!\n"
            conversation_history += "REMEMBER: Don't repeat requests that were already accepted! Track what the neighbor agreed to.\n"

        context = f"""**IDENTITY**:
- Your name: {self.name}
- Your role: Coordinate with neighbors to resolve conflicts

**YOUR NODES** (you control these):
- INTERNAL nodes: {", ".join(internal_nodes)} (modify these freely, silently)
- BOUNDARY nodes: {", ".join(boundary_nodes)} (coordinate these with neighbors)
- Current assignments: {self.assignments}

**CRITICAL - READ CAREFULLY**:
- YOU control nodes: {", ".join(self.nodes)} ← These are YOUR nodes
- NEIGHBOR controls: {", ".join(sorted(visible_neighbor_nodes)) if visible_neighbor_nodes else "None yet"} ← These are THEIR nodes
- ❌ NEVER ask neighbor to change YOUR nodes ({", ".join(self.nodes)})!
- ✅ ONLY ask neighbor to change THEIR nodes ({", ".join(sorted(visible_neighbor_nodes)) if visible_neighbor_nodes else "None"})!
- If you need to change YOUR nodes, just do it silently (update my_assignments)

**VISIBLE NEIGHBOR NODES** (partial observability - you can ONLY see these):
- Visible nodes: {", ".join(sorted(visible_neighbor_nodes)) if visible_neighbor_nodes else "None yet"}
- Their assignments: {visible_neighbor_assignments}
- You CANNOT see other neighbor nodes (they don't have edges to your cluster)

**Available colors**: {", ".join(self.domain)}
**Current penalty**: {penalty}
**Conflicts**: {len(conflicts)} edge conflicts
**Feasible**: {"Yes" if penalty < 1e-6 else "No"}

**Neighbors**: {", ".join(set(self.owners.values()) - {self.name})}
{conversation_history}

**CRITICAL NEGOTIATION RULES**:
1. FIRST: Silently modify INTERNAL nodes ({", ".join(internal_nodes)}) to resolve local conflicts
2. THEN: If still needed, request neighbor to change THEIR VISIBLE nodes
3. NEVER modify BOUNDARY nodes ({", ".join(boundary_nodes)}) - coordinate these

**CRITICAL MESSAGE RULES** (PARTIAL OBSERVABILITY):
Your messages must ONLY mention:
- YOUR BOUNDARY NODES: {", ".join(boundary_nodes)}
- VISIBLE NEIGHBOR NODES: {", ".join(sorted(visible_neighbor_nodes)) if visible_neighbor_nodes else "None"}
- NEVER YOUR INTERNAL NODES: {", ".join(internal_nodes)}
- NEVER INVISIBLE NODES: You cannot mention nodes you don't have edges to!

**Examples of GOOD messages (like RB mode)**:
✅ "Could you change h4 from red to blue? That would let me keep a4=red."
   (SPECIFIC: exact node h4, exact color blue, mentions only boundary a4)

✅ "If you set h1=blue and h4=green, then I can set a2=red and a5=blue."
   (IF-THEN structure, specific nodes/colors, only boundaries)

**Examples of BAD messages (DO NOT DO THIS)**:
❌ "I've set a1=red, a2=blue, a3=green, a4=red" (mentions internal a1, a3)
❌ "I've assigned colors to my nodes" (mentions all nodes, not specific)
❌ "Could you adjust your colors?" (too vague, not actionable)
❌ "I suggest we consider changing the color of a neighboring node" (VAGUE - which node? what color?)
❌ "Please make a change to resolve conflicts" (VAGUE - what specific change?)
❌ "We should modify some boundary nodes" (VAGUE - which nodes? what colors?)
❌ "Change h1, h2, h3" (mentions nodes not in your visible set - VIOLATES PARTIAL OBSERVABILITY!)

**Goal**: Make SPECIFIC, ACTIONABLE requests like RB mode.
**REQUIRED FORMAT**: Every request MUST specify exact node names and exact target colors!
"""
        return context

    def step(self) -> None:
        """Execute ReAct reasoning loop."""

        # Automatic announcement on first step
        if self._phase == "configure" and not self._config_announced:
            self.log("[REACT] In configure phase, sending automatic announcement")
            self._send_automatic_announcement()
            return

        # Check if we have backend LLM
        if self.backend_llm is None:
            self.log("[REACT] No backend LLM available, falling back to algorithmic mode")
            super().step()
            return

        # If no human message received yet, don't generate anything
        # Wait for human to announce first
        print(f"[{self.name}][REACT] Checking message conditions:")
        print(f"  _received_human_message_this_turn: {self._received_human_message_this_turn}")
        print(f"  received_messages count: {len(self.received_messages)}")
        print(f"  any(received_messages): {any(self.received_messages)}")

        if not self._received_human_message_this_turn and not any(self.received_messages):
            self.log("[REACT] No messages received yet, waiting for human announcement")
            print(f"[{self.name}][REACT] Waiting - no messages yet")
            return

        # Early satisfaction check: If already satisfied and no new human message, don't renegotiate
        if self.satisfied and not self._received_human_message_this_turn:
            self.log("[REACT] Already satisfied, no new message - skipping step")
            return

        # If satisfied, check if current config still works before re-negotiating
        if self.satisfied:
            # Human sent new message - re-check if we're still satisfied
            current_penalty, _ = self.api.get_current_penalty()
            if current_penalty < 1e-6:
                self.log("[REACT] Still satisfied (penalty=0) - sending acknowledgment")
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
                self._send_backend_decision(ack_message)
                self._received_human_message_this_turn = False
                return
            else:
                # No longer satisfied - continue with normal processing
                self.satisfied = False
                self.log(f"[REACT] No longer satisfied (penalty={current_penalty}) - re-negotiating")

        print(f"[{self.name}][REACT] Proceeding with LLM generation...")

        try:
            # Build context
            context = self._build_context()
            prompt = f"{self.react_prompt}\n\n{context}"

            # Add human message if received
            if self._received_human_message_this_turn:
                human_msg = self._format_human_message()
                prompt += f"\n\n**Human message**: {human_msg}\n\nPlease respond to this message."
                self._received_human_message_this_turn = False

            # ReAct loop
            trajectory = []
            backend_output = None

            for iteration in range(self.max_react_iterations):
                self.log(f"[REACT] Iteration {iteration + 1}/{self.max_react_iterations}")

                # LLM generates thought + action
                messages = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "\n".join(trajectory) if trajectory else "Begin reasoning."}
                ]

                response = self.backend_llm.chat.completions.create(
                    model=self.backend_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                    stop=["Observation:"]
                )

                thought_action = response.choices[0].message.content
                trajectory.append(thought_action)

                self.log(f"[REACT] Thought+Action: {thought_action[:200]}...")

                # Check for final answer
                if "Final Answer:" in thought_action:
                    backend_output = self._parse_final_answer(thought_action)
                    self.log(f"[REACT] Final answer reached: {backend_output}")
                    break

                # Parse and execute action
                observation = self._execute_action_from_text(thought_action)

                # Add observation to trajectory
                trajectory.append(f"Observation: {json.dumps(observation, default=str)}")

                # Log ReAct step
                self._log_react_step(iteration, thought_action, observation)

            # If no final answer after max iterations, use last state
            if backend_output is None:
                self.log("[REACT] Max iterations reached without Final Answer")
                backend_output = {
                    "should_send_message": True,
                    "recipient": "Human",
                    "message_type": "info",
                    "structured_content": {
                        "my_assignments": self.assignments,
                        "reason": "Still analyzing the situation..."
                    }
                }

            # Log backend decision
            self._log_backend_decision(backend_output)

            # SAFETY NET: Force should_send_message=true for acceptance/proposal/rejection messages
            # LLMs sometimes incorrectly set should_send_message=false even when they have something to say
            message_type = backend_output.get("message_type", "")
            if message_type in ["acceptance", "proposal", "rejection"] and not backend_output.get("should_send_message"):
                self.log(f"[REACT] SAFETY NET: Forcing should_send_message=true for message_type={message_type}")
                backend_output["should_send_message"] = True

            # Update satisfaction based on message type
            if message_type == "acceptance":
                self.satisfied = True
                self.log("[REACT] Satisfied: sent acceptance message")
            elif message_type in ["proposal", "rejection"]:
                # Check penalty to update satisfaction
                current_penalty, _ = self.api.get_current_penalty()
                if current_penalty < 1e-6:
                    self.satisfied = True
                    self.log("[REACT] Satisfied: penalty=0")
                else:
                    self.satisfied = False
                    self.log(f"[REACT] Not satisfied: penalty={current_penalty}")

            # Validate message specificity before sending
            if backend_output.get("should_send_message"):
                structured_content = backend_output.get("structured_content", {})
                is_valid, error_msg = self._validate_message_specificity(structured_content)

                if not is_valid:
                    self.log(f"[REACT] [VALIDATION FAILED] {error_msg}")
                    self.log(f"[REACT] [VALIDATION FAILED] Invalid message content: {structured_content}")
                    self.log(f"[REACT] [VALIDATION FAILED] Message BLOCKED - not sending to prevent errors")
                    # Do NOT send invalid messages - they violate observability rules or are too vague
                    # This prevents partial observability violations and vague/useless messages
                else:
                    # Message passed validation - send it
                    self._send_backend_decision(backend_output)

        except Exception as e:
            self.log(f"[REACT] Error in ReAct reasoning: {e}")
            import traceback
            self.log(traceback.format_exc())
            # Fall back to algorithmic mode
            super().step()

    def _execute_action(self, action_name: str, action_args: str) -> Any:
        """Execute action given parsed name and arguments.

        Parameters
        ----------
        action_name : str
            Name of the action/function
        action_args : str
            Argument string (e.g., 'node="a2"' or '{"a2": "green"}')

        Returns
        -------
        Any
            Observation result
        """
        # Parse arguments
        try:
            # Handle different argument formats
            if not action_args.strip():
                args_dict = {}
            elif action_args.strip().startswith('{'):
                # JSON object argument
                args_dict = json.loads(action_args)
            elif '=' in action_args:
                # Keyword arguments: key=value, key2=value2
                args_dict = {}
                for pair in action_args.split(','):
                    if '=' in pair:
                        key, val = pair.split('=', 1)
                        key = key.strip()
                        val = val.strip().strip('"\'')

                        # Parse value
                        try:
                            # Try JSON parse for arrays/objects
                            if val.startswith('[') or val.startswith('{'):
                                args_dict[key] = json.loads(val)
                            else:
                                args_dict[key] = val
                        except:
                            args_dict[key] = val
            else:
                # Single positional argument
                args_dict = {"value": action_args.strip().strip('"')}

        except Exception as e:
            return {"error": f"Failed to parse arguments: {str(e)}"}

        # POST-PROCESS: Complete any incomplete neighbor_nodes for simulate_neighbor_change
        # CRITICAL: LLM might generate neighbor_nodes={"h2": "red", "h5": "blue"} without other neighbors
        if action_name == "simulate_neighbor_change" and "neighbor_nodes" in args_dict:
            neighbor_nodes = args_dict["neighbor_nodes"]
            known_neighbors = set(self.neighbour_assignments.keys())
            provided_neighbors = set(neighbor_nodes.keys())
            missing_neighbors = known_neighbors - provided_neighbors

            if missing_neighbors:
                self.log(f"[REACT] WARNING: LLM generated incomplete neighbor config in Action!")
                self.log(f"  Provided: {sorted(provided_neighbors)}")
                self.log(f"  Missing: {sorted(missing_neighbors)}")
                self.log(f"  Auto-completing with current values...")

                # Fill in missing neighbors with current values
                complete_config = dict(self.neighbour_assignments)
                complete_config.update(neighbor_nodes)  # Override with LLM's intended changes
                args_dict["neighbor_nodes"] = complete_config

                self.log(f"  Completed: {sorted(complete_config.keys())}")

        # Execute action via API
        if hasattr(self.api, action_name):
            func = getattr(self.api, action_name)
            try:
                result = func(**args_dict)
                return result
            except Exception as e:
                return {"error": f"Error executing {action_name}: {str(e)}"}
        else:
            return {"error": f"Unknown action: {action_name}"}

    def _execute_action_from_text(self, text: str) -> Any:
        """Parse and execute action from ReAct text.

        Parameters
        ----------
        text : str
            Text containing "Action: function_name(args)"

        Returns
        -------
        Any
            Observation result
        """
        # Parse action line
        action_match = re.search(r"Action:\s*(\w+)\((.*?)\)", text, re.IGNORECASE)

        if not action_match:
            return {"error": "No valid action found in text"}

        action_name = action_match.group(1)
        action_args_str = action_match.group(2)

        self.log(f"[REACT] Parsed action: {action_name}({action_args_str})")

        # Parse arguments
        try:
            # Handle different argument formats
            if not action_args_str.strip():
                args_dict = {}
            elif action_args_str.strip().startswith('{'):
                # JSON object argument
                args_dict = json.loads(action_args_str)
            elif '=' in action_args_str:
                # Keyword arguments: key=value, key2=value2
                args_dict = {}
                for pair in action_args_str.split(','):
                    if '=' in pair:
                        key, val = pair.split('=', 1)
                        key = key.strip()
                        val = val.strip().strip('"\'')

                        # Parse value
                        try:
                            # Try JSON parse for arrays/objects
                            if val.startswith('[') or val.startswith('{'):
                                args_dict[key] = json.loads(val)
                            else:
                                args_dict[key] = val
                        except:
                            args_dict[key] = val
            else:
                # Single positional argument
                args_dict = {"value": action_args_str.strip().strip('"')}

        except Exception as e:
            self.log(f"[REACT] Failed to parse arguments: {e}")
            return {"error": f"Failed to parse arguments: {str(e)}"}

        # Execute action via API
        if hasattr(self.api, action_name):
            func = getattr(self.api, action_name)
            try:
                result = func(**args_dict)
                return result
            except Exception as e:
                error_msg = f"Error executing {action_name}: {str(e)}"
                self.log(f"[REACT] {error_msg}")
                return {"error": error_msg}
        else:
            error_msg = f"Unknown action: {action_name}"
            self.log(f"[REACT] {error_msg}")
            return {"error": error_msg}

    def _parse_final_answer(self, text: str) -> Dict[str, Any]:
        """Parse Final Answer from ReAct text.

        Parameters
        ----------
        text : str
            Text containing "Final Answer: {...}"

        Returns
        -------
        Dict[str, Any]
            Parsed decision
        """
        # Extract JSON after "Final Answer:"
        match = re.search(r"Final Answer:\s*(\{.*\})", text, re.DOTALL | re.IGNORECASE)

        if match:
            try:
                decision = json.loads(match.group(1))
                return decision
            except json.JSONDecodeError as e:
                self.log(f"[REACT] Failed to parse Final Answer JSON: {e}")

        # Fallback: If we can't parse JSON, don't send a message
        # The LLM didn't follow instructions properly
        self.log(f"[REACT] WARNING: Could not parse Final Answer as JSON - not sending message")
        self.log(f"[REACT] Skipping this turn - LLM must return valid JSON")

        return {
            "should_send_message": False,  # Don't send unparseable responses
            "recipient": "Human",
            "message_type": "info",
            "structured_content": {
                "my_assignments": self.assignments,
                "reason": "",
                "requested_changes": {}
            }
        }

    def _extract_requests_from_text(self, text: str) -> Dict[str, str]:
        """Extract node-color requests from free text.

        Looks for patterns like "h4 to blue", "change h1 from red to green", "h4=blue".

        Parameters
        ----------
        text : str
            Free text to parse

        Returns
        -------
        Dict[str, str]
            Dictionary mapping node names to colors
        """
        import re
        requests = {}

        # Pattern 1: "h4 to blue" or "h4 to color blue"
        for match in re.finditer(r'\b([a-z]\d+)\s+to\s+(?:color\s+)?(\w+)', text, re.IGNORECASE):
            node, color = match.groups()
            if color.lower() in self.domain:
                requests[node] = color.lower()

        # Pattern 2: "change h4 from red to blue" or "h4 from red to blue"
        for match in re.finditer(r'\b([a-z]\d+)\s+from\s+\w+\s+to\s+(\w+)', text, re.IGNORECASE):
            node, color = match.groups()
            if color.lower() in self.domain:
                requests[node] = color.lower()

        # Pattern 3: "h4=blue" or "h4 = blue"
        for match in re.finditer(r'\b([a-z]\d+)\s*=\s*(\w+)', text, re.IGNORECASE):
            node, color = match.groups()
            if color.lower() in self.domain:
                requests[node] = color.lower()

        return requests

    def _validate_message_specificity(self, content: Dict[str, Any]) -> tuple:
        """Validate that message is specific, not vague.

        Parameters
        ----------
        content : Dict[str, Any]
            Message content with 'reason' and 'requested_changes' fields

        Returns
        -------
        tuple
            (is_valid: bool, error_message: str)
        """
        reason = content.get("reason", "")
        requested = content.get("requested_changes", {})
        message_type = content.get("message_type", "info")

        # CRITICAL: Check for partial observability violations FIRST
        # Compute visible neighbor nodes (only those with edges to our cluster)
        visible_neighbor_nodes = set()
        for node in self.nodes:
            for neighbor in self.problem.get_neighbors(node):
                if neighbor not in self.nodes:
                    visible_neighbor_nodes.add(neighbor)

        # Check if message mentions invisible nodes
        all_neighbor_nodes = set(self.neighbour_assignments.keys())
        invisible_nodes = all_neighbor_nodes - visible_neighbor_nodes

        for invisible_node in invisible_nodes:
            # Check both reason and requested_changes
            if invisible_node in reason or invisible_node in requested:
                return False, f"PARTIAL OBSERVABILITY VIOLATION: Message mentions '{invisible_node}' which is NOT visible (no edges to your cluster). Visible nodes: {sorted(visible_neighbor_nodes)}"

        # Check requested_changes only mentions visible nodes
        if requested:
            for node in requested.keys():
                if node in self.nodes:
                    return False, f"OWNERSHIP VIOLATION: requested_changes contains YOUR node '{node}' (should only request NEIGHBOR nodes)"
                if node not in visible_neighbor_nodes:
                    return False, f"PARTIAL OBSERVABILITY VIOLATION: requested_changes mentions '{node}' which is NOT visible. Visible nodes: {sorted(visible_neighbor_nodes)}"

        # Check for vague phrases
        vague_phrases = [
            "make a change", "adjust colors", "modify", "reconsider",
            "let's", "we should", "might need", "consider changing",
            "a neighboring node", "some boundary nodes", "certain colors",
            "review this setup", "further reduce", "different color"
        ]

        for phrase in vague_phrases:
            if phrase.lower() in reason.lower():
                return False, f"VAGUE MESSAGE: Contains phrase '{phrase}' - must be specific with exact node names and colors"

        # REMOVED: Don't validate penalty/acceptance logic - trust the LLM + API
        # The LLM uses get_best_response_to() which returns the ACHIEVABLE penalty,
        # not the current penalty. If it says acceptance, trust it.

        # Only validate requests for proposals (not acceptance)
        if message_type == "proposal" and (not requested or len(requested) == 0):
            return False, f"EMPTY REQUEST: Proposals must have specific requested_changes with node-color pairs"

        # Check requested_changes has specific node names (not just empty dict)
        if requested:
            for node, color in requested.items():
                if not isinstance(node, str) or len(node) < 2:
                    return False, f"Invalid node name: {node}"
                if color not in self.domain:
                    return False, f"Invalid color: {color} (not in domain {self.domain})"

        # Check reason contains actual specifics (not just empty/generic)
        if message_type in ["proposal", "info"] and len(reason.strip()) < 10:
            return False, f"EMPTY REASON: Message reason is too short or empty"

        return True, ""

    def _send_backend_decision(self, decision: Dict[str, Any]) -> None:
        """Send message based on backend LLM decision.

        Parameters
        ----------
        decision : Dict[str, Any]
            Structured decision from backend LLM
        """
        recipient = decision.get("recipient", "Human")
        structured_content = decision.get("structured_content", {})

        # Apply internal node assignments, but NOT boundary node assignments
        # Boundary nodes require coordination with neighbors
        if "my_assignments" in structured_content:
            proposed = structured_content["my_assignments"]

            # Identify boundary nodes (nodes with edges to other clusters)
            boundary_nodes = set()
            for node in self.nodes:
                for neighbor in self.problem.get_neighbors(node):
                    if neighbor not in self.nodes:
                        boundary_nodes.add(node)
                        break

            # Only apply changes to internal nodes (non-boundary)
            for node, color in proposed.items():
                if node in self.nodes and node not in boundary_nodes:
                    self.assignments[node] = color
                    self.log(f"[REACT] Updated internal node {node} -> {color}")
                elif node in boundary_nodes:
                    self.log(f"[REACT] SKIPPED boundary node {node} (requires coordination)")
                else:
                    self.log(f"[REACT] SKIPPED non-owned node {node}")

        # CRITICAL: Update my_assignments to match current self.assignments before formatting
        # This ensures [report: ...] tag matches actual internal state (fixes UI inconsistency)
        structured_content["my_assignments"] = dict(self.assignments)
        decision["structured_content"] = structured_content

        # Format message via comm layer
        if hasattr(self.comm_layer, 'format_message'):
            # Pass the full decision object with message_type
            nl_message = self.comm_layer.format_message(
                sender=self.name,
                recipient=recipient,
                message_data=decision  # Pass full decision, not just structured_content
            )
        else:
            # Fallback: simple template
            nl_message = structured_content.get("reason", "I've updated my configuration.")

            # Add report tag for UI color updates
            import json
            report = {"assignments": self.assignments}
            nl_message += f" [report: {json.dumps(report)}]"

        # POST-PROCESS: Remove mentions of internal nodes (safety net)
        nl_message = self._filter_internal_node_mentions(nl_message)

        self.log(f"[REACT] Sending to {recipient}: {nl_message[:100]}...")
        self.send(recipient, nl_message)

    def _filter_internal_node_mentions(self, message: str) -> str:
        """Remove mentions of internal nodes from message (safety net).

        Parameters
        ----------
        message : str
            Original message

        Returns
        -------
        str
            Filtered message with internal node mentions removed
        """
        # Identify internal nodes
        boundary_nodes = set()
        for node in self.nodes:
            for neighbor in self.problem.get_neighbors(node):
                if neighbor not in self.nodes:
                    boundary_nodes.add(node)
                    break

        internal_nodes = [n for n in self.nodes if n not in boundary_nodes]

        # Remove sentences/phrases mentioning internal nodes
        import re
        filtered = message

        for internal_node in internal_nodes:
            # Remove patterns like "a1=red", "a1 is red", "a1 to red"
            filtered = re.sub(rf'\b{internal_node}\s*=\s*\w+', '', filtered)
            filtered = re.sub(rf'\b{internal_node}\s+(?:is|to|as)\s+\w+', '', filtered)
            # Remove node name if followed by color or punctuation
            filtered = re.sub(rf'\b{internal_node}\b(?=\s*[,.:;])', '', filtered)

        # Clean up extra spaces and commas
        filtered = re.sub(r'\s+', ' ', filtered)
        filtered = re.sub(r'\s*,\s*,', ',', filtered)
        filtered = re.sub(r',\s*\.', '.', filtered)

        return filtered.strip()

    def _format_human_message(self) -> str:
        """Format most recent human message for backend LLM."""
        return self._last_human_text if self._last_human_text else "No message"

    def _log_react_step(self, iteration: int, thought_action: str, observation: Any) -> None:
        """Log ReAct step to react_trace.jsonl for research traceability.

        Parameters
        ----------
        iteration : int
            Iteration number
        thought_action : str
            Thought + action text
        observation : Any
            Observation result
        """
        import time

        # Extract thought and action separately
        thought_match = re.search(r"Thought:\s*(.+?)(?:Action:|$)", thought_action, re.DOTALL | re.IGNORECASE)
        action_match = re.search(r"Action:\s*(.+)", thought_action, re.DOTALL | re.IGNORECASE)

        thought = thought_match.group(1).strip() if thought_match else ""
        action = action_match.group(1).strip() if action_match else ""

        log_entry = {
            "timestamp": time.time(),
            "agent": self.name,
            "iteration": iteration,
            "thought": thought,
            "action": action,
            "observation": observation
        }

        try:
            trace_file = getattr(self, '_react_trace_file', None)
            if trace_file:
                with open(trace_file, 'a') as f:
                    f.write(json.dumps(log_entry, default=str) + '\n')
        except Exception as e:
            self.log(f"[REACT] Failed to write trace: {e}")

    def _log_backend_decision(self, decision: Dict[str, Any]) -> None:
        """Log backend LLM decision to react_trace.jsonl."""
        import time
        log_entry = {
            "timestamp": time.time(),
            "agent": self.name,
            "event": "final_answer",
            "decision": decision
        }

        try:
            trace_file = getattr(self, '_react_trace_file', None)
            if trace_file:
                with open(trace_file, 'a') as f:
                    f.write(json.dumps(log_entry, default=str) + '\n')
        except Exception as e:
            self.log(f"[REACT] Failed to write trace: {e}")

    def receive(self, msg: Any) -> None:
        """Override receive to handle human messages and special tokens.

        Parameters
        ----------
        msg : Message
            Incoming message
        """
        # Handle special tokens
        if hasattr(msg, 'content') and msg.content == "__ANNOUNCE_CONFIG__":
            self.log(f"[REACT] Received __ANNOUNCE_CONFIG__ from {msg.sender}")
            self._handle_announce_config(msg.sender)
            return

        # Handle color update dicts (e.g., "{'h1': 'red', 'h4': 'blue'}")
        if hasattr(msg, 'content') and isinstance(msg.content, str):
            content_str = msg.content.strip()
            if content_str.startswith('{') and content_str.endswith('}'):
                try:
                    import ast
                    color_update = ast.literal_eval(content_str)
                    if isinstance(color_update, dict):
                        self.log(f"[REACT] Detected color update dict: {color_update}")
                        self.neighbour_assignments.update(color_update)
                        return  # Don't pass to parent, this was just a color notification
                except:
                    pass  # Not a valid dict, treat as normal message

        # Normal message handling
        super().receive(msg)
        self._received_human_message_this_turn = True

        # Store human message text
        if hasattr(msg, 'content'):
            if isinstance(msg.content, str):
                self._last_human_text = msg.content
            elif isinstance(msg.content, dict):
                self._last_human_text = msg.content.get('text', '')

    def _send_automatic_announcement(self) -> None:
        """Automatically send announcement to all neighbors on first step."""
        if self._config_announced:
            return

        self.log("[REACT] Sending automatic announcement to all neighbors")
        self._config_announced = True
        self._phase = "bargain"

        # CRITICAL FIX: Recompute assignments BEFORE announcing!
        # Initial assignments are random and may conflict with neighbor colors.
        # We must compute assignments that respect known neighbor constraints.
        if self.neighbour_assignments:
            self.log(f"[REACT] Recomputing assignments to respect neighbor constraints: {self.neighbour_assignments}")
            self.assignments = self.compute_assignments()
            self.log(f"[REACT] Recomputed assignments: {self.assignments}")
        else:
            self.log("[REACT] WARNING: No neighbor assignments known yet - announcing with initial (possibly random) assignments")

        # Get boundary nodes
        boundary = [n for n in self.nodes
                   if any((n, ext) in self.problem.edges or (ext, n) in self.problem.edges
                         for ext in self.neighbour_assignments.keys())]

        if not boundary:
            self.log("[REACT] No boundary nodes to announce")
            return

        # Build boundary assignments
        report = {n: self.assignments.get(n) for n in boundary if self.assignments.get(n)}
        self.log(f"[REACT] Announcing boundary: {report}")

        # Send to all neighbors
        for recipient in self.neighbour_assignments.keys():
            announcement = {
                "type": "announcement",
                "data": {"assignments": report},
                "report": report
            }
            self.send(recipient, announcement)
            self.log(f"[REACT] Announced config to {recipient}: {report}")

        # Don't set any flags - just wait for human to announce
        # The normal step() logic will handle responses when messages arrive

    def _handle_announce_config(self, recipient: str) -> None:
        """Handle announcement phase and generate first substantive message."""
        if self._config_announced:
            return

        self._config_announced = True
        self._phase = "bargain"

        # CRITICAL FIX: Recompute assignments considering human's announced colors!
        # At this point, _sync_neighbour_views() has already populated neighbour_assignments
        # with the human's colors. We MUST recompute to avoid conflicts.
        if self.neighbour_assignments:
            self.log(f"[REACT] Recomputing assignments to respect human's announced colors: {self.neighbour_assignments}")
            self.assignments = self.compute_assignments()
            self.log(f"[REACT] Recomputed assignments: {self.assignments}")
        else:
            self.log(f"[REACT] WARNING: No neighbor assignments available - using initial assignments")

        # Send announcement
        boundary = [n for n in self.nodes
                   if any((n, ext) in self.problem.edges or (ext, n) in self.problem.edges
                         for ext in self.neighbour_assignments.keys())]

        if boundary:
            # Build boundary assignments
            report = {n: self.assignments.get(n) for n in boundary if self.assignments.get(n)}

            # Send announcement as STRUCTURED MESSAGE (not plain string)
            # This ensures the communication layer preserves the report field
            announcement = {
                "type": "announcement",
                "data": {"assignments": report},
                "report": report  # UI will extract this from [report: ...] suffix
            }

            self.send(recipient, announcement)
            self.log(f"[REACT] Announced config to {recipient}: {report}")

        # Don't set any flags - agent will respond when it receives human messages
        self.log(f"[REACT] Announcement complete, waiting for human messages")

    def _generate_first_message_after_announcement(self, recipient: str) -> None:
        """Generate first substantive message after config announcement using ReAct.

        This checks for conflicts and uses backend LLM with ReAct reasoning
        to generate a meaningful first message.
        """
        print(f"[{self.name}][REACT] >>> _generate_first_message_after_announcement ENTERED for {recipient}")

        if self.backend_llm is None:
            print(f"[{self.name}][REACT] No backend LLM, returning")
            self.log("[REACT] No backend LLM, skipping first message generation")
            return

        print(f"[{self.name}][REACT] Backend LLM available, proceeding...")
        try:
            # Check current state
            penalty, conflicts = self.api.get_current_penalty()
            print(f"[{self.name}][REACT] Penalty={penalty}, conflicts={len(conflicts)}")

            # Build ReAct prompt for first message
            context = self._build_context()

            prompt = f"""{self.react_prompt}

{context}

**Situation**: You have just announced your initial configuration to {recipient}.

**Current state**:
- Your penalty: {penalty}
- Conflicts: {len(conflicts)} conflicts detected
- Conflict details: {conflicts if conflicts else "None"}

**Task**: Based on the current state, use the ReAct pattern to analyze the situation and generate an appropriate first message:
1. If there are conflicts (penalty > 0): Suggest changes (either to your nodes or request changes from {recipient})
2. If penalty == 0: Express satisfaction with current configuration

**IMPORTANT**: When you reach your final answer, respond with a JSON object in this format:
Final Answer: {{
  "should_send_message": true,
  "recipient": "{recipient}",
  "message_type": "proposal" | "question" | "acceptance" | "info",
  "structured_content": {{
    "my_assignments": {{"node": "color", ...}},
    "reason": "Your explanation",
    "dependencies": {{"neighbor_node": "color", ...}}  // optional
  }}
}}

Begin reasoning now. Be proactive and constructive."""

            self.log(f"[REACT] Generating first message after announcement (penalty={penalty})")

            # ReAct loop
            trajectory = []
            backend_output = None

            for iteration in range(self.max_react_iterations):
                print(f"[{self.name}][REACT] ReAct iteration {iteration + 1}/{self.max_react_iterations}")
                # LLM generates thought + action
                messages = [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "\n".join(trajectory) if trajectory else "Begin reasoning."}
                ]

                print(f"[{self.name}][REACT] Calling backend LLM...")
                response = self.backend_llm.chat.completions.create(
                    model=self.backend_model,
                    messages=messages,
                    stop=["Observation:"],
                    temperature=0.7,
                    max_tokens=1500
                )

                thought_action = response.choices[0].message.content
                print(f"[{self.name}][REACT] LLM response: {thought_action[:150]}...")
                trajectory.append(thought_action)

                # Check for final answer
                if "Final Answer:" in thought_action:
                    backend_output = self._parse_final_answer(thought_action)
                    print(f"[{self.name}][REACT] Got final answer: {backend_output}")
                    self.log(f"[REACT] Got final answer after {iteration + 1} iterations")
                    break

                # Parse and execute action
                action_match = re.search(r"Action:\s*(\w+)\((.*?)\)", thought_action, re.DOTALL)
                if action_match:
                    action_name = action_match.group(1)
                    action_args = action_match.group(2).strip()
                    print(f"[{self.name}][REACT] Executing action: {action_name}({action_args[:50]}...)")

                    # Execute action via API
                    observation = self._execute_action(action_name, action_args)
                    print(f"[{self.name}][REACT] Observation: {str(observation)[:100]}...")

                    trajectory.append(f"Observation: {json.dumps(observation, default=str)}")

                    # Log ReAct step
                    self._log_react_step(iteration, thought_action, action_name, observation)
                else:
                    print(f"[{self.name}][REACT] No action found in response, continuing...")

            # Check if loop completed without final answer
            if backend_output is None:
                print(f"[{self.name}][REACT] WARNING: ReAct loop completed without final answer (max iterations reached?)")
                self.log(f"[REACT] WARNING: No final answer after {self.max_react_iterations} iterations")

            # Send message if backend decided to
            print(f"[{self.name}][REACT] Checking backend_output: {backend_output}")
            if backend_output and backend_output.get("should_send_message"):
                print(f"[{self.name}][REACT] Backend says send message, calling _send_backend_decision()")
                self._send_backend_decision(backend_output)
                print(f"[{self.name}][REACT] sent_messages count now: {len(self.sent_messages)}")
                self.log(f"[REACT] Sent first message after announcement")
            else:
                print(f"[{self.name}][REACT] Backend decided NOT to send message (or backend_output is None)")
                self.log(f"[REACT] Backend decided not to send message (penalty={penalty})")

        except Exception as e:
            print(f"[{self.name}][REACT] EXCEPTION: {e}")
            self.log(f"[REACT] Error generating first message: {e}")
            import traceback
            traceback_str = traceback.format_exc()
            print(f"[{self.name}][REACT] Traceback: {traceback_str}")
            self.log(traceback_str)
