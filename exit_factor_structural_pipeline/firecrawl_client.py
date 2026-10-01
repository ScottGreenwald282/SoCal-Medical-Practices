"""Firecrawl client. Reads the key from the existing secret file and never logs it."""

from __future__ import annotations

import fcntl
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.firecrawl.dev/v2"
SECRET = Path("/tmp/fc_secret")
SHARED_CACHE = Path("/tmp/fc_cache")
SPENT = SHARED_CACHE / "credits_spent"
CAP = 4000
MIN_GAP = 0.45


class BudgetExhausted(RuntimeError):
    pass


class FirecrawlClient:
    def __init__(self, snapshot_dir: Path) -> None:
        self.snapshot_dir = snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        SHARED_CACHE.mkdir(parents=True, exist_ok=True)
        self.attempted = 0
        self.fetched = 0
        self.credits_observed = 0
        self.started = time.time()

    def _key(self) -> str:
        if not SECRET.exists():
            raise RuntimeError("firecrawl_secret_missing")
        return SECRET.read_text().strip()

    def spent(self) -> int:
        if not SPENT.exists():
            return 0
        try:
            return int(SPENT.read_text() or "0")
        except ValueError:
            return 0

    def _add_spent(self, amount: int) -> None:
        if amount <= 0:
            return
        lock = self._lock()
        try:
            SPENT.write_text(str(self.spent() + amount))
            self.credits_observed += amount
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def _lock(self):
        SHARED_CACHE.mkdir(parents=True, exist_ok=True)
        handle = open(SHARED_CACHE / "lock", "a+")
        fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    def _gap(self) -> None:
        lock = self._lock()
        try:
            last_path = SHARED_CACHE / "last_ts"
            now = time.time()
            prev = 0.0
            if last_path.exists():
                try:
                    prev = float(last_path.read_text() or "0")
                except ValueError:
                    prev = 0.0
            wait = MIN_GAP - (now - prev)
            if wait > 0:
                time.sleep(wait)
            last_path.write_text(str(time.time()))
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()

    def account_remaining(self) -> int | None:
        req = urllib.request.Request(
            API + "/team/credit-usage",
            headers={"Authorization": "Bearer " + self._key()},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
        return (body.get("data") or {}).get("remainingCredits")

    def reconcile(self, baseline_remaining: int, baseline_local: int) -> dict[str, int | None]:
        """Count this task's untracked Firecrawl usage against the shared local cap."""
        remaining = self.account_remaining()
        if remaining is None:
            return {"remaining": None, "local_spent": self.spent()}
        delta = max(0, baseline_remaining - int(remaining))
        target = baseline_local + delta
        if target > self.spent():
            self._add_spent(target - self.spent())
        return {"remaining": int(remaining), "local_spent": self.spent(), "cap": CAP}

    def scrape(self, url: str, actions: list[dict] | None = None, timeout_ms: int = 120000) -> dict:
        payload: dict = {
            "url": url,
            "formats": ["markdown"],
            "onlyMainContent": True,
            "timeout": timeout_ms,
        }
        if actions:
            payload["actions"] = actions
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        path = self.snapshot_dir / f"{digest}.json"
        if path.exists():
            cached = json.loads(path.read_text())
            cached["cached"] = True
            return cached
        if self.spent() >= CAP:
            raise BudgetExhausted(f"local cap {CAP} reached at {self.spent()}")
        self.attempted += 1
        self._gap()
        req = urllib.request.Request(
            API + "/scrape",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": "Bearer " + self._key(),
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=max(60, timeout_ms // 1000 + 30)) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            result = {"ok": False, "error": f"http_{exc.code}", "detail": detail, "digest": digest}
            return result
        data = body.get("data") or {}
        meta = data.get("metadata") or {}
        used = int(body.get("creditsUsed") or meta.get("creditsUsed") or 0)
        self._add_spent(used)
        self.fetched += 1
        result = {"ok": bool(body.get("success")), "credits_used": used, "digest": digest, "body": body}
        path.write_text(json.dumps(result))
        return result


SEARCH_URL = "https://sos.iowa.gov/search/business/Search.aspx"

_NAME_JS = (
    "(function(){ var r=document.querySelector('#searchName'); if(r){r.click();}"
    " var i=document.querySelector('#txtName'); if(i){i.disabled=false; i.focus(); i.value='';}"
    " return i ? 'ok' : 'missing'; })()"
)
_NUM_JS = (
    "(function(){ var r=document.querySelector('#searchBiz'); if(r){r.click();}"
    " var i=document.querySelector('#txtNumber'); if(i){i.disabled=false; i.focus(); i.value='';}"
    " return i ? 'ok' : 'missing'; })()"
)


def name_search_actions(prefix: str) -> list[dict]:
    return [
        {"type": "wait", "milliseconds": 2000},
        {"type": "executeJavascript", "script": _NAME_JS},
        {"type": "write", "text": prefix},
        {"type": "wait", "milliseconds": 300},
        {"type": "click", "selector": "button[name='btnNumber']"},
        {"type": "wait", "milliseconds": 7000},
    ]


def entity_actions(business_no: str) -> list[dict]:
    return [
        {"type": "wait", "milliseconds": 1500},
        {"type": "executeJavascript", "script": _NUM_JS},
        {"type": "write", "text": business_no},
        {"type": "wait", "milliseconds": 300},
        {"type": "click", "selector": "button[name='btnNumber']"},
        {"type": "wait", "milliseconds": 6000},
        {"type": "scrape"},
        {"type": "click", "selector": "a[title='Filings']"},
        {"type": "wait", "milliseconds": 4000},
        {"type": "scrape"},
        {"type": "click", "selector": "a[title='Officers']"},
        {"type": "wait", "milliseconds": 4000},
        {"type": "scrape"},
    ]


def document_actions(business_no: str, cert_no: str) -> list[dict]:
    click = (
        "(function(){ var a=Array.from(document.querySelectorAll('a')).find(function(x){"
        f"return (x.textContent||'').trim()==='{cert_no}';"
        "}); if(!a) return 'missing'; a.click(); return 'clicked'; })()"
    )
    return [
        {"type": "wait", "milliseconds": 1500},
        {"type": "executeJavascript", "script": _NUM_JS},
        {"type": "write", "text": business_no},
        {"type": "wait", "milliseconds": 200},
        {"type": "click", "selector": "button[name='btnNumber']"},
        {"type": "wait", "milliseconds": 5500},
        {"type": "click", "selector": "a[title='Filings']"},
        {"type": "wait", "milliseconds": 3500},
        {"type": "executeJavascript", "script": click},
        {"type": "wait", "milliseconds": 6000},
    ]


def markdown_of(result: dict) -> str:
    data = ((result.get("body") or {}).get("data") or {})
    return data.get("markdown") or ""


def action_scrapes(result: dict) -> list[dict]:
    data = ((result.get("body") or {}).get("data") or {})
    scrapes = ((data.get("actions") or {}).get("scrapes") or [])
    return scrapes if isinstance(scrapes, list) else []
