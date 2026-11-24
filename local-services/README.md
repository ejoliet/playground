# Local Services

A local homepage for the web servers and HTTP services running on your machine. The dashboard discovers listening TCP ports, checks for HTTP and HTTPS responses, and lets you search for and open the services it finds.

## Run on the machine you want to inspect

Use Python 3.9 or newer on Linux, macOS, or Windows. The app uses Python’s standard library and serves all its assets locally.

```sh
cd local-services
python3 dashboard.py
```

On Windows, use `py -3 dashboard.py`. Open <http://127.0.0.1:8787/>. If that port is busy, add `--port 8790` and use the URL printed in the terminal. Press Ctrl+C to stop the dashboard.

To reach the dashboard from other machines, add `--host 0.0.0.0`. This has no authentication: anyone on the network can list your listening services. Links to services listening on all interfaces use the hostname you opened the dashboard with. Services bound only to `127.0.0.1` keep their loopback link and open only on the machine running the dashboard.

The dashboard scans on page load and when you select **Rescan**. It sends a short `HEAD /` request without following redirects and lists services that return an HTTP status, including redirects and authentication errors. It can identify HTTPS endpoints with self-signed certificates. Your browser applies its normal certificate checks when you open them.

Discovery uses `ss` or `/proc/net/tcp*` on Linux, `lsof` on macOS, and `netstat` on Windows. The OS may hide process names or sockets from unprivileged users. Run directly on your host to see its listeners. In WSL, a container, or a VM, discovery sees listeners visible from that environment.

Services that require a specific hostname, client certificate, or HTTP/2, or that do not respond to a short `HEAD /` probe, may be missed. UDP-only services are outside the scan.
