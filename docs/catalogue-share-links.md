# Temporary Catalogue Links

Temporary Catalogue Links are short-lived capability URLs for viewing read-only catalogue metadata when a client cannot send an `Authorization: Bearer` header. They are not a replacement for [Personal API Tokens](api-tokens.md), which remain the preferred option for API clients.

Creating, listing, and revoking links requires the `catalogue_share_links.manage_own` permission and confirmation of the current password. A link expires after 5, 15, 30, or 60 minutes and can be revoked at any time. The full URL is shown only once; anyone possessing it can use it until expiry or revocation.

Every request evaluates the owner's current `catalogue.view` permission, active account state, and library-source scope. Removing any of these access rights takes effect immediately. Links expose only catalogue metadata: they cannot download archives, browse archive contents, serve images, modify data, or access account or administration APIs.

The available endpoints are `GET /api/share/catalogue/{token}/models` and `GET /api/share/catalogue/{token}/filters`. The models endpoint supports the same catalogue query parameters as `/api/models`, such as `search`, `source_id`, `tag_id`, `sort`, `page`, and `page_size`.

For example, open `https://meshive.example/api/share/catalogue/msh_share_example/models?search=Example` in a browser or fetch it with curl. Treat the complete URL like a password, do not put it in logs or tickets, and revoke it after ad-hoc use.
