# Docker Misconfig CLI

An interactive Docker client that lets you list containers and run commands via either a Unix socket or a remote HTTP(S) endpoint.  

> **Note**: This tool was inspired by a CTF challenge where a Docker socket was exposed inside a container. It is intended **solely for educational purposes**, never run this against systems you don't own or have explicit permission to test.

---

## Features

- Connect via:
  - **Unix socket** (e.g. `/var/run/docker.sock`)
  - **HTTP(S)** API (e.g. `http://host:2375` or `https://host:2376`)
- Interactive shell with:
  - **Prompt session** (history & autocomplete)
  - **Rich**-formatted container table and colored output  
- Easy install & uninstall via `pipx`

---

## Shodan Dork

If you're curious how attackers find exposed Docker APIs on the Internet, a common Shodan query is:

```

port:2375 product:"Docker"

```

Be aware: despite best practices, unprotected Docker sockets **still** show up in public scans.

---

## Installation

_First, clone or download this repository to your local machine, or install directly from GitHub._

1. **Install with pipx** (recommended isolation):

   ```bash
   pipx install git+https://github.com/Chocapikk/docker-misconfig-cli
   ```

2. **Or install with pip**:

   ```bash
   git clone https://github.com/Chocapikk/docker-misconfig-cli
   cd docker-misconfig-cli
   pip install .
   ```

---

## Usage

### Via Unix socket

```bash
docker-misconfig --socket /var/run/docker.sock
```

### Via HTTP(S) endpoint

```bash
docker-misconfig --url http://192.168.1.100:2375
# or with TLS
docker-misconfig --url https://docker.example.com:2376
```

Once started:

1. You'll see a table of running containers.
2. Enter the **index** of the container you want to target.
3. At the `CONTAINER_ID> ` prompt, type any Docker command (e.g. `ls /`, `cat /etc/hosts`, `exit`, etc.).
4. Type `exit` or `quit` to leave the shell.

---

## Security Disclaimer

* **DO NOT** run this tool against systems you do not control or have explicit authorization to test.
* Exposing the Docker socket (whether by bind-mount or open HTTP port) grants full control over the host, this is **extremely** dangerous in production.
* Use only in **controlled** lab or CTF environments to learn about Docker security.