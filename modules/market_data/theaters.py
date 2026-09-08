from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Mapping, Optional, Sequence


@dataclass(frozen=True)
class TheaterSpec:
    """Reviewed theater highlight, not an incident polygon."""

    theater_id: str
    label: str
    parent_region: str
    lat: float
    lon: float
    aliases: tuple[str, ...]
    geometry_note: str


# Centroids are approximate geographic centers of named theaters, not
# battlefronts. Used only when supporting text mentions the theater.
THEATERS: tuple[TheaterSpec, ...] = (
    TheaterSpec(
        "ukraine",
        "Ukraine",
        "Europe",
        48.38,
        31.17,
        ("ukraine", "kyiv", "kharkiv", "donbas", "donetsk", "luhansk", "crimea", "odesa"),
        "Geographic center of Ukraine. Not a front-line or oblast footprint.",
    ),
    TheaterSpec(
        "black-sea",
        "Black Sea",
        "Europe",
        43.4,
        34.3,
        ("black sea", "sevastopol", "azov"),
        "Approximate Black Sea basin center. Not a maritime exclusion zone.",
    ),
    TheaterSpec(
        "myanmar",
        "Myanmar",
        "Asia-Pacific",
        21.92,
        96.15,
        ("myanmar", "burma", "rakhine", "naypyidaw", "people's defense force"),
        "Approximate center of Myanmar. Not township-level conflict geometry.",
    ),
    TheaterSpec(
        "taiwan-scs",
        "Taiwan / South China Sea",
        "Asia-Pacific",
        21.0,
        117.5,
        ("taiwan", "south china sea", "taiwan strait", "west philippine sea"),
        "Basin highlight between Taiwan and the South China Sea. Not a claim line.",
    ),
    TheaterSpec(
        "kashmir",
        "Kashmir",
        "Asia-Pacific",
        34.05,
        76.0,
        ("kashmir", "jammu and kashmir", "line of control"),
        "Approximate Kashmir highland center. Not a ceasefire-line trace.",
    ),
    TheaterSpec(
        "israel-gaza",
        "Israel / Gaza",
        "Middle East",
        31.5,
        34.75,
        ("gaza", "israel", "west bank", "tel aviv", "rafah"),
        "Coastal Levant highlight. Not an operational boundary.",
    ),
    TheaterSpec(
        "yemen-red-sea",
        "Yemen / Red Sea",
        "Middle East",
        15.55,
        43.0,
        ("yemen", "houthi", "red sea", "bab el-mandeb", "aden"),
        "Yemen/Red Sea approach highlight. Not a shipping-lane polygon.",
    ),
    TheaterSpec(
        "iran",
        "Iran",
        "Middle East",
        32.4,
        53.7,
        ("iran", "tehran", "strait of hormuz"),
        "Approximate center of Iran. Not a strike or air-defense map.",
    ),
    TheaterSpec(
        "sudan",
        "Sudan",
        "Africa",
        15.6,
        32.5,
        ("sudan", "khartoum", "darfur", "rsf"),
        "Approximate center of Sudan. Not a city-fight footprint.",
    ),
    TheaterSpec(
        "sahel",
        "Sahel",
        "Africa",
        16.0,
        -2.0,
        ("sahel", "mali", "burkina faso", "niger"),
        "Central Sahel highlight. Not an insurgency shapefile.",
    ),
    TheaterSpec(
        "drc",
        "Eastern DRC",
        "Africa",
        -1.7,
        29.2,
        ("congo", "drc", "goma", "m23", "north kivu"),
        "Eastern DRC highland highlight. Not a militia area of operations.",
    ),
)


def match_theaters(
    texts: Sequence[str],
    *,
    parent_region: Optional[str] = None,
) -> List[TheaterSpec]:
    blob = " ".join(str(item or "") for item in texts).casefold()
    if not blob.strip():
        return []
    hits: List[TheaterSpec] = []
    for theater in THEATERS:
        if parent_region and theater.parent_region != parent_region:
            continue
        if any(
            re.search(rf"(?<!\w){re.escape(alias.casefold())}(?!\w)", blob)
            for alias in theater.aliases
        ):
            hits.append(theater)
    return hits


def headlines_from_items(items: Iterable[Mapping[str, object]], limit: int = 3) -> List[dict]:
    rows: List[dict] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        rows.append(
            {
                "title": title[:180],
                "source": (str(item.get("source") or "").strip() or None),
                "published_ts": item.get("published_ts"),
            }
        )
        if len(rows) >= limit:
            break
    return rows
