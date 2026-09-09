from __future__ import annotations

import json
import math
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


CLINICAL_CATEGORIES = {
    "OPERATING_ROOM",
    "PREP",
    "RECOVERY",
    "PREOP",
    "CORRIDOR",
    "SCRUB",
    "STERILIZATION",
}

CONDITIONED_CATEGORIES = CLINICAL_CATEGORIES | {
    "EQUIPMENT",
    "DOCTORS",
    "STAFF",
    "NURSE_STATION",
    "STORAGE",
    "TOILET",
    "CONTROL",
    "MEETING",
    "OFFICE",
    "SUPPORT",
}


def _suffix_number(name: str) -> int:
    m = re.search(r"\((\d+)\)\s*$", name)
    return int(m.group(1)) if m else 1


def english_name(source_name: str) -> str:
    """Translate the source FloorSpace room label into a stable English display name.

    The FloorSpace JSON is the geometry authority. This translation layer changes only
    display labels; it never mutates source geometry or OpenStudio handles.
    """
    n = source_name.strip()
    num = _suffix_number(n)

    if n.startswith("Phòng mổ"):
        return f"Operating Room {num}"
    if n.startswith("Chuẩn bị Prep."):
        return f"Preparation Room {num}"
    if n.startswith("Corridor"):
        return f"Corridor {num}"
    if n.startswith("Hồi sức"):
        return "Recovery Room"
    if n.startswith("Tiền phẫu"):
        return "Pre-op Area"
    if n.startswith("Thiết bị Equip."):
        return f"Equipment Room {num}"
    if n.startswith("Bác sĩ Doct."):
        return f"Doctors' Room {num}"
    if n == "Bác sĩ (nam)":
        return "Male Doctors' Room"
    if n == "Bác sĩ (nữ)":
        return "Female Doctors' Room"
    if n.startswith("Bác sĩ thay đồ (nam)"):
        return "Male Doctors' Changing Room"
    if n.startswith("Bác sĩ thay đồ (nữ)"):
        return "Female Doctors' Changing Room"
    if n.startswith("Quầy điều dưỡng"):
        return f"Nurse Station {num}"
    if n == "Y tá":
        return "Nurses' Room"
    if n == "Hộ lý":
        return "Orderly Room"
    if n == "Phòng thư giãn":
        return "Staff Lounge"
    if n == "Phòng điều khiển":
        return "Control Room"
    if n == "Phòng nghỉ":
        return "Rest Room"
    if n == "Phòng họp":
        return "Meeting Room"
    if n == "Kho":
        return "Storage"
    if n == "Rửa":
        return "Scrub Room"
    if n.startswith("Rửa sạch"):
        return f"Clean Wash Room {num}"
    if n == "Thanh trùng":
        return "Sterilization Room"
    if n.startswith("Toilet"):
        return f"Restroom {num}"
    if n.startswith("Stairs"):
        return f"Stair {num}"
    if n.startswith("Void"):
        return f"Void {num}"
    if n == "Chứa rác":
        return "Waste Holding"
    if n == "Chứa đồ dơ":
        return "Soiled Utility"
    if n == "P. người làm":
        return "Staff Room"
    if n == "N.S":
        return "N.S."
    if n == "Office":
        return "Office"
    if n in {"D.S.A", "C.P.U."}:
        return n
    return n


def room_category(source_name: str) -> str:
    n = source_name.strip()
    if n.startswith("Phòng mổ"):
        return "OPERATING_ROOM"
    if n.startswith("Chuẩn bị Prep."):
        return "PREP"
    if n.startswith("Hồi sức"):
        return "RECOVERY"
    if n.startswith("Tiền phẫu"):
        return "PREOP"
    if n.startswith("Corridor"):
        return "CORRIDOR"
    if n == "Rửa":
        return "SCRUB"
    if n.startswith("Rửa sạch") or n == "Thanh trùng":
        return "STERILIZATION"
    if n.startswith("Thiết bị Equip."):
        return "EQUIPMENT"
    if n.startswith("Bác sĩ"):
        return "DOCTORS"
    if n.startswith("Quầy điều dưỡng") or n == "Y tá":
        return "NURSE_STATION"
    if n in {"Kho", "Chứa rác", "Chứa đồ dơ"}:
        return "STORAGE"
    if n.startswith("Toilet"):
        return "TOILET"
    if n.startswith("Stairs"):
        return "STAIRS"
    if n.startswith("Void"):
        return "VOID"
    if n == "Phòng điều khiển":
        return "CONTROL"
    if n == "Phòng họp":
        return "MEETING"
    if n in {"Office"}:
        return "OFFICE"
    if n in {"Phòng thư giãn", "Phòng nghỉ", "Hộ lý", "P. người làm"}:
        return "STAFF"
    return "SUPPORT"


