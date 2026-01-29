"""Experimenter debug window.

This is *not* participant-facing. It lets the experimenter inspect each
agent's perspective and internal state while the main human UI runs.

The goal is to make it clear how agent decisions relate to:
 - incoming messages (raw + parsed)
 - chosen internal assignments
 - structured messages the agent is generating (cost_list/constraints)

The debug window intentionally exposes information that participants
should not see.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


class DebugWindow:
    def __init__(self, root, *, agents: List[Any], owners: Dict[str, str], get_visible_graph_fn) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._root = root
        self._agents = agents
        self._owners = owners
        self._get_visible_graph_fn = get_visible_graph_fn

        self._win = tk.Toplevel(root)
        self._win.title("Debug (Experimenter)")
        self._win.geometry("1200x820")

        FONT_H = ("Arial", 16, "bold")
        FONT_B = ("Arial", 13)

        top = ttk.Frame(self._win)
        top.pack(fill="x", padx=10, pady=10)
        ttk.Label(top, text="Agent:", font=FONT_H).pack(side="left")

        self._agent_names = [a.name for a in agents]
        self._selected = tk.StringVar(value=self._agent_names[0] if self._agent_names else "")
        combo = ttk.Combobox(top, textvariable=self._selected, values=self._agent_names, state="readonly", width=30)
        combo.pack(side="left", padx=8)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh())

        main = ttk.Frame(self._win)
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # left: graph
        self._canvas = tk.Canvas(main, width=560, height=560, background="white", highlightthickness=1)
        self._canvas.pack(side="left", fill="both", expand=False)

        # zoom/pan state for the graph canvas
        self._zoom = 1.0
        self._pan = (0.0, 0.0)
        self._drag_last = None

        # Mouse bindings: wheel to zoom, left-drag to pan
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<Button-4>", lambda e: self._on_wheel(e, delta=120))
        self._canvas.bind("<Button-5>", lambda e: self._on_wheel(e, delta=-120))
        self._canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self._canvas.bind("<B1-Motion>", self._on_drag_move)

        # right: text panes
        right = ttk.Frame(main)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self._info = tk.Text(right, height=14, font=FONT_B, wrap="word")
        self._info.pack(fill="x", pady=(0, 10))

        panes = ttk.Frame(right)
        panes.pack(fill="both", expand=True)
        self._incoming = tk.Text(panes, font=FONT_B, wrap="word")
        self._incoming.pack(side="left", fill="both", expand=True, padx=(0, 6))
        self._outgoing = tk.Text(panes, font=FONT_B, wrap="word")
        self._outgoing.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # Tabs: Reasoning + LLM trace. This avoids the lower panels being hidden on
        # smaller screens and makes it obvious where to find the LLM prompts.
        tabs = ttk.Notebook(right)
        tabs.pack(fill="both", expand=False, pady=(10, 0))

        reasoning_tab = ttk.Frame(tabs)
        llm_tab = ttk.Frame(tabs)
        tabs.add(reasoning_tab, text="Reasoning")
        tabs.add(llm_tab, text="LLM trace")

        # Reasoning history viewer
        self._reason_index: Dict[str, int] = {}
        reason_bar = ttk.Frame(reasoning_tab)
        reason_bar.pack(fill="x", pady=(6, 2))
        ttk.Label(reason_bar, text="Reasoning", font=("Arial", 13, "bold")).pack(side="left")
        self._reason_page = ttk.Label(reason_bar, text="0/0", font=("Arial", 12))
        self._reason_page.pack(side="left", padx=(10, 0))
        ttk.Button(reason_bar, text="◀", width=3, command=lambda: self._nav_reason(-1)).pack(side="left", padx=(10, 2))
        ttk.Button(reason_bar, text="▶", width=3, command=lambda: self._nav_reason(1)).pack(side="left")
        self._reasoning = tk.Text(reasoning_tab, height=18, font=FONT_B, wrap="word")
        self._reasoning.pack(fill="both", expand=True)

        # LLM call trace viewer (prompt/response/parsed)
        self._llm_index: Dict[str, int] = {}
        llm_bar = ttk.Frame(llm_tab)
        llm_bar.pack(fill="x", pady=(6, 2))
        ttk.Label(llm_bar, text="LLM call trace", font=("Arial", 13, "bold")).pack(side="left")
        self._llm_page = ttk.Label(llm_bar, text="0/0", font=("Arial", 12))
        self._llm_page.pack(side="left", padx=(10, 0))
        ttk.Button(llm_bar, text="◀", width=3, command=lambda: self._nav_llm(-1)).pack(side="left", padx=(10, 2))
        ttk.Button(llm_bar, text="▶", width=3, command=lambda: self._nav_llm(1)).pack(side="left")
        self._llm = tk.Text(llm_tab, height=20, font=FONT_B, wrap="word")
        self._llm.pack(fill="both", expand=True)

        ttk.Label(right, text="Left: incoming (raw + parsed). Right: outgoing (structured).", font=("Arial", 12)).pack(anchor="w", pady=(8, 0))

        self.refresh()

    def destroy(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass

    def _get_agent(self):
        name = self._selected.get()
        for a in self._agents:
            if a.name == name:
                return a
        return self._agents[0] if self._agents else None

    def _nav_reason(self, delta: int) -> None:
        a = self._get_agent()
        if a is None:
            return
        name = a.name
        hist = list(getattr(a, "debug_reasoning_history", []))
        if not hist:
            return
        idx = self._reason_index.get(name, len(hist) - 1)
        idx = max(0, min(len(hist) - 1, idx + delta))
        self._reason_index[name] = idx
        self.refresh()

    def _nav_llm(self, delta: int) -> None:
        a = self._get_agent()
        if a is None:
            return
        name = a.name
        calls = []
        try:
            cl = getattr(a, "comm_layer", None)
            calls = list(getattr(cl, "debug_calls", [])) if cl is not None else []
        except Exception:
            calls = []
        if not calls:
            return
        idx = self._llm_index.get(name, len(calls) - 1)
        idx = max(0, min(len(calls) - 1, idx + delta))
        self._llm_index[name] = idx
        self.refresh()

    def refresh(self) -> None:
        a = self._get_agent()
        if a is None:
            return

        # ----- info -----
        self._info.delete("1.0", "end")
        nodes = getattr(a, "nodes", [])
        assigns = getattr(a, "assignments", {})
        neigh_assigns = getattr(a, "neighbour_assignments", {})
        dec = getattr(a, "debug_last_decision", {})
        self._info.insert("end", f"Name: {a.name}\n")
        self._info.insert("end", f"Nodes: {nodes}\n")
        self._info.insert("end", f"Assignments: {assigns}\n")
        if neigh_assigns:
            self._info.insert("end", f"Known neighbour assignments (from language parsing): {neigh_assigns}\n")
        if dec:
            self._info.insert("end", f"Decision: {dec}\n")

        # ----- RB protocol state (if applicable) -----
        if hasattr(a, 'rb_active_offers'):
            rb_phase = getattr(a, 'rb_phase', 'N/A')
            rb_iteration = getattr(a, 'rb_iteration_counter', 0)
            satisfied = getattr(a, 'satisfied', False)
            self._info.insert("end", f"\n--- RB Protocol State ---\n")
            self._info.insert("end", f"Phase: {rb_phase}, Iteration: {rb_iteration}, Satisfied: {satisfied}\n")

            # Show pending offers (waiting for response)
            active_offers = getattr(a, 'rb_active_offers', {})
            accepted_offers = getattr(a, 'rb_accepted_offers', set())
            rejected_offers = getattr(a, 'rb_rejected_offers', set())
            offer_iterations = getattr(a, 'rb_offer_iteration', {})

            # Separate our offers from their offers
            our_pending = []
            their_pending = []
            for offer_id, offer in active_offers.items():
                if offer_id in accepted_offers or offer_id in rejected_offers:
                    continue
                if a.name in offer_id:
                    our_pending.append(offer_id)
                else:
                    their_pending.append(offer_id)

            if our_pending:
                self._info.insert("end", f"\nPending offers WE sent (waiting for response):\n")
                for offer_id in our_pending:
                    offer_iter = offer_iterations.get(offer_id, 0)
                    age = rb_iteration - offer_iter
                    offer_obj = active_offers.get(offer_id)
                    num_cond = len(offer_obj.conditions) if hasattr(offer_obj, 'conditions') and offer_obj.conditions else 0
                    num_assign = len(offer_obj.assignments) if hasattr(offer_obj, 'assignments') and offer_obj.assignments else 0
                    self._info.insert("end", f"  • {offer_id} (age: {age} iter, {num_cond} cond, {num_assign} assign)\n")
                if our_pending:
                    self._info.insert("end", "  ⚠ Agent is waiting for response - may block new offers!\n")

            if their_pending:
                self._info.insert("end", f"\nPending offers FROM others (need our response):\n")
                for offer_id in their_pending:
                    offer_iter = offer_iterations.get(offer_id, 0)
                    age = rb_iteration - offer_iter
                    self._info.insert("end", f"  • {offer_id} (age: {age} iter)\n")

        # ----- incoming -----
        self._incoming.delete("1.0", "end")
        raw = list(getattr(a, "debug_incoming_raw", []))[-10:]
        parsed = list(getattr(a, "debug_incoming_parsed", []))[-10:]
        for i, (r, p) in enumerate(zip(raw, parsed), start=1):
            self._incoming.insert("end", f"#{i} RAW:\n{r}\n")
            self._incoming.insert("end", f"   PARSED:\n{p}\n\n")

        # ----- outgoing -----
        self._outgoing.delete("1.0", "end")
        out = getattr(a, "debug_last_outgoing", {})
        self._outgoing.insert("end", f"Outgoing (structured, pre-comm-layer):\n{out}\n")

        # ----- reasoning -----
        self._reasoning.delete("1.0", "end")
        history = list(getattr(a, "debug_reasoning_history", []))
        if history:
            idx = self._reason_index.get(a.name)
            if idx is None:
                idx = len(history) - 1
            idx = max(0, min(len(history) - 1, idx))
            self._reason_index[a.name] = idx
            self._reason_page.config(text=f"{idx+1}/{len(history)}")
            snap = history[idx]
            # Format a compact, readable trace
            self._reasoning.insert("end", f"Iteration: {snap.get('iteration')}\n")
            self._reasoning.insert("end", f"Known neighbour assignments: {snap.get('known_neighbour_assignments')}\n\n")
            self._reasoning.insert("end", "Local scores (penalty per colour)\n")
            scores = snap.get('local_scores') or {}
            for node, cm in scores.items():
                self._reasoning.insert("end", f"  {node}: {cm}\n")
            self._reasoning.insert("end", "\nChosen assignments\n")
            self._reasoning.insert("end", f"  {snap.get('chosen_assignments')}\n")
        else:
            self._reason_page.config(text="0/0")
            self._reasoning.insert("end", "(no reasoning snapshots yet)\n")

        # ----- llm call trace -----
        self._llm.delete("1.0", "end")
        calls = []
        try:
            cl = getattr(a, "comm_layer", None)
            calls = list(getattr(cl, "debug_calls", [])) if cl is not None else []
        except Exception:
            calls = []
        if calls:
            idx = self._llm_index.get(a.name)
            if idx is None:
                idx = len(calls) - 1
            idx = max(0, min(len(calls) - 1, idx))
            self._llm_index[a.name] = idx
            self._llm_page.config(text=f"{idx+1}/{len(calls)}")
            c = calls[idx]
            self._llm.insert("end", f"Kind: {c.get('kind')}\n\n")
            self._llm.insert("end", "PROMPT\n")
            self._llm.insert("end", f"{c.get('prompt')}\n\n")
            self._llm.insert("end", "RESPONSE\n")
            self._llm.insert("end", f"{c.get('response')}\n\n")
            self._llm.insert("end", "PARSED / GLEANED\n")
            self._llm.insert("end", f"{c.get('parsed')}\n\n")
            msgs = c.get('messages')
            if msgs:
                self._llm.insert("end", "FULL MESSAGES (as sent / would be sent)\n")
                try:
                    for m in msgs:
                        self._llm.insert("end", f"- {m.get('role')}: {m.get('content')}\n")
                except Exception:
                    self._llm.insert("end", f"{msgs}\n")
        else:
            self._llm_page.config(text="0/0")
            self._llm.insert("end", "(no LLM calls recorded for this agent yet)\n")

        # ----- graph -----
        self._draw_agent_graph(a)

    def _on_wheel(self, event, delta: int | None = None) -> None:
        # Zoom about the cursor position
        d = delta if delta is not None else getattr(event, "delta", 0)
        if d == 0:
            return
        factor = 1.1 if d > 0 else 1 / 1.1
        self._zoom = max(0.4, min(3.0, self._zoom * factor))
        self._draw_agent_graph(self._get_agent())

    def _on_drag_start(self, event) -> None:
        self._drag_last = (event.x, event.y)

    def _on_drag_move(self, event) -> None:
        if self._drag_last is None:
            return
        lx, ly = self._drag_last
        dx, dy = event.x - lx, event.y - ly
        px, py = self._pan
        self._pan = (px + dx, py + dy)
        self._drag_last = (event.x, event.y)
        self._draw_agent_graph(self._get_agent())

    def _draw_agent_graph(self, a) -> None:
        # Draw the agent's visible graph (its cluster + 1-hop boundary)
        import networkx as nx

        nodes, edges = self._get_visible_graph_fn(a.name)
        G = nx.Graph()
        G.add_nodes_from(nodes)
        G.add_edges_from(edges)

        # Cluster-aware layout: group nodes by owner, position clusters separately
        clusters = {}
        for n in nodes:
            owner = self._owners.get(n, "Unknown")
            if owner not in clusters:
                clusters[owner] = []
            clusters[owner].append(n)

        # Position clusters in a row: Agent1 | Human | Agent2
        cluster_positions = {}
        cluster_order = sorted(clusters.keys())  # Alphabetical order
        num_clusters = len(cluster_order)

        for idx, owner in enumerate(cluster_order):
            # X position for this cluster center (spread across -1 to 1)
            if num_clusters == 1:
                cx = 0.0
            else:
                cx = -1.0 + (idx / (num_clusters - 1)) * 2.0
            cluster_positions[owner] = cx

        # Position nodes within each cluster
        pos = {}
        for owner, cluster_nodes in clusters.items():
            cx = cluster_positions[owner]
            # Create subgraph for this cluster
            subgraph = G.subgraph(cluster_nodes)
            # Use circular layout within cluster
            sub_pos = nx.circular_layout(subgraph, scale=0.3)
            # Offset to cluster center position
            for node, (sx, sy) in sub_pos.items():
                pos[node] = (cx + sx, sy)

        c = self._canvas
        c.delete("all")
        w = int(c.winfo_width() or 560)
        h = int(c.winfo_height() or 560)

        def xy(p):
            # base mapping from layout coords -> canvas coords, then apply pan/zoom
            x0, y0 = (w * (p[0] * 0.8 + 0.5), h * (p[1] * 0.8 + 0.5))
            cx, cy = w / 2.0, h / 2.0
            zx = (x0 - cx) * self._zoom + cx + self._pan[0]
            zy = (y0 - cy) * self._zoom + cy + self._pan[1]
            return (zx, zy)

        # edges
        for u, v in edges:
            x1, y1 = xy(pos[u])
            x2, y2 = xy(pos[v])
            c.create_line(x1, y1, x2, y2, fill="#333", width=2)

        # nodes
        assigns = getattr(a, "assignments", {})
        # boundary nodes: anything visible but not locally owned
        boundary = [n for n in nodes if self._owners.get(n, "") != a.name]
        if boundary:
            # annotate in the info pane to make boundary nodes easy to spot
            try:
                self._info.insert("end", f"Boundary/visible-neighbour nodes: {boundary}\n")
            except Exception:
                pass
        for n in nodes:
            x, y = xy(pos[n])
            r = int(max(12, min(32, 22 * self._zoom)))
            owner = self._owners.get(n, "")
            is_local = owner == a.name
            fill = "#E0E0E0" if not is_local else "#AAF"
            # if local node, colour fill roughly based on assignment name (cosmetic only)
            if is_local and n in assigns:
                val = str(assigns[n]).lower()
                if "red" in val:
                    fill = "#ff9999"
                elif "green" in val:
                    fill = "#99ff99"
                elif "blue" in val:
                    fill = "#9999ff"
                elif "orange" in val:
                    fill = "#ffcc99"

            outline = "#111" if is_local else "#666"
            width = 3 if is_local else 2
            c.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=outline, width=width)
            name_font = ("Arial", int(max(10, min(18, 12 * self._zoom))), "bold")
            owner_font = ("Arial", int(max(8, min(14, 10 * self._zoom))))
            c.create_text(x, y - (r + 10), text=n, font=name_font)
            c.create_text(x, y + (r + 8), text=f"({owner})", font=owner_font)


