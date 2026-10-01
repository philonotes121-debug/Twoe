"""Read-only Notion sync for CA Tracker Pro, plus optional access-event sync."""
import logging
from typing import Any
import aiohttp
import config

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return bool(config.NOTION_API_TOKEN)


def _value(prop: dict) -> str:
    typ=prop.get("type")
    if typ=="title": return "".join(x.get("plain_text","") for x in prop.get("title",[]))
    if typ=="rich_text": return "".join(x.get("plain_text","") for x in prop.get("rich_text",[]))
    if typ in ("select","status"):
        return (prop.get(typ) or {}).get("name","")
    if typ=="multi_select": return ", ".join(x.get("name","") for x in prop.get("multi_select",[]))
    if typ=="url": return prop.get("url") or ""
    if typ=="date": return (prop.get("date") or {}).get("start","")
    if typ=="number": return str(prop.get("number")) if prop.get("number") is not None else ""
    if typ=="checkbox": return "yes" if prop.get("checkbox") else "no"
    if typ=="formula":
        f=prop.get("formula",{}); return str(f.get(f.get("type"),""))
    return ""


def normalize_page(item: dict, source: str) -> dict:
    props=item.get("properties") or {}
    vals={}
    for name,p in props.items(): vals[name]=_value(p)
    def pick(*names):
        low={k.lower().replace("_"," "):v for k,v in vals.items()}
        for n in names:
            v=low.get(n.lower().replace("_"," "))
            if v: return v
        return ""
    return {
        "id": item.get("id"), "url": item.get("url") or "",
        "source": pick("source","publication","newspaper","publisher") or source,
        "title": pick("title","name","headline","article") or "Untitled",
        "summary": pick("summary","editorial summary","brief","content","notes"),
        "content_type": pick("type","content type","category"),
        "date": pick("date","published","edition"),
        "topic": pick("topic","topics","subject"),
        "tags": pick("tags","tag","keywords"),
        "location": pick("place in news","location","place"),
        "organisation": pick("international organisation","organisation","organization"),
        "language": pick("language","medium"),
    }


async def _query(source_id: str, source_name: str, filters: dict|None=None) -> list[dict]:
    if not source_id or not enabled(): return []
    headers={"Authorization":f"Bearer {config.NOTION_API_TOKEN}","Notion-Version":config.NOTION_VERSION,"Content-Type":"application/json"}
    payload={"page_size":100}
    if filters: payload["filter"]={"property":filters["property"],"select":{"equals":filters["value"]}}
    out=[]; cursor=None
    async with aiohttp.ClientSession(headers=headers) as session:
        for _ in range(10):
            body=dict(payload)
            if cursor: body["start_cursor"]=cursor
            url=f"https://api.notion.com/v1/data_sources/{source_id}/query"
            async with session.post(url,json=body,timeout=20) as resp:
                if resp.status==404:
                    url=f"https://api.notion.com/v1/databases/{source_id}/query"
                    async with session.post(url,json=body,timeout=20) as resp2:
                        if resp2.status>=400: return out
                        data=await resp2.json()
                elif resp.status>=400:
                    return out
                else:
                    data=await resp.json()
            out.extend(normalize_page(x,source_name) for x in data.get("results",[]))
            if not data.get("has_more"): break
            cursor=data.get("next_cursor")
    return out


async def get_ca_items(filters: dict|None=None) -> list[dict]:
    datasets=[
        (config.NOTION_CA_SOURCE_ID,"Daily Current Affairs"),
        (config.NOTION_EDITORIAL_SOURCE_ID,"Editorial"),
        (config.NOTION_PLACE_NEWS_SOURCE_ID,"Place in News"),
        (config.NOTION_INTERNATIONAL_ORGS_SOURCE_ID,"International Organisations"),
    ]
    out=[]
    for sid,name in datasets:
        out.extend(await _query(sid,name))
    # Separate client-side filters permit independent source/category/topic filters.
    if filters:
        q=str(filters.get("q") or "").lower().strip()
        if q:
            out=[x for x in out if any(q in str(x.get(k,"")).lower() for k in ("title","summary","topic","tags","location","organisation"))]
        for key,val in filters.items():
            if key=="q" or val in (None,"", "all"): continue
            v=str(val).lower()
            out=[x for x in out if v in str(x.get(key,"")).lower() or v in str(x.get("tags","")).lower()]
    return out[:500]


async def sync_access_event(user_id:int, plan:str, status:str) -> bool:
    """Optional write; only attempts when an access data-source is configured."""
    if not config.NOTION_ACCESS_SOURCE_ID or not enabled(): return False
    headers={"Authorization":f"Bearer {config.NOTION_API_TOKEN}","Notion-Version":config.NOTION_VERSION,"Content-Type":"application/json"}
    # Keep this deliberately schema-light: a title property is the only common requirement.
    body={"parent":{"data_source_id":config.NOTION_ACCESS_SOURCE_ID},"properties":{"Name":{"title":[{"text":{"content":f"{user_id}:{plan}:{status}"}}]}}}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post("https://api.notion.com/v1/pages",json=body,timeout=20) as resp:
                return resp.status < 300
    except Exception:
        logger.exception("Notion access sync failed")
        return False

async def notion_health() -> str:
    configured = [
        ("CA", config.NOTION_CA_SOURCE_ID),
        ("Editorial", config.NOTION_EDITORIAL_SOURCE_ID),
        ("Place in News", config.NOTION_PLACE_NEWS_SOURCE_ID),
        ("International Organisations", config.NOTION_INTERNATIONAL_ORGS_SOURCE_ID),
        ("Access", config.NOTION_ACCESS_SOURCE_ID),
    ]
    ready=[name for name,sid in configured if sid]
    return "Configured datasets: " + (", ".join(ready) if ready else "none")


async def get_ca_dataset(dataset: str, filters: dict|None=None) -> list[dict]:
    mapping={
        "daily": (config.NOTION_CA_SOURCE_ID,"Daily Current Affairs"),
        "editorial": (config.NOTION_EDITORIAL_SOURCE_ID,"Editorial"),
        "place_news": (config.NOTION_PLACE_NEWS_SOURCE_ID,"Place in News"),
        "international": (config.NOTION_INTERNATIONAL_ORGS_SOURCE_ID,"International Organisations"),
    }
    sid,name=mapping.get(dataset,("",dataset))
    if not sid or not enabled(): return []
    rows=await _query(sid,name)
    if not filters: return rows[:500]
    q=str(filters.get("q") or "").lower().strip()
    for key,val in filters.items():
        if key=="q" or not val: continue
        vv=str(val).lower()
        rows=[x for x in rows if vv in str(x.get(key,"")).lower() or vv in str(x.get("tags","")).lower()]
    if q:
        rows=[x for x in rows if any(q in str(x.get(k,"")).lower() for k in ("title","summary","topic","tags","location","organisation"))]
    return rows[:500]
