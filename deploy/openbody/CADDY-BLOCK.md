# Caddy site block: landing page

This block serves the public marketing site (`LandingPage/`), not the OpenBody
protocol host. The protocol host's blocks are in
[`Caddyfile.example`](Caddyfile.example).

```caddyfile
openbody.invivo.health {
	encode zstd gzip
	header {
		X-Content-Type-Options "nosniff"
		Referrer-Policy "no-referrer"
	}
	reverse_proxy host.docker.internal:8796
}
```

Assumptions:

- **Public by design.** The site is static marketing content and has no
  authenticated boundary. Never point this block at the protocol host's port
  (`8797`).
- **Caddy runs in a container; the site runs on the host.** Docker Desktop
  resolves `host.docker.internal` automatically. On Linux, add
  `extra_hosts: ["host.docker.internal:host-gateway"]` to the Caddy service, or
  use `127.0.0.1:8796` when Caddy runs on the host.
- **Only Caddy reaches `:8796`.** Bind the site to an interface the container can
  reach, and firewall that port from the internet so the proxy cannot be
  bypassed.
- **TLS** is Caddy's automatic HTTPS for the named host. Add HSTS or a content
  security policy once the site's asset origins are settled.
