# Password recovery

Meshive can send email-verification and password-reset links through an SMTP
account. Password recovery is optional. The login page only shows the recovery
link when all required mail settings are present.

## SMTP configuration

Set the following container environment variables:

```env
MESHIVE_PUBLIC_URL=https://meshive.example.com
MESHIVE_SMTP_HOST=smtp.example.com
MESHIVE_SMTP_PORT=587
MESHIVE_SMTP_USERNAME=meshive@example.com
MESHIVE_SMTP_PASSWORD=replace-with-the-mailbox-password
MESHIVE_SMTP_FROM=meshive@example.com
MESHIVE_SMTP_SECURITY=starttls
```

`MESHIVE_SMTP_SECURITY` accepts:

- `ssl` for implicit TLS, commonly on port 465;
- `starttls` for a plaintext connection upgraded to TLS, commonly on port 587;
- `none` only for a trusted development mail relay.

Do not commit SMTP credentials. Supply them through the container platform's
environment or secret management. Meshive validates SMTP certificates using
the operating system trust store.

Optional limits are `MESHIVE_SMTP_TIMEOUT_SECONDS` (default 15),
`MESHIVE_PASSWORD_RESET_LIFETIME_MINUTES` (default 30), and
`MESHIVE_EMAIL_VERIFICATION_LIFETIME_HOURS` (default 24).

## User workflow

A signed-in user adds a recovery address from Account settings and confirms the
message sent by Meshive. Until confirmation, the address cannot receive
password-reset links. Administrators can also store an address and trigger its
verification from the Users page.

Password-reset requests always return the same public response, regardless of
whether a matching eligible account exists. Tokens are random, stored only as
SHA-256 hashes, expire automatically, and can only be used once. A successful
reset revokes every active session and every other recovery token for that
account.

## Container-side recovery

SMTP is not required for emergency recovery. From a container console, run:

```sh
meshive reset-password --username admin
```

When the console runs as root, run the command with the configured runtime
identity:

```sh
gosu "$PUID:$PGID" meshive reset-password --username admin
```

The command prompts without placing the password in the process arguments and
revokes all sessions belonging to the account. For non-interactive secret
input, pass `--password-stdin` and provide the value through standard input.
