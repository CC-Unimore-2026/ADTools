# Adding Filters to Threesome

Threesome is a **TCP proxy**: it sits in front of your services and intercepts every connection. For each configured service it generates two Python filter modules — `_in` (attacker → your service) and `_out` (your service → attacker). You write Python functions in those modules to detect and block attacks. No restart needed — modules are **hot-reloaded** whenever you save the file.

## Step 1 — Configure which services to proxy

Edit `/root/threesome/proxy/config/config.json` on the vulnbox. Add one entry per service:

```json
{
    "services": [
        {
            "name": "myservice",
            "port": 8080
        },
        {
            "name": "http_service",
            "port": 80,
            "http": true
        },
        {
            "name": "https_service",
            "port": 443,
            "http": true,
            "ssl": {
                "server_certificate": "server.pem",
                "server_key": "server.pem"
            }
        }
    ],
    "global_config": {
        "keyword": "UNIMORE",
        "verbose": false,
        "interface": "game",
        "dos": {
            "enabled": true,
            "duration": 60,
            "interval": 2
        },
        "max_stored_messages": 10,
        "max_message_size": 65535
    }
}
```

**Key `global_config` options:**
- `keyword` — string sent back to attackers when a packet is blocked (useful for finding attacks in Packmate)
- `interface` — the game network interface (`game` on this vulnbox)
- `dos.enabled` — when `true`, keeps the attacker's socket alive for `duration` seconds instead of closing it immediately, wasting their time

## Step 2 — Run the proxy (first time)

On first run, threesome auto-generates two module files per service inside `proxy/filter_modules/<service_name>/`:
- `<service_name>_in.py` — filters inbound traffic (attacker → service)
- `<service_name>_out.py` — filters outbound traffic (service → attacker, e.g. to hide flag leaks)

```sh
cd /root/threesome
docker compose up --build -d
# or without docker:
cd proxy && .venv/bin/python proxy.py
```

## Step 3 — Write filter functions

Open the generated module file (e.g. `proxy/filter_modules/myservice/myservice_in.py`) and add methods to the `Module` class. Each method receives a `Stream` object and returns `True` to block or `False` to pass.

```python
from src.stream import Stream, TCPStream, HTTPStream

class Module():

    # --- TCP filter example ---
    def sqli(self, stream: TCPStream):
        """block SQL injection attempts"""
        keywords = [b"' OR '", b"1=1", b"UNION SELECT", b"DROP TABLE"]
        return any(k in stream.current_message.upper() for k in keywords)

    def long_payload(self, stream: TCPStream):
        """block suspiciously large payloads"""
        return len(stream.current_message) > 4096

    # --- HTTP filter example ---
    def path_traversal(self, stream: HTTPStream):
        """block path traversal attempts"""
        return b"../" in stream.current_message or b"..%2F" in stream.current_message.upper()

    def block_flag_leak(self, stream: HTTPStream):
        """
        _out module: block responses that contain a flag
        put this in the _out module to prevent leaking flags to attackers
        """
        import re
        return bool(re.search(rb'[A-Z0-9]{31}=', stream.current_message))

    def execute(self, stream: Stream):
        ignored_functions = []
        attacks = [getattr(Module, attr) for attr in dir(Module)
                   if callable(getattr(Module, attr))
                   and not attr.startswith('__')
                   and attr != "execute"
                   and attr not in ignored_functions]
        for attack in attacks:
            try:
                if attack(self, stream):
                    return attack.__name__
            except IndexError:
                pass
            except Exception as e:
                if isinstance(e, KeyboardInterrupt):
                    raise e
                print(f"[ ERROR in MODULE: {attack.__name__} ]: {e}")
        return None
```

> **Hot reload:** just save the file — threesome picks up changes immediately without restarting. If the file has a syntax error, the previous working version keeps running.

## Stream reference

| Class | Attribute | Type | Description |
|---|---|---|---|
| `TCPStream` | `current_message` | `bytes` | Current packet (modify this to alter what gets sent) |
| `TCPStream` | `previous_messages` | `deque[bytes]` | Previous packets, newest first |
| `HTTPStream` | `current_message` | `bytes` | Raw HTTP bytes (modify this to alter the response) |
| `HTTPStream` | `current_http_message` | `HttpMessage` | Parsed current request/response |
| `HTTPStream` | `previous_http_messages` | `deque[HttpMessage]` | Previous parsed messages, newest first |

`HttpMessage` fields: `.method`, `.url`, `.path`, `.headers` (dict), `.parameters` (dict), `.raw_body`.

> If you modify the body of an HTTP message, update the `Content-Length` header in `current_message` accordingly.

## Skipping a filter temporarily

Add the function name to `ignored_functions` inside `execute()`:

```python
ignored_functions = ["sqli"]  # disable sqli filter without deleting it
```

## Monitor blocked attacks

```sh
# On the vulnbox:
watch cat /root/threesome/proxy/log.txt

# Or via docker logs:
docker logs --follow proxy
```

## Deploy filters via Ansible

To version-control your filter modules, store them in `configs/threesome_filters/` locally and copy them in `tasks/threesome.yml` after the setup step:

```yaml
- name: Setup threesome
  command: bash /root/threesome/setup.sh {{ game_interface }}

- name: Copy filter modules
  ansible.builtin.copy:
    src: ./configs/threesome_filters/
    dest: /root/threesome/proxy/filter_modules/
    # files are hot-reloaded automatically, no restart needed
```

## Redeploy threesome only

```sh
.venv/bin/python deploy_parallel.py \
  --vulnbox-password $(.venv/bin/python -c "import json; print(json.load(open('.env.json'))['root_password'])") \
  --modules threesome
```
