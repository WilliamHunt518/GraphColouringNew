"""Minimal Tkinter UI for a human-controlled cluster.

This UI is intended for the in-person PC study. It collects, once per
iteration:

* a colour choice for each human-controlled node
* an optional free-form message to neighbour clusters

It also displays the latest known neighbour assignments.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class HumanTurnResult:
    assignments: Dict[str, Any]
    message: str


class HumanTurnUI:
    """Blocking UI that returns the human's choices for the current iteration."""

    def __init__(self, title: str = "Human Turn") -> None:
        self.title = title

    def get_turn(
        self,
        *,
        nodes: List[str],
        domain: List[Any],
        current_assignments: Dict[str, Any],
        neighbour_assignments: Dict[str, Any],
        iteration: int,
        visible_graph: Tuple[List[str], List[Tuple[str, str]]] | None = None,
        owners: Dict[str, str] | None = None,
        messages: List[Tuple[str, Any]] | None = None,
        all_visible_assignments: Dict[str, Any] | None = None,
    ) -> HumanTurnResult:
        """Open a window, block until Submit is pressed, and return choices."""
        # Tkinter is part of the standard library on most Python installs.
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title(f"{self.title} — Iteration {iteration}")
        root.geometry("780x560")

        # --- header ---
        header = ttk.Label(
            root,
            text=f"Iteration {iteration}: choose colours for your nodes",
            font=("Arial", 12, "bold"),
        )
        header.pack(pady=8)

        # --- top: graph + messages ---
        top = ttk.Frame(root)
        top.pack(fill="both", expand=False, padx=10, pady=6)

        graph_frame = ttk.LabelFrame(top, text="Your observable graph")
        graph_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

        msg_frame = ttk.LabelFrame(top, text="Incoming messages")
        msg_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # Render graph figure (if provided)
        if visible_graph is not None:
            try:
                import io
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                import networkx as nx
                from PIL import Image, ImageTk

                vis_nodes, vis_edges = visible_graph
                G = nx.Graph()
                G.add_nodes_from(vis_nodes)
                G.add_edges_from(vis_edges)

                # Use a stable layout so nodes don't jump around too much.
                pos = nx.spring_layout(G, seed=42)

                # Node colours (fallback grey)
                assign_map = all_visible_assignments or {}
                def node_color(n: str) -> str:
                    c = str(assign_map.get(n, ""))
                    if c in {"red", "green", "blue", "orange", "yellow", "purple"}:
                        return c
                    return "lightgrey"

                colors = [node_color(n) for n in G.nodes()]
                labels = {}
                for n in G.nodes():
                    owner = owners.get(n, "") if owners else ""
                    labels[n] = f"{n}\n({owner})" if owner else n

                fig = plt.figure(figsize=(4.6, 3.6), dpi=110)
                ax = fig.add_subplot(111)
                ax.axis("off")
                nx.draw_networkx_edges(G, pos, ax=ax)
                nx.draw_networkx_nodes(G, pos, node_color=colors, ax=ax, node_size=700, edgecolors="black")
                nx.draw_networkx_labels(G, pos, labels=labels, font_size=8, ax=ax)

                buf = io.BytesIO()
                fig.tight_layout(pad=0.2)
                fig.savefig(buf, format="png")
                plt.close(fig)
                buf.seek(0)

                img = Image.open(buf)
                tk_img = ImageTk.PhotoImage(img)

                img_label = ttk.Label(graph_frame, image=tk_img)
                img_label.image = tk_img  # keep ref
                img_label.pack(padx=6, pady=6)
            except Exception as e:
                ttk.Label(graph_frame, text=f"(Could not render graph: {e})", wraplength=340).pack(anchor="w", padx=8, pady=6)
        else:
            ttk.Label(graph_frame, text="(No graph provided)").pack(anchor="w", padx=8, pady=6)

        # Incoming messages (with sender)
        msg_box = tk.Text(msg_frame, height=12, wrap="word")
        msg_box.pack(fill="both", expand=True, padx=8, pady=6)
        msg_box.insert("end", "\n".join(
            [f"From {s}: {c}" for (s, c) in (messages or [])]
        ) or "(none yet)")
        msg_box.configure(state="disabled")

        # Known neighbour assignments (compact)
        neigh_frame = ttk.LabelFrame(root, text="Known neighbour assignments (parsed)")
        neigh_frame.pack(fill="x", padx=10, pady=6)
        neigh_text = ", ".join(f"{k}={v}" for k, v in neighbour_assignments.items()) or "(none yet)"
        ttk.Label(neigh_frame, text=neigh_text, wraplength=740).pack(anchor="w", padx=8, pady=4)

        # --- assignments controls ---
        assign_frame = ttk.LabelFrame(root, text="Your nodes")
        assign_frame.pack(fill="x", padx=10, pady=6)

        vars_by_node: Dict[str, tk.StringVar] = {}
        for i, node in enumerate(nodes):
            row = ttk.Frame(assign_frame)
            row.pack(fill="x", padx=8, pady=2)
            ttk.Label(row, text=node, width=8).pack(side="left")
            var = tk.StringVar(value=str(current_assignments.get(node, domain[0])))
            vars_by_node[node] = var
            combo = ttk.Combobox(row, textvariable=var, values=[str(x) for x in domain], width=12, state="readonly")
            combo.pack(side="left")

        # --- outgoing message box ---
        out_frame = ttk.LabelFrame(root, text="Message to neighbour cluster (optional)")
        out_frame.pack(fill="both", expand=True, padx=10, pady=6)
        out_box = tk.Text(out_frame, height=5, wrap="word")
        out_box.pack(fill="both", expand=True, padx=8, pady=6)

        result: Dict[str, Any] = {"done": False, "data": None}

        def on_submit() -> None:
            assignments: Dict[str, Any] = {}
            for node in nodes:
                assignments[node] = vars_by_node[node].get()
            message = out_box.get("1.0", "end").strip()
            result["data"] = HumanTurnResult(assignments=assignments, message=message)
            result["done"] = True
            root.destroy()

        btn = ttk.Button(root, text="Submit turn", command=on_submit)
        btn.pack(pady=10)

        root.mainloop()
        if not result["done"] or result["data"] is None:
            # Window was closed; fall back to keeping current assignments.
            return HumanTurnResult(assignments=dict(current_assignments), message="")
        return result["data"]
