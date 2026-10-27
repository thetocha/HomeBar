"""Keep one public HTTPS URL alive and point the Telegram menu button at it.

Prefers a Cloudflare quick tunnel when ``cloudflared`` is on PATH. That hostname stays
put for the life of the process. localhost.run is the fallback, but it sometimes
prints a new hostname and immediately 502s the previous one, which breaks an open
Mini App. A watchdog restarts the tunnel only after repeated failed health checks.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import signal
import subprocess
import urllib.error
import urllib.request
from typing import Literal

from aiogram import Bot

from .bot import setup_menu_button, setup_webhook
from .config import ROOT_DIR, settings

logger = logging.getLogger(__name__)

LOCALHOST_URL_RE = re.compile(r"https://[a-z0-9]+\.lhr\.life")
CLOUDFLARE_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
LOCAL_ORIGIN = "127.0.0.1:8000"

TunnelProvider = Literal["auto", "cloudflare", "localhost"]
SessionState = dict[str, subprocess.Popen[str] | str | bool | None]
WATCH_INTERVAL_SECONDS = 25
HEALTH_TIMEOUT_SECONDS = 12
# One 502 from the tunnel edge is common. Restart only when several probes fail.
HEALTH_PROBES = 3
HEALTH_PROBE_GAP_SECONDS = 2
CLOUDFLARE_PUBLISH_TIMEOUT_SECONDS = 45


def _stop_stray_tunnels() -> None:
    """Only one tunnel client may forward port 8000."""
    patterns = (
        "cloudflared tunnel --url",
        "ssh -n -T -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30",
        "nokey@localhost.run",
    )
    for pattern in patterns:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, check=False)
        for token in result.stdout.split():
            if not token.isdigit():
                continue
            try:
                os.kill(int(token), signal.SIGTERM)
            except ProcessLookupError:
                continue


def _write_env_url(url: str) -> None:
    path = ROOT_DIR / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    except OSError:
        logger.warning("Could not read .env to store the public URL")
        return
    found = False
    updated: list[str] = []
    for line in lines:
        if line.startswith("WEBAPP_URL="):
            updated.append(f"WEBAPP_URL={url}")
            found = True
        else:
            updated.append(line)
    if not found:
        updated.append(f"WEBAPP_URL={url}")
    try:
        path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    except OSError:
        logger.warning("Could not write the public URL into .env")


def _verify_public(url: str) -> bool:
    health = f"{url.rstrip('/')}/api/health"
    request = urllib.request.Request(health, headers={"User-Agent": "homebar-tunnel-watchdog/1"})
    try:
        with urllib.request.urlopen(request, timeout=HEALTH_TIMEOUT_SECONDS) as response:
            body = response.read(200).decode("utf-8", errors="replace")
            return response.status == 200 and '"ok"' in body
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


async def _publish(
    url: str,
    bot: Bot | None,
    session: SessionState,
) -> None:
    if settings.webapp_url == url and session.get("published_url") == url:
        return
    settings.webapp_url = url
    session["published_url"] = url
    session["ever_published"] = True
    _write_env_url(url)
    logger.info("Public menu URL: %s", url)
    if bot is None:
        return
    try:
        await setup_menu_button(bot)
        if settings.use_webhook_updates():
            await setup_webhook(bot)
    except Exception:
        logger.exception("Could not point the Telegram menu button at %s", url)


async def _publish_if_healthy(
    url: str,
    bot: Bot | None,
    session: SessionState,
) -> bool:
    # localhost.run can announce a second hostname while the first one still
    # serves. Publishing the new one 502s anyone who already has the menu open.
    current = session.get("published_url")
    if isinstance(current, str) and current and current != url:
        if await asyncio.to_thread(_verify_public, current):
            if session.get("pending_url") != url:
                logger.info("Keeping public URL %s; ignoring %s while it still responds", current, url)
            session["pending_url"] = url
            return True
    if session.get("last_candidate") == url:
        return bool(session.get("published_url") == url)
    session["last_candidate"] = url
    await asyncio.sleep(5)
    for attempt in range(15):
        if await asyncio.to_thread(_verify_public, url):
            await _publish(url, bot, session)
            return True
        if attempt < 14:
            await asyncio.sleep(2)
    logger.warning("Tunnel URL never became healthy, skipping publish: %s", url)
    return False


def _resolve_provider() -> TunnelProvider:
    raw = (settings.tunnel_provider or "auto").strip().lower()
    if raw == "localhost":
        return "localhost"
    # Cloudflare keeps one hostname until the process exits. localhost.run
    # sometimes replaces the hostname and 502s the previous address.
    if raw == "cloudflare" or shutil.which("cloudflared"):
        return "cloudflare"
    return "localhost"


def _ssh_bin() -> str:
    found = shutil.which("ssh")
    if not found:
        raise RuntimeError("OpenSSH client (ssh) was not found on PATH")
    return found


def _cloudflared_bin() -> str:
    found = shutil.which("cloudflared")
    if not found:
        raise RuntimeError("cloudflared was not found on PATH")
    return found


def _worth_logging(text: str) -> bool:
    lowered = text.lower()
    if "lhr.life" in lowered or "trycloudflare.com" in lowered:
        return True
    return any(word in lowered for word in ("error", "denied", "refused", "warning", "closed", "timeout", "failed"))


def _spawn_localhost(ssh: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            ssh,
            "-n",
            "-T",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "ExitOnForwardFailure=yes",
            "-R",
            f"80:{LOCAL_ORIGIN}",
            "nokey@localhost.run",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _spawn_cloudflare(cloudflared: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            cloudflared,
            "tunnel",
            "--url",
            f"http://{LOCAL_ORIGIN}",
            "--no-autoupdate",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        text=True,
        encoding="utf-8",
        errors="replace",
    )


async def _read_tunnel_stream(
    proc: subprocess.Popen[str],
    bot: Bot | None,
    url_pattern: re.Pattern[str],
    session: SessionState,
) -> None:
    assert proc.stdout is not None
    while True:
        line = await asyncio.to_thread(proc.stdout.readline)
        if not line:
            break
        text = line.rstrip()
        match = url_pattern.search(text)
        if match:
            await _publish_if_healthy(match.group(0), bot, session)
        elif text and _worth_logging(text):
            logger.info("tunnel: %s", text[:300])


async def _localhost_session(
    bot: Bot | None,
    session: SessionState,
) -> None:
    ssh = await asyncio.to_thread(_ssh_bin)
    proc = await asyncio.to_thread(_spawn_localhost, ssh)
    session["proc"] = proc
    logger.info("Public tunnel started (localhost.run)")
    try:
        await _read_tunnel_stream(proc, bot, LOCALHOST_URL_RE, session)
        code = await asyncio.to_thread(proc.wait)
        logger.warning("Public tunnel exited (%s)", code)
    finally:
        session["proc"] = None
        if proc.poll() is None:
            proc.kill()
        await asyncio.to_thread(proc.wait)


async def _cloudflare_session(
    bot: Bot | None,
    session: SessionState,
) -> None:
    cloudflared = await asyncio.to_thread(_cloudflared_bin)
    proc = await asyncio.to_thread(_spawn_cloudflare, cloudflared)
    session["proc"] = proc
    logger.info("Public tunnel started (Cloudflare quick tunnel)")
    try:
        await _read_tunnel_stream(proc, bot, CLOUDFLARE_URL_RE, session)
        code = await asyncio.to_thread(proc.wait)
        logger.warning("Public tunnel exited (%s)", code)
    finally:
        session["proc"] = None
        if proc.poll() is None:
            proc.kill()
        await asyncio.to_thread(proc.wait)


async def _is_healthy(url: str) -> bool:
    for attempt in range(HEALTH_PROBES):
        if await asyncio.to_thread(_verify_public, url):
            return True
        if attempt + 1 < HEALTH_PROBES:
            await asyncio.sleep(HEALTH_PROBE_GAP_SECONDS)
    return False


async def _watchdog(bot: Bot | None, session: SessionState) -> None:
    while True:
        await asyncio.sleep(WATCH_INTERVAL_SECONDS)
        url_raw = session.get("published_url")
        if not isinstance(url_raw, str) or not url_raw.strip():
            continue
        url = url_raw.strip()
        if await _is_healthy(url):
            continue
        pending = session.get("pending_url")
        if isinstance(pending, str) and pending.strip() and pending != url:
            if await asyncio.to_thread(_verify_public, pending):
                logger.warning("Public URL failed health check, switching to %s", pending)
                await _publish(pending, bot, session)
                session["pending_url"] = None
                continue
        logger.warning("Public URL failed health check, restarting tunnel: %s", url)
        proc = session.get("proc")
        if isinstance(proc, subprocess.Popen) and proc.poll() is None:
            proc.kill()
            try:
                await asyncio.to_thread(proc.wait, timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        session["published_url"] = None
        return


async def _run_session(
    bot: Bot | None,
    provider: TunnelProvider,
    *,
    publish_timeout: float | None,
) -> bool:
    session: SessionState = {
        "proc": None,
        "published_url": None,
        "last_candidate": None,
        "pending_url": None,
        "ever_published": False,
    }
    session_factory = _cloudflare_session if provider == "cloudflare" else _localhost_session
    try:
        session_task = asyncio.create_task(session_factory(bot, session))
        watchdog_task = asyncio.create_task(_watchdog(bot, session))
        try:
            if publish_timeout is None:
                await session_task
            else:
                loop = asyncio.get_running_loop()
                deadline = loop.time() + publish_timeout
                while not session_task.done():
                    if session.get("ever_published"):
                        await session_task
                        break
                    remaining = deadline - loop.time()
                    if remaining <= 0:
                        logger.warning("%s tunnel produced no healthy URL", provider)
                        proc = session.get("proc")
                        if isinstance(proc, subprocess.Popen) and proc.poll() is None:
                            proc.kill()
                        await session_task
                        break
                    await asyncio.wait({session_task}, timeout=min(1.0, remaining))
                if session_task.done():
                    await session_task
        finally:
            watchdog_task.cancel()
            try:
                await watchdog_task
            except asyncio.CancelledError:
                pass
    except Exception:
        logger.exception("%s tunnel failed", provider)
    return bool(session.get("ever_published"))


async def _one_cycle(bot: Bot | None) -> None:
    await asyncio.to_thread(_stop_stray_tunnels)
    await asyncio.sleep(1)
    provider = _resolve_provider()
    published = await _run_session(
        bot,
        provider,
        publish_timeout=CLOUDFLARE_PUBLISH_TIMEOUT_SECONDS if provider == "cloudflare" else None,
    )
    if provider == "cloudflare" and not published:
        logger.warning("Cloudflare tunnel was not usable; falling back to localhost.run")
        await asyncio.to_thread(_stop_stray_tunnels)
        await asyncio.sleep(1)
        await _run_session(bot, "localhost", publish_timeout=None)


async def run_tunnel(bot: Bot | None) -> None:
    delay = 3
    while True:
        try:
            await _one_cycle(bot)
            delay = 3
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Public tunnel failed")
        logger.info("Restarting public tunnel in %s seconds", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
