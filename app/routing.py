import heapq
from typing import Dict, Iterable, List, Optional, Tuple

Graph = Dict[str, List[Tuple[str, float]]]


def build_graph(edges: Iterable[Tuple[str, str, float]]) -> Graph:
    graph: Graph = {}
    for src, dst, latency in edges:
        graph.setdefault(src, []).append((dst, latency))
    return graph


def shortest_path(graph: Graph, source: str, destination: str) -> Optional[Tuple[float, List[str]]]:
    # Dijkstra's algorithm, returns (total_latency, path) or None if there is no path
    if source == destination:
        return 0.0, [source]

    dist: Dict[str, float] = {source: 0.0}
    prev: Dict[str, str] = {}
    heap: List[Tuple[float, str]] = [(0.0, source)]
    visited = set()

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == destination:
            break
        for nxt, weight in graph.get(node, ()):
            nd = d + weight
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                prev[nxt] = node
                heapq.heappush(heap, (nd, nxt))

    if destination not in visited:
        return None

    path = [destination]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    return round(dist[destination], 6), path
