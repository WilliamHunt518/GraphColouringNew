# Communication Modes - Quick Comparison

## All Modes Overview

| Mode | Agent Reasoning | Communication | Use Case |
|------|-----------------|---------------|----------|
| **RB** | Algorithmic (greedy/maxsum) | Structured templates | Baseline, maximum explainability |
| **LLM_RB** | Algorithmic (greedy/maxsum) | NL ↔ RB grammar | Natural interface, structured backend |
| **LLM_API** | Algorithmic (greedy/maxsum) | Constraint-oriented NL | Natural constraints discussion |
| **LLM_TOOL** | **LLM-based** | Multi-layer (Speech + Backend) | Emergent strategies, function calling |
| **LLM_REACT** | **LLM-based** | Multi-layer (Speech + Backend) | Transparent reasoning, ReAct pattern |

## Detailed Comparison Matrix

### Architecture

| Aspect | RB | LLM_RB | LLM_API | LLM_TOOL | LLM_REACT |
|--------|----|---------|---------| ---------|-----------|
| Solver | Greedy/MaxSum | Greedy/MaxSum | Greedy/MaxSum | **LLM + API** | **LLM + API** |
| Comm Layer | Templates | LLM Translation | LLM Formatting | Speech LLM | Speech LLM |
| Backend LLM | None | None | None | **GPT-4** | **GPT-4** |
| Reasoning Trace | None | None | None | Tool calls | **Thought/Action/Obs** |

### Message Examples

#### RB Mode
```
I propose the following configuration:
- a2 = green
- a5 = blue

This is conditional on:
- Your h1 = red
- Your h2 = blue
```

#### LLM_RB Mode
```
If you set h1 to red and h2 to blue, then I can do a2=green and a5=blue.
How does that sound?
```
*(Internally translated to RB grammar)*

#### LLM_API Mode
```
I need h1≠green and h2≠green to avoid conflicts with my cluster.
Can you accommodate that?
```

#### LLM_TOOL Mode
```
I propose a2=green. I analyzed the current conflicts and found that changing
a2 from blue to green resolves the conflict with h2 while maintaining
feasibility. [report: {"a2": "green"}]
```
*(Backend used: get_current_penalty() → get_available_colors() → test_configuration())*

#### LLM_REACT Mode
```
I propose a1=yellow, a2=green. After checking conflicts and testing
alternatives, this configuration achieves penalty=0.
[report: {"a1": "yellow", "a2": "green"}]
```
*(Reasoning trace: Thought→Action→Observation→... visible in logs)*

### Performance Characteristics

| Metric | RB | LLM_RB | LLM_API | LLM_TOOL | LLM_REACT |
|--------|----|---------|---------| ---------|-----------|
| **Speed** | Fast (~50ms) | Medium (~2s) | Medium (~2s) | Slow (~10s) | Slower (~15s) |
| **Cost per msg** | Free | $0.02 | $0.02 | $0.10 | $0.12 |
| **Tokens per msg** | 0 | ~800 | ~800 | ~3000 | ~4000 |
| **Determinism** | Full | High | High | Low | Low |
| **Explainability** | Highest | High | Medium | Medium | **Highest** |

### Capabilities Comparison

| Capability | RB | LLM_RB | LLM_API | LLM_TOOL | LLM_REACT |
|------------|----|---------|---------| ---------|-----------|
| Conditional offers | ✅ | ✅ | ✅ | ✅ | ✅ |
| Constraint propagation | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| Natural language | ❌ | ✅ | ✅ | ✅ | ✅ |
| Emergent strategies | ❌ | ❌ | ❌ | ✅ | ✅ |
| Transparent reasoning | ⚠️ | ⚠️ | ❌ | ⚠️ | ✅ |
| Self-correction | ❌ | ❌ | ❌ | ⚠️ | ✅ |

Legend: ✅ Full support | ⚠️ Partial support | ❌ Not supported

### Use Cases by Research Question

**RQ1: Does natural language improve coordination?**
- Compare: **RB** vs **LLM_RB** vs **LLM_API**
- Hypothesis: Natural language reduces cognitive load

**RQ2: Do LLM-based agents discover novel strategies?**
- Compare: **LLM_API** vs **LLM_TOOL** vs **LLM_REACT**
- Hypothesis: LLM reasoning finds non-obvious solutions

**RQ3: Does transparent reasoning affect trust?**
- Compare: **LLM_TOOL** vs **LLM_REACT**
- Hypothesis: Visible reasoning traces increase human trust

**RQ4: What's the cost-benefit tradeoff?**
- Compare: All modes on time/cost/outcome metrics
- Hypothesis: LLM modes justify cost via better outcomes

### Implementation Complexity

| Mode | Lines of Code | Dependencies | Setup Difficulty |
|------|---------------|--------------|------------------|
| RB | ~1500 | None | Easy |
| LLM_RB | ~2200 | OpenAI API | Medium |
| LLM_API | ~1800 | OpenAI API | Medium |
| LLM_TOOL | ~3500 | OpenAI API | Hard |
| LLM_REACT | ~3800 | OpenAI API | Hard |

### Failure Modes

**RB**:
- ❌ Unnatural for humans (steep learning curve)
- ❌ Rigid (can't express novel ideas)

**LLM_RB**:
- ❌ Translation errors (LLM misinterprets intent)
- ❌ Incomplete RB grammar (some NL concepts unmappable)

**LLM_API**:
- ❌ Ambiguity (constraint semantics unclear)
- ❌ Hallucination (LLM invents constraints)

**LLM_TOOL**:
- ❌ Invalid tool calls (wrong arguments)
- ❌ Tool call loops (infinite exploration)
- ❌ Non-determinism (varies between runs)

**LLM_REACT**:
- ❌ All LLM_TOOL failure modes +
- ❌ Format violations (LLM forgets Thought/Action structure)
- ❌ Reasoning loops (circular reasoning)
- ❌ Context overflow (long trajectories hit limits)

## Recommendations

### For Production Use
**Use RB or LLM_RB**: Fast, reliable, explainable

### For Research on NL Communication
**Use LLM_RB or LLM_API**: Structured vs free-form NL comparison

### For Research on LLM Reasoning
**Use LLM_TOOL and LLM_REACT**: Function calling vs explicit reasoning

### For Maximum Interpretability
**Use LLM_REACT**: Full reasoning traces available

### For Cost-Conscious Studies
**Use RB or LLM_RB**: Minimal API costs

## Quick Decision Tree

```
Do you need LLM-based reasoning (not just formatting)?
├─ No: Do you need natural language?
│  ├─ No: Use RB (baseline, fastest, explainable)
│  └─ Yes: Use LLM_RB (natural + structured)
└─ Yes: Do you need transparent reasoning traces?
   ├─ No: Use LLM_TOOL (faster, function calling)
   └─ Yes: Use LLM_REACT (slower, full traces)
```

## See Also

- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md): Complete system architecture
- [MODE_LLM_TOOL.md](MODE_LLM_TOOL.md): Function calling details
- [MODE_LLM_REACT.md](MODE_LLM_REACT.md): ReAct pattern details
- [LLM_RB_ARCHITECTURE.md](LLM_RB_ARCHITECTURE.md): LLM_RB implementation
