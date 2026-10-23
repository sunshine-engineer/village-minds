"""Grid navigation shared by simulation and controllers.

File: village/navigation.py
Maintainer: sunshine-engineer
Modified: 2026-10-23
"""

import heapq
import math

from .map_data import BUILDINGS, LIMIT, W


def distance(a, b):
    """Measure Euclidean distance between two planar positions.

    Args:
        a: First planar point or RGB endpoint.
        b: Second planar point or RGB endpoint.

    Returns:
        Distance in world units.
    """
    return math.hypot(a[0] - b[0], a[1] - b[1])


def walkable(x, y):
    """Test map bounds, wall openings and configured building clearance.

    Args:
        x: Planar x coordinate.
        y: Planar y coordinate.

    Returns:
        Whether the grid position can be occupied.
    """
    at_wall = (
        abs(abs(x) - W["wall_coordinate"]) < W["wall_half_thickness"]
        and abs(y) > W["gate_half_opening"]
        and abs(y) < (W["wall_coordinate"] + W["wall_half_thickness"])
    ) or (
        abs(abs(y) - W["wall_coordinate"]) < W["wall_half_thickness"]
        and abs(x) > W["gate_half_opening"]
        and abs(x) < (W["wall_coordinate"] + W["wall_half_thickness"])
    )
    return (
        abs(x) <= LIMIT
        and abs(y) <= LIMIT
        and not at_wall
        and not any(
            abs(x - bx) < hx + W["navigation_clearance"]
            and abs(y - by) < hy + W["navigation_clearance"]
            for bx, by, hx, hy in BUILDINGS
        )
    )


def pathfind(start, goal):
    """Four-neighbor A* on a one-unit grid, avoiding houses.

    Args:
        start: Initial planar world position.
        goal: Requested planar destination.

    Returns:
        Route excluding the start; empty for an unreachable or already-reached goal.
    """
    exact_start = tuple(start)
    start = tuple(round(v) for v in start)
    goal = tuple(round(v) for v in goal)
    if not walkable(*goal):
        return []
    if start == goal:
        return [goal] if distance(exact_start, goal) > 1e-9 else []
    frontier = [(0, start)]
    cost, came = {start: 0}, {}
    while frontier:
        _, cell = heapq.heappop(frontier)
        if cell == goal:
            path = [cell]
            while cell in came:
                cell = came[cell]
                path.append(cell)
            return list(reversed(path))[1:]
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = cell[0] + dx, cell[1] + dy
            new = cost[cell] + 1
            if walkable(*nxt) and new < cost.get(nxt, float("inf")):
                cost[nxt], came[nxt] = new, cell
                heapq.heappush(frontier, (new + distance(nxt, goal), nxt))
    return []


def work_point(start, center, radius, offset=(0, 0)):
    """Find a reachable grid cell strictly inside an action's work radius.

    Prefer a personal offset to reduce crowding, then nearby alternatives. A plot
    center may be blocked by a building; working beside it can still be legal.

    Args:
        start: Initial planar world position.
        center: Center of the action work area.
        radius: Strict action work radius in world units.
        offset: Preferred personal planar offset from the service center.

    Returns:
        Work position, or None when no legal reachable cell exists.
    """
    preferred = tuple(round(v + delta) for v, delta in zip(center, offset))
    candidates = [
        (x, y)
        for x in range(
            math.ceil(center[0] - radius), math.floor(center[0] + radius) + 1
        )
        for y in range(
            math.ceil(center[1] - radius), math.floor(center[1] + radius) + 1
        )
        if distance((x, y), center) < radius and walkable(x, y)
    ]
    candidates.sort(key=lambda p: (distance(p, preferred), distance(start, p), p))
    for point in candidates:
        if distance(start, point) < 1e-9 or pathfind(start, point):
            return point
    return None
