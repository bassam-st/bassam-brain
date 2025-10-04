# core/search_web.py — وحدة البحث في الويب
import httpx, asyncio

async def web_search(query: str, max_results: int = 8):
    url = f"https://ddg-api.herokuapp.com/search?max={max_results}&q={query}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code == 200:
                return r.json().get("results", [])
    except Exception:
        pass
    return []