# Explicit demo capability profile. The OpenStudio/FloorSpace files do not encode
# clinical specialty. Keeping this separate makes the assumption visible/editable.
OR_CAPABILITIES: Dict[int, List[str]] = {
    1: ["GENERAL", "CARDIAC", "VASCULAR"],
    2: ["GENERAL", "GASTROINTESTINAL", "UROLOGY"],
    3: ["ORTHOPEDICS", "TRAUMA", "NEUROSURGERY"],
    4: ["ENT", "UROLOGY", "MINOR"],
    5: ["CARDIAC", "TRAUMA", "NEUROSURGERY", "GENERAL"],
    6: ["MINOR", "ENDOSCOPY", "ENT"],
    7: ["ORTHOPEDICS", "GENERAL", "GYNECOLOGY"],
    8: ["GENERAL", "GYNECOLOGY", "ENT"],
}


def _or_capabilities(display_name: str, config: Optional[Dict[str, List[str]]] = None) -> List[str]:
    if config and display_name in config:
        return [str(x).upper() for x in config[display_name]]
    m = re.search(r"(\d+)$", display_name)
    idx = int(m.group(1)) if m else 1
    return list(OR_CAPABILITIES.get(idx, ["GENERAL"]))


def _polygon_area(points: List[Tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    return abs(
        sum(
            points[i][0] * points[(i + 1) % len(points)][1]
            - points[(i + 1) % len(points)][0] * points[i][1]
            for i in range(len(points))
        )
        / 2.0
    )


def _polygon_centroid(points: List[Tuple[float, float]]) -> Tuple[float, float]:
    if len(points) < 3:
        if not points:
            return (0.0, 0.0)
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
    cross_sum = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(len(points)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        cross_sum += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(cross_sum) < 1e-9:
        return (
            sum(p[0] for p in points) / len(points),
            sum(p[1] for p in points) / len(points),
        )
    factor = 1.0 / (3.0 * cross_sum)
    return (cx * factor, cy * factor)


@dataclass(frozen=True)
class FloorplanModel:
    story: Dict[str, Any]
    rooms: List[Dict[str, Any]]
    doors: List[Dict[str, Any]]
    adjacency: Dict[str, List[str]]
    bounds: Dict[str, float]

    def room_map(self) -> Dict[str, Dict[str, Any]]:
        return {room["id"]: room for room in self.rooms}

    def operating_rooms(self) -> List[Dict[str, Any]]:
        return [r for r in self.rooms if r["category"] == "OPERATING_ROOM"]

    def rooms_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [r for r in self.rooms if r["category"] == category]

    def shortest_path(self, start_room_id: str, end_room_id: str) -> List[str]:
        if start_room_id == end_room_id:
            return [start_room_id]
        if start_room_id not in self.adjacency or end_room_id not in self.adjacency:
            return []
        q: deque[str] = deque([start_room_id])
        parent: Dict[str, Optional[str]] = {start_room_id: None}
        while q:
            node = q.popleft()
            for nxt in self.adjacency.get(node, []):
                if nxt in parent:
                    continue
                parent[nxt] = node
                if nxt == end_room_id:
                    path = [nxt]
                    cur: Optional[str] = nxt
                    while cur is not None and cur != start_room_id:
                        cur = parent[cur]
                        if cur is not None:
                            path.append(cur)
                    return list(reversed(path))
                q.append(nxt)
        return []

    def graph_distance(self, a: str, b: str) -> int:
        path = self.shortest_path(a, b)
        return max(0, len(path) - 1) if path else 999

    def public_dict(self) -> Dict[str, Any]:
        return {
            "story": self.story,
            "bounds": self.bounds,
            "rooms": self.rooms,
            "doors": self.doors,
            "adjacency": self.adjacency,
            "capability_source": "BEAM_DEMO_CONFIG_NOT_OPENSTUDIO",
        }


def load_floorplan(path: str | Path) -> FloorplanModel:
    source_path = Path(path)
    source = json.loads(source_path.read_text(encoding="utf-8"))
    capability_config: Optional[Dict[str, List[str]]] = None
    capability_path = source_path.with_name("or_capabilities.json")
    if capability_path.exists():
        raw_config = json.loads(capability_path.read_text(encoding="utf-8"))
        if isinstance(raw_config, dict):
            capability_config = {str(k): list(v) for k, v in raw_config.items() if isinstance(v, list)}
    stories = source.get("stories") or []
    if not stories:
        raise ValueError("FloorSpace JSON has no stories")
    story = stories[0]
    geometry = story.get("geometry") or {}
    vertices = {str(v["id"]): (float(v["x"]), float(v["y"])) for v in geometry.get("vertices", [])}
    edges = {str(e["id"]): e for e in geometry.get("edges", [])}
    faces = {str(f["id"]): f for f in geometry.get("faces", [])}

    def face_polygon(face_id: str) -> List[Tuple[float, float]]:
        face = faces[str(face_id)]
        edge_ids = face.get("edge_ids") or []
        edge_order = face.get("edge_order") or [1] * len(edge_ids)
        vertex_ids: List[str] = []
        for idx, (edge_id, direction) in enumerate(zip(edge_ids, edge_order)):
            edge = edges[str(edge_id)]
            a, b = [str(x) for x in edge["vertex_ids"]]
            # FloorSpace edge_order uses 1=forward, 0=reverse.
            if int(direction) == 0:
                a, b = b, a
            if idx == 0:
                vertex_ids.extend([a, b])
            else:
                if vertex_ids[-1] != a:
                    raise ValueError(f"Non-contiguous face {face_id}: edge {edge_id}")
                vertex_ids.append(b)
        if len(vertex_ids) > 1 and vertex_ids[-1] == vertex_ids[0]:
            vertex_ids.pop()
        return [vertices[v] for v in vertex_ids]

    face_to_room: Dict[str, str] = {}
    rooms: List[Dict[str, Any]] = []
    xs: List[float] = []
    ys: List[float] = []

    for space in story.get("spaces") or []:
        source_name = str(space.get("name") or "Unnamed Space")
        display = english_name(source_name)
        category = room_category(source_name)
        polygon = face_polygon(str(space["face_id"]))
        if not polygon:
            continue
        area = _polygon_area(polygon)
        centroid = _polygon_centroid(polygon)
        room_id = f"space-{space['id']}"
        face_to_room[str(space["face_id"])] = room_id
        xs.extend(p[0] for p in polygon)
        ys.extend(p[1] for p in polygon)
        rooms.append(
            {
                "id": room_id,
                "source_space_id": str(space["id"]),
                "source_face_id": str(space["face_id"]),
                "openstudio_handle": space.get("handle"),
                "source_name": source_name,
                "name": display,
                "category": category,
                "area_m2": round(area, 2),
                "polygon": [[round(x, 4), round(y, 4)] for x, y in polygon],
                "centroid": [round(centroid[0], 4), round(centroid[1], 4)],
                "conditioned": category in CONDITIONED_CATEGORIES,
                "capabilities": _or_capabilities(display, capability_config) if category == "OPERATING_ROOM" else [],
                "capability_source": "BEAM_DEMO_CONFIG_NOT_OPENSTUDIO" if category == "OPERATING_ROOM" else None,
            }
        )

    rooms.sort(key=lambda r: (r["category"] != "OPERATING_ROOM", r["name"]))

    adjacency_sets: Dict[str, set[str]] = {r["id"]: set() for r in rooms}
    doors: List[Dict[str, Any]] = []
    for door in story.get("doors") or []:
        edge = edges.get(str(door.get("edge_id")))
        if not edge:
            continue
        a_id, b_id = [str(x) for x in edge["vertex_ids"]]
        ax, ay = vertices[a_id]
        bx, by = vertices[b_id]
        alpha = float(door.get("alpha", 0.5))
        x = ax + (bx - ax) * alpha
        y = ay + (by - ay) * alpha
        connected = [face_to_room[f] for f in map(str, edge.get("face_ids") or []) if f in face_to_room]
        connected = list(dict.fromkeys(connected))
        if len(connected) == 2:
            a, b = connected
            adjacency_sets[a].add(b)
            adjacency_sets[b].add(a)
        doors.append(
            {
                "id": f"door-{door['id']}",
                "source_door_id": str(door["id"]),
                "edge_id": str(door.get("edge_id")),
                "point": [round(x, 4), round(y, 4)],
                "room_ids": connected,
            }
        )

    adjacency = {room_id: sorted(neighbors) for room_id, neighbors in adjacency_sets.items()}
    bounds = {
        "min_x": min(xs) if xs else 0.0,
        "max_x": max(xs) if xs else 1.0,
        "min_y": min(ys) if ys else 0.0,
        "max_y": max(ys) if ys else 1.0,
    }
    story_public = {
        "id": str(story.get("id")),
        "name": "Surgical Suite — Level 1",
        "source_name": story.get("name"),
        "floor_to_ceiling_height_m": float(story.get("floor_to_ceiling_height") or 2.4384),
        "space_count": len(rooms),
    }
    return FloorplanModel(
        story=story_public,
        rooms=rooms,
        doors=doors,
        adjacency=adjacency,
        bounds=bounds,
    )
