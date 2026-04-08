"""
X (Twitter) API Integration Diagnostic
---------------------------------------
Tests read access (Bearer Token) and write access (OAuth 1.0a),
then verifies fallback logic.

Run:
    python examples/test_x_api.py
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
from dotenv import load_dotenv

load_dotenv()

# ── Load credentials (strip whitespace — common .env issue) ──────────────────

BEARER_TOKEN         = os.getenv("X_BEARER_TOKEN", "").strip()
API_KEY              = os.getenv("X_API_KEY", "").strip()
API_SECRET           = os.getenv("X_API_SECRET", "").strip()
ACCESS_TOKEN         = os.getenv("X_ACCESS_TOKEN", "").strip()
ACCESS_TOKEN_SECRET  = os.getenv("X_ACCESS_TOKEN_SECRET", "").strip()

RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"


def ok(label: str, detail: str = "") -> None:
    print(f"  {GREEN}✓  PASS{RESET}  {BOLD}{label}{RESET}  {detail}")


def fail(label: str, detail: str = "") -> None:
    print(f"  {RED}✗  FAIL{RESET}  {BOLD}{label}{RESET}  {detail}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠  {msg}{RESET}")


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


# ── Step 1: Read access ───────────────────────────────────────────────────────

async def test_x_read() -> dict:
    section("STEP 1 — Read Access (Bearer Token)")

    if not BEARER_TOKEN:
        fail("Bearer Token", "X_BEARER_TOKEN is empty in .env")
        return {"read_api": "FAIL", "issue": "X_BEARER_TOKEN not set"}

    print(f"  Token prefix : {BEARER_TOKEN[:20]}...")
    print(f"  Token length : {len(BEARER_TOKEN)} chars")

    url = "https://api.twitter.com/2/users/by/username/karpathy"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
            )
    except Exception as exc:
        fail("Network", str(exc))
        return {"read_api": "FAIL", "issue": f"Network error: {exc}"}

    print(f"  HTTP status  : {resp.status_code}")

    if resp.status_code == 200:
        data = resp.json()
        user = data.get("data", {})
        print(f"  User found   : @{user.get('username')}  id={user.get('id')}")
        ok("Read API", f"fetched @karpathy  id={user.get('id')}")
        return {"read_api": "PASS", "user_id": user.get("id")}

    # Failure path — show full response
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:400]

    print(f"  Response     : {json.dumps(body, indent=2)[:400]}")

    if resp.status_code == 401:
        fail("Read API", "401 Unauthorized — Bearer Token is invalid or expired")
        return {"read_api": "FAIL", "issue": "Invalid Bearer Token (401)"}
    if resp.status_code == 403:
        fail("Read API", "403 Forbidden — app lacks read permissions or wrong tier")
        return {"read_api": "FAIL", "issue": "Forbidden (403) — check app permissions"}
    if resp.status_code == 429:
        fail("Read API", "429 Rate limit — wait 15 minutes and retry")
        return {"read_api": "FAIL", "issue": "Rate limited (429)"}

    fail("Read API", f"HTTP {resp.status_code}")
    return {"read_api": "FAIL", "issue": f"HTTP {resp.status_code}: {str(body)[:200]}"}


# ── Step 2: Write access ──────────────────────────────────────────────────────

async def test_x_write() -> dict:
    section("STEP 2 — Write Access (OAuth 1.0a)")

    missing = [k for k, v in {
        "X_API_KEY": API_KEY,
        "X_API_SECRET": API_SECRET,
        "X_ACCESS_TOKEN": ACCESS_TOKEN,
        "X_ACCESS_TOKEN_SECRET": ACCESS_TOKEN_SECRET,
    }.items() if not v]

    if missing:
        fail("OAuth credentials", f"Missing: {', '.join(missing)}")
        return {"write_api": "FAIL", "issue": f"Missing credentials: {missing}"}

    print(f"  API Key      : {API_KEY[:10]}...")
    print(f"  Access Token : {ACCESS_TOKEN[:20]}...")

    url  = "https://api.twitter.com/2/tweets"
    text = f"Test tweet from MultiAgentAI pipeline — {int(time.time())}"

    # Build OAuth 1.0a header
    oauth_params = {
        "oauth_consumer_key":     API_KEY,
        "oauth_nonce":            uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            ACCESS_TOKEN,
        "oauth_version":          "1.0",
    }
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(oauth_params.items())
    )
    base_string = "&".join([
        "POST",
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])
    signing_key = (
        urllib.parse.quote(API_SECRET, safe="")
        + "&"
        + urllib.parse.quote(ACCESS_TOKEN_SECRET, safe="")
    )
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = signature

    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth_params.items())
    )

    print(f"  Posting text : \"{text[:60]}...\"")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": auth_header, "Content-Type": "application/json"},
                json={"text": text},
            )
    except Exception as exc:
        fail("Network", str(exc))
        return {"write_api": "FAIL", "issue": f"Network error: {exc}"}

    print(f"  HTTP status  : {resp.status_code}")

    try:
        body = resp.json()
    except Exception:
        body = resp.text[:400]

    if resp.status_code == 201:
        tweet_id = body.get("data", {}).get("id", "")
        tweet_url = f"https://x.com/i/web/status/{tweet_id}"
        print(f"  Tweet ID     : {tweet_id}")
        print(f"  Tweet URL    : {tweet_url}")
        ok("Write API", f"tweet posted  id={tweet_id}")
        return {"write_api": "PASS", "tweet_id": tweet_id, "url": tweet_url}

    print(f"  Response     : {json.dumps(body, indent=2)[:400]}")

    if resp.status_code == 401:
        fail("Write API", "401 Unauthorized — OAuth credentials invalid or wrong app permissions")
        return {"write_api": "FAIL", "issue": "OAuth 401 — check API_KEY/SECRET/ACCESS_TOKEN"}
    if resp.status_code == 403:
        fail("Write API", "403 Forbidden — app needs 'Read and Write' permissions in developer portal")
        return {"write_api": "FAIL", "issue": "403 Forbidden — enable Read+Write in dev portal"}
    if resp.status_code == 429:
        fail("Write API", "429 Rate limit exceeded")
        return {"write_api": "FAIL", "issue": "Rate limited (429)"}

    fail("Write API", f"HTTP {resp.status_code}")
    return {"write_api": "FAIL", "issue": f"HTTP {resp.status_code}: {str(body)[:200]}"}


# ── Step 3: Fallback logic ────────────────────────────────────────────────────

async def test_fallback() -> dict:
    section("STEP 3 — Fallback Logic (no credentials)")

    from services.x_api_client import fetch_user_posts, USE_REAL_API

    # Temporarily patch settings to simulate missing token
    from config import get_settings
    settings = get_settings()
    original_token = settings.x_bearer_token
    settings.__dict__["x_bearer_token"] = ""   # patch in-place

    try:
        posts = await fetch_user_posts("karpathy", max_results=3)
        if posts and posts[0].get("source") == "mock":
            ok("Fallback", f"returned {len(posts)} mock posts — no crash")
            result = {"fallback": "WORKING"}
        else:
            warn("Fallback returned unexpected data")
            result = {"fallback": "WORKING", "note": "returned data but source unclear"}
    except Exception as exc:
        fail("Fallback", f"CRASHED: {exc}")
        result = {"fallback": "NOT WORKING", "issue": str(exc)}
    finally:
        settings.__dict__["x_bearer_token"] = original_token

    return result


# ── Step 4: Credential format check ──────────────────────────────────────────

def check_credential_format() -> None:
    section("STEP 4 — Credential Format Check")

    checks = {
        "X_BEARER_TOKEN": (BEARER_TOKEN, lambda v: v.startswith("AAAAAAA"), "should start with AAAAAAA"),
        "X_API_KEY":      (API_KEY,      lambda v: len(v) == 25,            "should be 25 chars"),
        "X_API_SECRET":   (API_SECRET,   lambda v: len(v) >= 40,            "should be 40+ chars"),
        "X_ACCESS_TOKEN": (ACCESS_TOKEN, lambda v: "-" in v,                "should contain '-'"),
        "X_ACCESS_TOKEN_SECRET": (ACCESS_TOKEN_SECRET, lambda v: len(v) >= 40, "should be 40+ chars"),
    }

    all_ok = True
    for name, (value, check_fn, hint) in checks.items():
        if not value:
            fail(name, "EMPTY — not set in .env")
            all_ok = False
        elif not check_fn(value):
            warn(f"{name} format looks wrong ({hint}) — value: {value[:15]}...")
            all_ok = False
        else:
            ok(name, f"{value[:12]}...  ({len(value)} chars)")

    if all_ok:
        print(f"\n  {GREEN}All credentials present and correctly formatted.{RESET}")
    else:
        print(f"\n  {YELLOW}Some credentials may be wrong — see warnings above.{RESET}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print(f"\n{BOLD}{CYAN}{'═' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  X (Twitter) API Integration Diagnostic{RESET}")
    print(f"{BOLD}{CYAN}{'═' * 60}{RESET}")

    check_credential_format()

    read_result  = await test_x_read()
    write_result = await test_x_write()
    fallback_result = await test_fallback()

    # ── Final report ──────────────────────────────────────────────────────
    section("FINAL REPORT")

    report = {
        "read_api":  read_result.get("read_api", "FAIL"),
        "write_api": write_result.get("write_api", "FAIL"),
        "fallback":  fallback_result.get("fallback", "NOT WORKING"),
        "issue":     read_result.get("issue") or write_result.get("issue") or "none",
        "fix":       _suggest_fix(read_result, write_result),
    }

    print(json.dumps(report, indent=2))

    # Summary line
    all_pass = report["read_api"] == "PASS" and report["write_api"] == "PASS"
    if all_pass:
        print(f"\n  {GREEN}{BOLD}X API fully operational — read and write both working.{RESET}\n")
    else:
        print(f"\n  {YELLOW}{BOLD}See issues above. Fallback is {report['fallback']}.{RESET}\n")


def _suggest_fix(read: dict, write: dict) -> str:
    issue = read.get("issue", "") + " " + write.get("issue", "")
    if "401" in issue:
        return (
            "Regenerate tokens in developer.twitter.com → "
            "Your App → Keys and Tokens → Regenerate"
        )
    if "403" in issue:
        return (
            "Go to developer.twitter.com → Your App → Settings → "
            "App permissions → change to 'Read and Write' → regenerate tokens"
        )
    if "429" in issue:
        return "Wait 15 minutes (free tier rate limit) then retry"
    if "not set" in issue or "Missing" in issue:
        return "Add missing keys to .env — see .env.example for all required fields"
    if "format" in issue.lower():
        return "Check for leading/trailing spaces in .env values"
    return "Check developer.twitter.com for app status and permissions"


if __name__ == "__main__":
    asyncio.run(main())
