"""Grid navigation shared by simulation and controllers."""

import math
import heapq
from .map_data import LIMIT, BUILDINGS, W


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def walkable(x, y):
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
    """Four-neighbor A* on a one-unit grid, avoiding houses."""
    start = tuple(round(v) for v in start)
    goal = tuple(round(v) for v in goal)
    if not walkable(*goal):
        return []
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
