# Users and login

- [Users and rights](#users-and-rights)
- [Two-factor login](#two-factor-login)
- [OpenID Connect](#openid-connect)
- [API tokens and shortcuts](#api-tokens-and-shortcuts)

## Users and rights

Under **Einstellungen → Benutzer** (settings → users) admins create more accounts. Clicking a
user opens their rights:

- **Administrator:** may do everything, settings, users and the admin area included.
- **Sichtbare Kanäle** (visible channels): all or only selected ones. Whoever sees only selected channels finds
  nothing else anywhere – not in the library, the search, on the home page or by direct link.
  Ideal for a kids profile.
- **Darf Videos hinzufügen und abonnieren** (may add and subscribe): off = watch-only. Adding, subscriptions and the
  downloads page then disappear from the interface and are blocked in the API too.
- **Auf Familiengeräten zeigen** (show on family devices) and a PIN – see
  ["Wer schaut?"](living-room.md#wer-schaut--family-devices).

Watch progress, playlists, playback speeds and "save to device" always belong to the single
user.

## Two-factor login

Under **Einstellungen → Konto → Zwei-Faktor-Anmeldung** (settings → account → two-factor
login) scan the QR code with an authenticator app (e.g. Aegis, 2FAS, Google Authenticator, the
Passwords app on the iPhone). From then on TubeVault asks for the 6-digit code when you sign in.
Keep the ten recovery codes somewhere safe – each works once if the phone is gone. Admins can
reset a user's two-factor login; for your own admin account, as a last resort:

```sh
docker exec -it tubevault python -m app reset-2fa <user>
```

## OpenID Connect

If you already run Authelia, Authentik, Keycloak, Pocket ID or another OIDC provider, you can
sign in through it – with its two-factor protection and without a separate TubeVault password.
It is set up with environment variables, so the client secret ends up neither in the database
nor in backups:

| Variable | Default | Meaning |
| -------- | ------- | ------- |
| `PUBLIC_URL` | empty | The address TubeVault is reachable under, including `BASE_PATH`, e.g. `https://tube.example.com`. Empty = taken from the request |
| `OIDC_ISSUER` | empty | The provider's address, e.g. `https://auth.example.com` (Authentik: `https://auth.example.com/application/o/tubevault/`). Empty = off |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | empty | The client's credentials at the provider |
| `OIDC_NAME` | `SSO` | Text on the button: "Mit … anmelden" (sign in with …) |
| `OIDC_SCOPES` | `openid profile email groups` | Requested scopes |
| `OIDC_USERNAME_CLAIM` | `preferred_username` | Where the user name of new accounts comes from |
| `OIDC_GROUPS_CLAIM` | `groups` | Where the groups are |
| `OIDC_ADMIN_GROUP` | empty | Members of this group become admins, everyone else doesn't (the last admin always stays). Empty = rights are managed in TubeVault |
| `OIDC_AUTO_CREATE` | `true` | Create unknown accounts on first login. `false` = only linked accounts get in |
| `OIDC_TOKEN_AUTH` | `client_secret_basic` | Or `client_secret_post` – as configured at the provider |
| `PASSWORD_LOGIN` | `true` | `false` = sign in only through the provider (only takes effect when OIDC is set up) |

At the provider, create a confidential client with this redirect address – **Verwaltung →
Anmeldung über OIDC** (admin area → login via OIDC) shows it too:

```
https://tube.example.com/api/auth/oidc/callback
```

<details>
<summary>Authelia</summary>

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: tubevault
        client_name: TubeVault
        client_secret: '$pbkdf2-sha512$…'   # authelia crypto hash generate pbkdf2
        authorization_policy: two_factor
        redirect_uris:
          - https://tube.example.com/api/auth/oidc/callback
        scopes: [openid, profile, email, groups]
        token_endpoint_auth_method: client_secret_basic
```

`OIDC_ISSUER=https://auth.example.com`
</details>

<details>
<summary>Authentik</summary>

*Applications → Providers → OAuth2/OpenID Provider*, client type *Confidential*, redirect URI
as above. Then create an application with the slug `tubevault`.
`OIDC_ISSUER=https://auth.example.com/application/o/tubevault/`
</details>

<details>
<summary>Keycloak</summary>

A client with *Client authentication* on and *Valid redirect URIs* as above. For groups, add a
*Group Membership* mapper with the token claim name `groups` to the dedicated client scope
("Full group path" off) and set `OIDC_SCOPES=openid profile email` – Keycloak doesn't know a
`groups` scope by itself. `OIDC_ISSUER=https://auth.example.com/realms/<realm>`
</details>

<details>
<summary>Pocket ID</summary>

*OIDC Clients → Add*, callback URL as above. `OIDC_ISSUER=https://id.example.com`
</details>

The first account that signs in this way becomes admin if there are no users yet. Existing
TubeVault accounts are linked under **Einstellungen → Konto → Anmeldung über …** (only while
signed in – the same user name alone is never enough). Accounts without a password can set one
to get in without the provider too.

## API tokens and shortcuts

Under **Einstellungen → API-Tokens** you create tokens for scripts (read-only or full access,
optionally with an expiry date). The token is sent as a header:

```sh
curl -X POST https://tube.example.com/api/videos \
  -H "Authorization: Bearer tv_…" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtu.be/dQw4w9WgXcQ"}'
```

The API documentation at `/api/docs` describes every endpoint. Managing tokens, changing the
password, podcast addresses and family devices only work after signing in in the browser, not
with a token.

**iPhone/iPad – "Share → Load into TubeVault":** in the *Shortcuts* app, create a new shortcut,
turn on "Show in Share Sheet" (input: URLs) in its details and add the action **Get Contents of
URL**: URL `https://tube.example.com/api/videos`, method *POST*, header `Authorization` =
`Bearer tv_…`, request body *JSON* with the field `url` = *Shortcut Input*. The shortcut then
appears under *Share* in the YouTube app.

**Android:** with TubeVault installed as an app, it is right in the share menu – the link lands
in the "add video" dialog.
