// ─── Tactical scheduling — cross-drone dependency cycle detection ─────────
//
// A drone's sequence [t0, t1, ...] implies task t_i can't start until that drone
// finishes t_{i-1}. When two or more drones' sequences disagree on which of a
// shared pair of tasks goes first (e.g. Blue: task1→task2, Red: task2→task1),
// each task ends up waiting on a drone that is itself waiting on the other task
// to finish — neither can ever reach quorum. This is a cycle in the directed
// graph of "task depends on task" edges induced by every drone's sequence.

// Builds the task-depends-on-task graph: an edge t_{i-1} → t_i for every consecutive pair in a
// drone's sequence (t_i can't start until that drone finishes t_{i-1}).
function buildDependencyGraph(
  taskAssignments: Record<string, string[]>,
  droneSequences: Record<string, string[]>,
): Map<string, Set<string>> {
  const graph = new Map<string, Set<string>>()
  const ensure = (id: string) => {
    if (!graph.has(id)) graph.set(id, new Set())
  }
  for (const tid of Object.keys(taskAssignments)) ensure(tid)
  for (const seq of Object.values(droneSequences)) {
    for (let i = 1; i < seq.length; i++) {
      ensure(seq[i - 1])
      ensure(seq[i])
      graph.get(seq[i - 1])!.add(seq[i])
    }
  }
  return graph
}

/**
 * Returns the SET of task IDs that lie on SOME dependency cycle — i.e. the tasks that are
 * genuinely blocking each other (a task can reach itself in the graph). A task that merely waits
 * on a busy drone but isn't part of a mutual-wait cycle (e.g. a downstream task starved of drones
 * that are stuck upstream) is NOT included — it will free up once the real cycle is broken.
 */
export function tasksInCycles(
  taskAssignments: Record<string, string[]>,
  droneSequences: Record<string, string[]>,
): Set<string> {
  const graph = buildDependencyGraph(taskAssignments, droneSequences)
  const result = new Set<string>()
  for (const start of graph.keys()) {
    // Can `start` reach itself by following edges? If so it's on a cycle.
    const seen = new Set<string>()
    const stack = [...(graph.get(start) ?? [])]
    while (stack.length) {
      const n = stack.pop()!
      if (n === start) { result.add(start); break }
      if (seen.has(n)) continue
      seen.add(n)
      for (const m of graph.get(n) ?? []) stack.push(m)
    }
  }
  return result
}

/**
 * Builds the task-depends-on-task graph from per-drone sequences and returns the
 * task IDs forming a cycle (in cycle order), or null if the graph is acyclic.
 */
export function findSchedulingCycle(
  taskAssignments: Record<string, string[]>,
  droneSequences: Record<string, string[]>,
): string[] | null {
  const graph = buildDependencyGraph(taskAssignments, droneSequences)

  const WHITE = 0, GRAY = 1, BLACK = 2
  const color = new Map<string, number>()
  const path: string[] = []
  let cycle: string[] | null = null

  function dfs(node: string): boolean {
    color.set(node, GRAY)
    path.push(node)
    for (const next of graph.get(node) ?? []) {
      const c = color.get(next) ?? WHITE
      if (c === GRAY) {
        const start = path.indexOf(next)
        cycle = path.slice(start)
        return true
      }
      if (c === WHITE && dfs(next)) return true
    }
    path.pop()
    color.set(node, BLACK)
    return false
  }

  for (const node of graph.keys()) {
    if ((color.get(node) ?? WHITE) === WHITE && dfs(node)) return cycle
  }
  return null
}
