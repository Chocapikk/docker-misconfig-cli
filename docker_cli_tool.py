#!/usr/bin/env python3
"""
Interactive Docker CLI supporting Unix socket or HTTP(S) endpoints.
Features:
 - prompt_toolkit for interactive REPL with command history
 - rich for formatted output
 - rich_click for a modern, typed CLI interface
 - requests for HTTP(S) API calls with SSL warnings suppressed
"""
from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests
import rich_click as rc
import urllib3
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.table import Table

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

console = Console()


@dataclass
class DockerConfig:
    url: Optional[str] = None
    socket_path: str = "/var/run/docker.sock"


class DockerClient:
    def __init__(self, config: DockerConfig) -> None:
        self.config = config
        if config.url:
            base = config.url
            if not base.startswith(("http://", "https://")):
                base = "http://" + base
            self.base_url = base.rstrip("/")
            self.use_http = True
        else:
            self.socket_path = config.socket_path
            self.use_http = False

    def _raw_request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """Perform the raw HTTP or Unix‐socket request and return raw body bytes."""
        if self.use_http:
            resp = requests.request(
                method, f"{self.base_url}{path}", json=payload, timeout=10, verify=False
            )
            return resp.status_code, resp.reason, resp.content

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(self.socket_path)
            hdr = f"{method} {path} HTTP/1.1\r\nHost: docker\r\n"
            body = b""
            if payload is not None:
                body = json.dumps(payload).encode()
                hdr += (
                    f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n"
                )
            hdr += "\r\n"
            sock.sendall(hdr.encode() + body)
            sock.settimeout(1.0)
            data = bytearray()
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data.extend(chunk)
                except socket.timeout:
                    break

        idxs = [i for i in (data.find(b"["), data.find(b"{")) if i != -1]
        if idxs:
            return 200, "OK", data[min(idxs) :]
        _, _, body = data.partition(b"\r\n\r\n")
        return 200, "OK", body

    def _call(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]],
        expected_codes: Tuple[int, ...],
    ) -> Optional[bytes]:
        status, reason, body = self._raw_request(method, path, payload)
        if status not in expected_codes:
            console.print(f"[red]Error {method} {path}: HTTP {status} {reason}[/red]")
            if body.strip():
                console.print(body.decode(errors="ignore"))
            return None
        return body

    def list_containers(self) -> List[Dict[str, Any]]:
        """Fetch and display list of containers."""
        raw = self._call("GET", "/containers/json", None, (200,))
        if not raw:
            return []

        text = raw.decode(errors="ignore")
        try:
            decoder = json.JSONDecoder()
            containers, _ = decoder.raw_decode(text)
        except json.JSONDecodeError as e:
            console.print(f"[red]JSON parse error: {e}[/red]")
            console.print(text)
            return []

        table = Table(title="Docker Containers")
        table.add_column("Idx", justify="right")
        table.add_column("ID", style="cyan")
        table.add_column("Names", style="green")
        for idx, ctr in enumerate(containers):
            table.add_row(str(idx), ctr["Id"][:12], ",".join(ctr.get("Names", [])))
        console.print(table)
        return containers

    def exec_command(self, container_id: str, cmd: List[str]) -> None:
        exec_payload = {
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": False,
            "Cmd": cmd,
        }
        body = self._call(
            "POST", f"/containers/{container_id}/exec", exec_payload, (200, 201)
        )
        if body is None:
            return

        exec_id = json.loads(body).get("Id")
        start_payload = {"Detach": False, "Tty": False}
        output = self._call("POST", f"/exec/{exec_id}/start", start_payload, (200, 101))
        if output:
            console.print(output.decode(errors="ignore"))


class DockerShell:
    def __init__(
        self, client: DockerClient, history_file: str = "~/.docker_cli_history"
    ) -> None:
        self.client = client
        path = os.path.expanduser(history_file)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.session = PromptSession(history=FileHistory(path))

    def run(self) -> None:
        containers = self.client.list_containers()
        if not containers:
            return

        max_idx = len(containers) - 1
        idx = int(self.session.prompt(f"Select container [0-{max_idx}]: ") or "0")
        cid = containers[idx]["Id"][:12]
        console.print(f"[bold]Selected:[/bold] {cid}")

        commands: List[str] = ["ls", "cat", "exit", "quit"]
        completer = WordCompleter(commands, ignore_case=True)

        while True:
            line = self.session.prompt(f"{cid}> ", completer=completer).strip()
            if line in ("exit", "quit"):
                console.print("Exiting shell")
                break

            parts = line.split()
            self.client.exec_command(cid, parts)

            root = parts[0]
            if root not in commands:
                commands.append(root)
                completer = WordCompleter(commands, ignore_case=True)
                self.session.completer = completer


@rc.command("Docker Shell CLI with prompt history and rich output.")
@rc.option(
    "-u",
    "--url",
    default=None,
    help="Docker API endpoint e.g. http://host:2375 or https://host:2376",
)
@rc.option(
    "-s", "--socket", "socket_path", default=None, help="Path to Docker Unix socket"
)
def main(
    url: Optional[str] = None,
    socket_path: Optional[str] = None,
) -> None:
    if (url is None and socket_path is None) or (
        url is not None and socket_path is not None
    ):
        raise rc.UsageError("Must specify exactly one of --url or --socket")

    if url:
        console.print(f"[green]Using HTTP API at[/green] {url}")
        cfg = DockerConfig(url=url, socket_path="")
    else:
        path = socket_path
        console.print(f"[green]Using Unix socket at[/green] {path}")
        cfg = DockerConfig(url=None, socket_path=path)

    client = DockerClient(cfg)
    DockerShell(client).run()


if __name__ == "__main__":
    main()
