# Personal API tokens

Personal API tokens let applications and scripts call supported Meshive APIs
as an existing user. They are password-equivalent secrets and must be stored
and transmitted securely.

## Access and creation

An administrator grants `api_tokens.manage_own` through a custom role. The
user then opens **Account settings**, finds **API Tokens**, and enters a token
name, expiration, and current password. Users who must still change their
password cannot manage tokens.

Expiration presets include 5, 15, and 30 minutes; 1, 6, and 24 hours; 7 and 30
days; and an explicit **Never** option. Custom durations may use minutes,
hours, or days and must be between 1 minute and 365 days. The default is 1
hour. Meshive calculates the exact expiration time on the server.

Meshive shows the complete token once after creation. Copy it immediately:
later listings contain only a non-secret prefix. Meshive stores a SHA-256 hash,
not the plaintext token. Do not place tokens in URLs, source control, logs, or
screenshots.

## API usage

Send the token in the HTTP `Authorization` header:

```bash
curl \
  -H 'Authorization: Bearer msh_pat_REPLACE_ME' \
  'https://meshive.example.invalid/api/models?search=Magik'
```

Catalogue search and filters use the same APIs as the web application. A token
always receives the owner's current permissions and library-source scope. For
example, a user with `catalogue.view` can query visible models but cannot
download archives unless the current role also grants `archives.download`.

Tokens cannot authenticate account-credential, session, recovery, setup, or
token-management endpoints. Creating another token always requires a normal
browser session and the user's current password.

## Expiration and revocation

Expired tokens return `401 Unauthorized`. A user can revoke a token at any
time from **Account settings**; revocation takes effect immediately. Existing
tokens also stop working immediately when the owner is disabled or required
to change their password. Role, permission, and source-access changes are
applied on the next request without recreating the token.
