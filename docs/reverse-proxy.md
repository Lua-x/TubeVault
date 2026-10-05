# Reverse proxy

TubeVault works behind Nginx, Nginx Proxy Manager, Caddy and Traefik – WebSockets included
(live progress, phone remote, watch together). For a sub-path set `BASE_PATH`; it doesn't
matter whether the proxy passes the prefix on or strips it.

A reverse proxy with a certificate (HTTPS) is also what makes
[save to device](watching.md#save-to-device) and [installing the app](watching.md#installing-the-app-pwa)
possible on Android and desktop. Set `PUBLIC_URL` (e.g. `https://tube.example.com`) so podcast
feeds and the OIDC redirect use the public address.

The examples use port 8823; installs from before 1.0 that still run on 8096 use that instead
(see [port](installation.md#port)).

<details>
<summary>Nginx / Nginx Proxy Manager</summary>

```nginx
location / {
    proxy_pass http://tubevault:8823;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_buffering off;
}
```

In Nginx Proxy Manager it is enough to switch on **Websockets Support** for the proxy host.
</details>

<details>
<summary>Caddy</summary>

```caddy
tube.example.com {
    reverse_proxy tubevault:8823
}
```

With a sub-path (`BASE_PATH=/tubevault`):

```caddy
example.com {
    handle /tubevault* {
        reverse_proxy tubevault:8823
    }
}
```
</details>

<details>
<summary>Traefik (labels)</summary>

```yaml
    labels:
      - traefik.enable=true
      - traefik.http.routers.tubevault.rule=Host(`tube.example.com`)
      - traefik.http.routers.tubevault.entrypoints=websecure
      - traefik.http.routers.tubevault.tls.certresolver=letsencrypt
      - traefik.http.services.tubevault.loadbalancer.server.port=8823
```
</details>

`FORWARDED_ALLOW_IPS` (default `*`) decides whose `X-Forwarded-*` headers are trusted. If
TubeVault is reachable without the proxy too, set it to the proxy's address.

The [DLNA server](living-room.md#dlna) refuses every request that comes through a reverse
proxy – it is meant for the home network only.
