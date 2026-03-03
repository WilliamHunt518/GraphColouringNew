
# Study Redesign Summary: Interactive Constraint Explanations for Human–Agent Graph Colouring

## 1. Overview

This document summarises the redesign of the original graph colouring human–agent coordination study.
The previous design focused on **dialogue-based interaction** between humans and AI agents using
rule-based negotiation and LLM-mediated communication.

The new design replaces negotiation with **interactive constraint visualisation**, where the human
directly manipulates the graph and the system continuously exposes the implications of those actions.

The core research question shifts from:

> How should humans and AI negotiate solutions?

to:

> How should AI systems **explain constraint structure** to human collaborators?

The new experiment studies how different representations of constraint information affect human
understanding, workload, and task performance.

---

# 2. Original Study Design (Summary)

The original experiment involved:

### Task
Distributed graph colouring with:

- 3 participants:
  - 1 human
  - 2 artificial agents
- Each participant controlled a cluster of nodes.
- Objective: avoid colour conflicts across edges.

### Interaction model
Human and agents negotiated through dialogue.

Four experimental conditions were studied:

1. **RB**
   - Structured conditional-offer negotiation protocol

2. **LLM-RB**
   - Natural language translated into RB dialogue moves

3. **LLM-TOOL**
   - LLM reasoning agent using backend tools

4. **LLM-REACT**
   - ReAct reasoning loop using tools

### System characteristics

- Agents computed best responses
- Human-agent negotiation occurred through message panels
- Interaction was sequential and conversational
- Communication protocols were the independent variable

### Measurements

- Convergence rate
- Negotiation turns
- Solution quality
- NASA-TLX workload
- Trust in agents

---

# 3. Motivation for Redesign

Several limitations motivated the redesign:

### 3.1 Cognitive overhead of dialogue
The dialogue system required participants to:

- interpret agent messages
- construct responses
- understand formal move types

This introduces complexity unrelated to the underlying optimisation problem.

### 3.2 Conflation of reasoning and communication
The previous study mixed multiple research questions:

- agent reasoning ability
- negotiation strategies
- LLM tool use
- human understanding

The redesign isolates **human understanding of constraints**.

### 3.3 Difficulty interpreting constraint structure
The core difficulty in distributed coordination is understanding:

- how one agent's decision constrains others
- which configurations remain possible

The new system focuses on making this structure visible.

---

# 4. New Study Concept

The redesigned experiment introduces **Interactive Constraint Visualisation**.

Instead of negotiating with agents, the human:

- directly manipulates node colours
- observes how the system responds

Agents no longer act as negotiating partners.
Instead they act as **constraint analyzers** that expose feasible responses.

The system continuously reveals:

- what agent configurations remain possible
- whether the current configuration is feasible
- what constraints the human decisions impose

---

# 5. New Interaction Model

## Graph Interface

The participant sees a graph interface with:

- human cluster nodes
- agent clusters
- coloured edges showing adjacency

Nodes start **grey (unassigned)**.

Available colours:

- Red
- Green
- Blue

Grey represents **an unspecified value**.

Users may cycle through colours for each node.

---

## Real-time Updates

Whenever a node colour changes:

1. The system recomputes feasible agent configurations.
2. Constraint panels update immediately.
3. The interface displays how the current configuration affects the rest of the graph.

There is **no turn structure** and **no messaging interface**.

---

# 6. Mathematical Model

The human configuration is a partial assignment:

α_h : V_h → C

where grey nodes are excluded.

For each agent cluster a:

S_a(α_h) = { x_a ∈ C^{|V_a|} | J_a(x_a, α_h) = 0 }

This represents the set of feasible assignments for the agent cluster
given the human's current choices.

The system computes this set exactly.

---

# 7. Constraint Projection

Because the full configuration space is difficult to interpret,
the interface presents projections of the feasible set.

Two complementary views are used.

---

## 7.1 Agent-Centric Constraints

Agent nodes display the colours they may still adopt.

For node u:

D_u(α_h) = { c ∈ C | ∃ x_a ∈ S_a(α_h) such that x_a(u) = c }

Example display:

Possible:
a5 = Green OR Red

Conditional:
a5 = Blue IF h4 ≠ Blue

This view shows the **remaining degrees of freedom** for agent nodes.

---

## 7.2 User-Centric Constraints

Constraints are expressed relative to the human's choices.

Example:

Because:
h4 = Blue

Means:
a5 = Red AND a4 = Green
OR
a5 = Green AND a4 = Red

This representation links the human's decisions directly to possible agent outcomes.

---

# 8. Global Feasibility Panel

A whole-graph panel shows the status of each agent cluster.

Possible states:

### Feasible
S_a(α_h) ≠ ∅

The agent cluster still has valid configurations.

### Infeasible
S_a(α_h) = ∅

The human configuration cannot produce a valid global colouring.

The system also proposes minimal changes that restore feasibility.

Example:

"This configuration cannot work.
Node h2 and h5 must change colour."

---

# 9. Experimental Conditions

Two design dimensions define the study:

### Perspective
How the constraint information is framed

- User-centric
- Agent-centric

### Representation
How the constraint information is expressed

- Formulaic logical statements
- Natural-language summaries

This produces four conditions.

---

## Condition 1: User-Centric Formulaic Constraints

Human nodes display logical expressions describing feasible agent responses.

Advantages:

- exact representation
- transparent constraint structure

Disadvantages:

- cognitively demanding
- difficult to interpret when many possibilities exist

---

## Condition 2: Agent-Centric Formulaic Constraints

Agent nodes display remaining feasible colours.

Advantages:

- highlights remaining flexibility
- simple domain representation

Disadvantages:

- does not directly explain consequences of human actions

---

## Condition 3: User-Centric LLM Summaries

Logical constraints are summarised using an LLM.

Example output:

Because:
h4 = Blue

Means:
Most configurations remain possible.
The neighbouring agent nodes are only weakly constrained.

The LLM **does not perform reasoning**.
It only summarises precomputed constraint information.

---

## Condition 4: Agent-Centric LLM Summaries

Agent node domains are described using natural language.

Example:

"a5 can be either red or green.
Blue would only be possible if h4 changed colour."

Again the LLM is used purely for explanation.

---

# 10. Experimental Task

Participants must colour the human nodes such that a valid global colouring exists.

They may:

- change colours freely
- leave nodes grey while exploring possibilities
- observe constraint explanations in real time

The task ends when a configuration exists for which all agent clusters have feasible assignments.

---

# 11. Measurements

## Objective

- Time to reach feasible configuration
- Number of node adjustments
- Frequency of infeasible states

## Subjective

- NASA-TLX workload
- Perceived clarity of explanations
- Trust in system guidance
- Preference between interface modes

---

# 12. Expected Outcomes

Hypotheses:

### H1
LLM summaries reduce cognitive workload compared to formulaic constraints.

### H2
Agent-centric views enable faster convergence by exposing remaining degrees of freedom.

### H3
User-centric views improve understanding of how human decisions affect the system.

---

# 13. Contributions of the New Study

1. A novel **interactive constraint explanation interface**
2. A controlled testbed for studying **human understanding of constraint systems**
3. A comparison between **symbolic and LLM-based explanation methods**
4. Insights into how AI systems should communicate **feasible solution spaces** to humans

