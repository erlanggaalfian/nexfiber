"""netmiko Telnet transport wrapper. Same interface as SshTransport so drivers pick a
transport based on `olts.cli_protocol` without branching their own command logic.

Prompt konfirmasi ditangani di level driver, bukan di sini (lihat ssh.py dan
`zte_c320._send_config`): tidak ada auto-answer "y" diam-diam.
"""

import asyncio

from netmiko import ConnectHandler


class TelnetTransport:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 23,
        secret: str | None = None,
        device_type: str = "generic_termserver_telnet",
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
        if self._conn is None:
            raise RuntimeError("TelnetTransport.connect() must be called first")
        return await asyncio.to_thread(
            self._conn.send_command_timing,
            command,
            strip_prompt=False,
            strip_command=False,
            delay_factor=expect_prompt_delay,
        )

    async def show(self, command: str, read_timeout: float = 60) -> str:
        """Perintah baca-saja: menunggu prompt OLT (cepat), bukan jeda tetap.

        Tidak menjawab (y/n) otomatis; jangan dipakai untuk perintah yang mengubah config.
        """
        if self._conn is None:
            raise RuntimeError("connect() must be called first")
        return await asyncio.to_thread(
            self._conn.send_command, command,
            strip_prompt=False, strip_command=False, read_timeout=read_timeout,
        )

    async def send_config_set(self, commands: list[str]) -> str:
        if self._conn is None:
            raise RuntimeError("TelnetTransport.connect() must be called first")
        return await asyncio.to_thread(self._conn.send_config_set, commands)

    async def __aenter__(self) -> "TelnetTransport":
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.disconnect()
