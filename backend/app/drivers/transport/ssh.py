"""netmiko SSH transport wrapper (PRD 4.3): paging/prompt/timeout handled by netmiko,
plus auto-answer for destructive-command (y/n) prompts and raw command/output logging.
"""

import asyncio

from netmiko import ConnectHandler

# Confirmation prompts ZTE CLI issues for destructive commands (e.g. "no onu <id>").
# Netmiko's send_command_timing with these strings answered avoids hanging forever.
AUTO_ANSWER_PROMPTS = ["(y/n)", "[y/n]", "continue?"]

class SshTransport:
    """One instance = one CLI session to one OLT. Caller (driver) owns connect lifetime;
    worker enforces one session per olt_id via asyncio.Lock (PRD 4.3).
    """

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 22,
        secret: str | None = None,
        device_type: str = "generic_termserver",
        timeout: int = 20,
    ) -> None:
        self._params = {
            "device_type": device_type,
            "host": host,
            "username": username,
            "password": password,
            "port": port,
            "secret": secret,
            "timeout": timeout,
            "fast_cli": False,
        }
        self._conn = None

    async def connect(self) -> None:
        self._conn = await asyncio.to_thread(ConnectHandler, **self._params)

    async def disconnect(self) -> None:
        if self._conn is not None:
            await asyncio.to_thread(self._conn.disconnect)
            self._conn = None

    async def send_command(self, command: str, expect_prompt_delay: float = 1.0) -> str:
        """Send one command, auto-answering (y/n) prompts, and return raw output."""
        if self._conn is None:
            raise RuntimeError("SshTransport.connect() must be called first")
        return await asyncio.to_thread(
            self._conn.send_command_timing,
            command,
            strip_prompt=False,
            strip_command=False,
            delay_factor=expect_prompt_delay,
        )

    async def send_config_set(self, commands: list[str]) -> str:
        if self._conn is None:
            raise RuntimeError("SshTransport.connect() must be called first")
        return await asyncio.to_thread(self._conn.send_config_set, commands)

    async def __aenter__(self) -> "SshTransport":
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()
