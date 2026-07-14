// ─── Tactical scheduling — cross-drone dependency cycle detection ─────────
//
// A drone's sequence [t0, t1, ...] implies task t_i can't start until that drone
// finishes t_{i-1}. When two or more drones' sequences disagree on which of a
// shared pair of tasks goes first (e.g. Blue: task1→task2, Red: task2→task1),
// each task ends up waiting on a drone that is itself waiting on the other task
// to finish — neither can ever reach quorum. This is a cycle in the directed
// graph of "task depends on task" edges induced by every drone's sequence.

/**
 * Builds the task-depends-on-task graph from per-drone sequences and returns the
 * task IDs forming a cycle (in cycle order), or null if the graph is acyclic.
 */
export function findSchedulingCycle(
  taskAssignments: Record<string, string[]>,
  droneSequences: Record<string, string[]>,
): string[] | null {
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
