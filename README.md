# iPhone Stock Watch

Public repository for monitoring iPhone Pro Max 256GB Black stock.

- No notification secret is stored in this repository.
- Android notifications are sent through ntfy.
- The ntfy topic is read from the GitHub Actions secret `NTFY_TOPIC`.
- GitHub Actions checks stock every 5 minutes.
