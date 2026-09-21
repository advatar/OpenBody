# Caddy site block

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
