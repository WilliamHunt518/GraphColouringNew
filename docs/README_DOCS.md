# Documentation Index

This directory contains comprehensive documentation for the Graph Coloring Negotiation System.

## Getting Started

1. **[SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md)** - START HERE
   - Complete system architecture
   - Problem definition
   - Core components
   - Data flow
   - Two-phase workflow

## Communication Modes

### Quick Reference
- **[MODES_COMPARISON.md](MODES_COMPARISON.md)** - Side-by-side comparison of all modes

### Detailed Mode Documentation

#### Algorithmic Modes (LLM for Communication Only)
- **[MODE_RB.md](MODE_RB.md)** *(if exists)* - Pure rule-based argumentation
- **[LLM_RB_ARCHITECTURE.md](LLM_RB_ARCHITECTURE.md)** - Natural language ↔ RB grammar translation
- **[MODE_LLM_API.md](MODE_LLM_API.md)** *(if exists)* - Constraint-oriented natural language

#### LLM-Based Reasoning Modes
- **[MODE_LLM_TOOL.md](MODE_LLM_TOOL.md)** - Function calling architecture
  - Backend LLM uses tool calling
  - OpenAI-style function definitions
  - API library with 11 functions
  - ~10s per turn

- **[MODE_LLM_REACT.md](MODE_LLM_REACT.md)** - ReAct reasoning pattern
  - Explicit Thought→Action→Observation loops
  - Based on Yao et al. (2022) ReAct framework
  - Full reasoning traces
  - ~15s per turn

## Implementation Guides

### Core Architecture
- **[MULTI_LAYER_LLM_ARCHITECTURE.md](MULTI_LAYER_LLM_ARCHITECTURE.md)** - Three-layer LLM design
- **[MULTI_LAYER_LLM_IMPLEMENTATION.md](MULTI_LAYER_LLM_IMPLEMENTATION.md)** - Implementation details

### Quick Starts
- **[QUICK_START_LLM_MODES.md](QUICK_START_LLM_MODES.md)** - Running LLM modes
- **[MULTI_LAYER_LLM_QUICKSTART.md](MULTI_LAYER_LLM_QUICKSTART.md)** - Quick start for multi-layer modes

### Developer Resources
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)** - Where to modify code
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Legacy architecture notes
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions

## Feature Documentation

### Specific Features
- **[LLM_RB_TRANSLATION_IMPROVEMENTS.md](LLM_RB_TRANSLATION_IMPROVEMENTS.md)** - NL → RB translation enhancements
- **[LLM_RB_RENDERING_ENHANCEMENTS.md](LLM_RB_RENDERING_ENHANCEMENTS.md)** - RB → NL rendering with LLM
- **[LLM_RB_RICH_OFFERS.md](LLM_RB_RICH_OFFERS.md)** - Conditional offer generation
- **[IMPOSSIBLE_CONDITIONS_USER_GUIDE.md](IMPOSSIBLE_CONDITIONS_USER_GUIDE.md)** - Constraint system guide
- **[README_IMPOSSIBLE_CONDITIONS.md](README_IMPOSSIBLE_CONDITIONS.md)** - Infeasibility constraints

### Bug Fixes & Improvements
- **[FIX_ANNOUNCEMENT_THEN_FIRST_MESSAGE.md](FIX_ANNOUNCEMENT_THEN_FIRST_MESSAGE.md)** - Announcement flow fixes
- **[FIX_FIRST_MESSAGE_AFTER_ANNOUNCEMENT.md](FIX_FIRST_MESSAGE_AFTER_ANNOUNCEMENT.md)** - First message generation
- **[LLM_API_ANNOUNCEMENT_FIX.md](LLM_API_ANNOUNCEMENT_FIX.md)** - LLM_API announcement stage

## Process Documentation

### Agent Decision Making
- **[AGENT_DECISION_PROCESS.md](AGENT_DECISION_PROCESS.md)** - How agents make decisions
- **[AGENT_FLOW_DIAGRAM.md](AGENT_FLOW_DIAGRAM.md)** - Visual flow diagrams

### Other Resources
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Quick reference card

## Session Notes & Paper Drafts

- **[session-notes/](session-notes/)** - Development session notes
- **[PaperDraft/](PaperDraft/)** - Research paper drafts
- **[fixes/](fixes/)** - Detailed fix documentation

## Recommended Reading Order

### For New Users
1. [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) - Understand the system
2. [MODES_COMPARISON.md](MODES_COMPARISON.md) - Choose a mode
3. [QUICK_START_LLM_MODES.md](QUICK_START_LLM_MODES.md) - Run experiments

### For Researchers
1. [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) - System design
2. [MODE_LLM_TOOL.md](MODE_LLM_TOOL.md) - Function calling architecture
3. [MODE_LLM_REACT.md](MODE_LLM_REACT.md) - ReAct reasoning pattern
4. [MODES_COMPARISON.md](MODES_COMPARISON.md) - Performance comparison
5. [AGENT_DECISION_PROCESS.md](AGENT_DECISION_PROCESS.md) - Decision logic

### For Developers
1. [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) - Overall architecture
2. [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Where to modify
3. [MULTI_LAYER_LLM_IMPLEMENTATION.md](MULTI_LAYER_LLM_IMPLEMENTATION.md) - Implementation details
4. [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues

## Key Concepts

### Partial Observability
Each agent sees:
- ✅ Their own cluster fully (nodes + internal edges)
- ✅ Boundary neighbor nodes
- ❌ Internal structure of other clusters
- ❌ Non-boundary nodes in other clusters

### Two-Phase Workflow
1. **Configure Phase**: Agents compute initial assignments, wait for announcement
2. **Bargain Phase**: Announcement → first message → negotiation → consensus

### Communication Modes
- **Algorithmic**: Agent uses greedy/maxsum solver, LLM formats messages
- **LLM-Based**: Agent uses LLM for reasoning, LLM calls API functions

### Logging & Observability
- `communication_log.txt`: All messages
- `Agent1_log.txt`, etc.: Per-agent traces
- `llm_trace.jsonl`: LLM API calls (LLM modes only)
- `react_trace.jsonl`: ReAct reasoning traces (LLM_REACT only)

## File Format Conventions

### Markdown Files
- `.md` files use GitHub-flavored markdown
- Code blocks specify language for syntax highlighting
- Pseudocode uses Python-like syntax

### Log Files
- `.txt` for human-readable logs
- `.jsonl` for structured logs (one JSON object per line)

## Citing This Work

If you use this system in your research, please cite:

```
@inproceedings{graphcoloring2026,
  title={Human-Agent Coordination via Structured Argumentation in Distributed Graph Coloring},
  author={[Authors]},
  booktitle={[Conference]},
  year={2026}
}
```

## Contributing

When adding new documentation:
1. Follow existing file naming: `MODE_*.md`, `FIX_*.md`, etc.
2. Include pseudocode for algorithms
3. Add entry to this README
4. Cross-reference related documents

## Contact

For questions or issues:
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Review [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)
- Open GitHub issue (if applicable)

## Version History

- **v2.0** (2026-02-11): Added LLM_TOOL and LLM_REACT modes with multi-layer architecture
- **v1.5** (2026-02-10): Enhanced LLM_RB with bidirectional LLM rendering
- **v1.4** (2026-02-09): Fixed LLM_RB translation for complex conditions
- **v1.3** (2026-01-28): Added impossible_combinations for conditional constraints
- **v1.0** (2025-01-14): Initial release with RB, LLM_RB, LLM_API modes

## License

[Add license information]
