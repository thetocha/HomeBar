"""Keep one public HTTPS URL alive and point the Telegram menu button at it.

The tunnel is an SSH port forward to localhost.run (lhr.life). That hostname opens
on a phone that is not on the computer's VPN. Cloudflare quick tunnels often do not.
When localhost.run rotates the address, this process updates the bot menu button.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess

from aiogram import Bot

from .bot import setup_menu_button
from .config import ROOT_DIR, settings

logger = logging.getLogger(__name__)

URL_RE = re.compile(r"https://[a-z0-9]+\.lhr\.life")
LOCAL_ORIGIN = "127.0.0.1:8000"


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


async def _publish(url: str, bot: Bot | None) -> None:
    if settings.webapp_url == url:
        return
    settings.webapp_url = url
    _write_env_url(url)
    logger.info("Public menu URL: %s", url)
    if bot is None:
        return
    try:
        await setup_menu_button(bot)
    except Exception:
        logger.exception("Could not point the Telegram menu button at %s", url)


def _ssh_bin() -> str:
    found = shutil.which("ssh")
    if not found:
        raise RuntimeError("OpenSSH client (ssh) was not found on PATH")
    return found


async def _one_session(bot: Bot | None) -> None:
    # Uvicorn's Windows event loop cannot spawn subprocesses, so ssh is
    # started with Popen and watched from a worker thread.
    ssh = await asyncio.to_thread(_ssh_bin)
    proc = await asyncio.to_thread(_spawn, ssh)
    logger.info("Public tunnel started")
    try:
        assert proc.stdout is not None
        while True:
            line = await asyncio.to_thread(proc.stdout.readline)
            if not line:
                break
            text = line.rstrip()
            match = URL_RE.search(text)
            if match:
                await _publish(match.group(0), bot)
            elif text and _worth_logging(text):
                logger.info("tunnel: %s", text[:300])
        code = await asyncio.to_thread(proc.wait)
        logger.warning("Public tunnel exited (%s)", code)
    finally:
        if proc.poll() is None:
            proc.kill()
        await asyncio.to_thread(proc.wait)


def _worth_logging(text: str) -> bool:
    lowered = text.lower()
    if "lhr.life" in lowered:
        return True
    return any(word in lowered for word in ("error", "denied", "refused", "warning", "closed", "timeout"))


def _spawn(ssh: str) -> subprocess.Popen[str]:
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
        creationflags=subprocess.CREATE_NO_WINDOW,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


async def run_tunnel(bot: Bot | None) -> None:
    delay = 3
    while True:
        try:
            await _one_session(bot)
            delay = 3
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Public tunnel failed")
        logger.info("Restarting public tunnel in %s seconds", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
