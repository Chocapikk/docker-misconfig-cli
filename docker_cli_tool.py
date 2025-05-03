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
    """Configuration for Docker connection."""

    url: Optional[str] = None
    socket_path: str = "/var/run/docker.sock"


class DockerClient:
    """Client to interact with Docker via HTTP(S) or Unix socket."""

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

    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, str, bytes]:
        """
        Send request via HTTP or Unix socket and return (status, reason, body).
        """
        if self.use_http:
            url = f"{self.base_url}{path}"
            try:
                resp = requests.request(
                    method=method,
                    url=url,
                    json=payload,
                    timeout=10,
                    verify=False,
                )
                return resp.status_code, resp.reason, resp.content
            except requests.RequestException as e:
                console.print(f"[red]HTTP request failed:[/red] {e}")
                return 0, str(e), b""

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(self.socket_path)
            header = f"{method} {path} HTTP/1.1\r\nHost: docker\r\n"
            body = b""
            if payload is not None:
                body = json.dumps(payload).encode()
                header += (
                    f"Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                )
            header += "\r\n"
            sock.sendall(header.encode() + body)
            sock.settimeout(1.0)
            data = bytearray()
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data.extend(chunk)
            except socket.timeout:
                pass

        _, _, raw_body = data.partition(b"\r\n\r\n")
        return 200, "OK", raw_body

    def list_containers(self) -> List[Dict[str, Any]]:
        """Fetch and display list of containers."""
        status, reason, content = self._request("GET", "/containers/json")
        if status != 200:
            console.print(f"[red]Failed to list containers {status} {reason}[/red]")
            return []
        try:
            containers = json.loads(content)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON response[/red]")
            return []

        table = Table(title="Docker Containers")
        table.add_column("Idx", justify="right")
        table.add_column("ID", style="cyan")
        table.add_column("Names", style="green")
        for idx, ctr in enumerate(containers):
            names = ",".join(ctr.get("Names", []))
            table.add_row(str(idx), ctr["Id"][:12], names)
        console.print(table)
        return containers

    def exec_command(self, container_id: str, cmd: List[str]) -> None:
        """Run a command inside container and print output."""
        exec_payload = {
            "AttachStdout": True,
            "AttachStderr": True,
            "Tty": False,
            "Cmd": cmd,
        }
        status, reason, data = self._request(
            "POST", f"/containers/{container_id}/exec", payload=exec_payload
        )
        if status not in (200, 201):
            console.print(f"[red]Exec creation failed {status} {reason}[/red]")
            return

        exec_id = json.loads(data).get("Id")
        start_payload = {"Detach": False, "Tty": False}
        status, reason, output = self._request(
            "POST", f"/exec/{exec_id}/start", payload=start_payload
        )
        if status not in (200, 101):
            console.print(f"[red]Exec start failed {status} {reason}[/red]")
            return

        console.print(output.decode(errors="ignore"))


class DockerShell:
    """Interactive shell for Docker commands."""

    def __init__(
        self, client: DockerClient, history_file: str = "~/.docker_cli_history"
    ) -> None:
        self.client = client

        history_path = os.path.expanduser(history_file)
        history_dir = os.path.dirname(history_path)
        if history_dir and not os.path.exists(history_dir):
            os.makedirs(history_dir, exist_ok=True)
        self.session = PromptSession(history=FileHistory(history_path))

    def run(self) -> None:
        containers = self.client.list_containers()
        if not containers:
            return
        count = len(containers)
        prompt = f"Select container [0-{count-1}]"
        idx_str = self.session.prompt(f"{prompt}: ") or "0"
        idx = int(idx_str)
        container_id = containers[idx]["Id"][:12]
        console.print(f"[bold]Selected:[/bold] {container_id}")

        completer = WordCompleter(["ls", "cat", "exit", "quit"], ignore_case=True)
        while True:
            cmd_line = self.session.prompt(f"{container_id}> ", completer=completer)
            cmd = cmd_line.strip().split()
            if not cmd or cmd[0] in ("exit", "quit"):
                console.print("Exiting shell")
                break
            self.client.exec_command(container_id, cmd)


@rc.command("Docker Shell CLI with prompt history and rich output.")
@rc.option(
    "-u",
    "--url",
    "url",
    help="Docker API endpoint e.g. http://host:2375 or https://host:2376",
)
@rc.option(
    "-s",
    "--socket",
    "socket_path",
    default="/var/run/docker.sock",
    help="Path to Docker Unix socket",
)
def main(url: Optional[str] = None, socket_path: str = "/var/run/docker.sock") -> None:
    config = DockerConfig(url=url, socket_path=socket_path)
    client = DockerClient(config)
    shell = DockerShell(client)
    shell.run()


if __name__ == "__main__":
    main()
