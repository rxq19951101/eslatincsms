#
# 地理编码（站点地址搜索）
# 通过 CSMS 后端代理调用 OSM Nominatim，规避浏览器 CORS，并统一 User-Agent / 缓存 / 限流。
#

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


NOMINATIM_BASE_URL = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")
NOMINATIM_USER_AGENT = os.getenv("NOMINATIM_USER_AGENT", "eslatin-csms/1.0 (admin geocoding)")
NOMINATIM_COUNTRYCODES = os.getenv("NOMINATIM_COUNTRYCODES", "co").strip().lower()

# 简单进程内 TTL 缓存（key = (q, limit)）
_cache: Dict[Tuple[str, int], Tuple[float, List[Dict[str, Any]]]] = {}
_cache_lock = threading.Lock()
_cache_ttl_sec = int(os.getenv("NOMINATIM_CACHE_TTL_SECONDS", "600"))  # 默认 10 分钟

# 简单限流（进程内）：两次请求间隔至少 N ms
_min_interval_sec = float(os.getenv("NOMINATIM_MIN_INTERVAL_SECONDS", "0.8"))
_last_request_at = 0.0
_rate_lock = threading.Lock()


def _now() -> float:
    return time.time()


def _get_cached(key: Tuple[str, int]) -> Optional[List[Dict[str, Any]]]:
    now = _now()
    with _cache_lock:
        item = _cache.get(key)
        if not item:
            return None
        ts, data = item
        if now - ts > _cache_ttl_sec:
            _cache.pop(key, None)
            return None
        return data


def _set_cached(key: Tuple[str, int], data: List[Dict[str, Any]]) -> None:
    with _cache_lock:
        _cache[key] = (_now(), data)


def _enforce_rate_limit() -> None:
    global _last_request_at
    with _rate_lock:
        now = _now()
        elapsed = now - _last_request_at
        if elapsed < _min_interval_sec:
            raise HTTPException(status_code=429, detail="Geocoding rate limited, please retry")
        _last_request_at = now


@router.get("/search", summary="地址搜索（代理 Nominatim）")
def geocoding_search(
    q: str = Query(..., min_length=3, description="搜索关键词，至少 3 个字符"),
    limit: int = Query(5, ge=1, le=10, description="返回条数（默认 5，最大 10）"),
) -> List[Dict[str, Any]]:
    """
    返回结构（精简）：
    - display_name: string
    - lat: number
    - lon: number
    - address: object（可选）
    """
    query = (q or "").strip()
    if len(query) < 3:
        raise HTTPException(status_code=400, detail="Query too short")

    key = (query.lower(), int(limit))
    cached = _get_cached(key)
    if cached is not None:
        return cached

    _enforce_rate_limit()

    url = f"{NOMINATIM_BASE_URL}/search"
    params = {
        "format": "jsonv2",
        "q": query,
        "addressdetails": 1,
        "limit": str(limit),
    }
    # 默认限制在哥伦比亚（可通过环境变量覆盖）
    if NOMINATIM_COUNTRYCODES:
        params["countrycodes"] = NOMINATIM_COUNTRYCODES
    headers = {
        "User-Agent": NOMINATIM_USER_AGENT,
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=8.0, headers=headers) as client:
            resp = client.get(url, params=params)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Nominatim request failed: {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Nominatim error: {resp.status_code}")

    try:
        raw = resp.json()
    except Exception:
        raise HTTPException(status_code=502, detail="Invalid Nominatim response")

    results: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            try:
                lat = float(item.get("lat")) if item.get("lat") is not None else None
                lon = float(item.get("lon")) if item.get("lon") is not None else None
                display_name = item.get("display_name") or ""
                if lat is None or lon is None or not display_name:
                    continue
                results.append(
                    {
                        "display_name": display_name,
                        "lat": lat,
                        "lon": lon,
                        "address": item.get("address") or {},
                    }
                )
            except Exception:
                continue

    _set_cached(key, results)
    return results

