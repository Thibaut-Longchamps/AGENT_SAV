import httpx


def api_error_message(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            payload = exc.response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
            return str(payload["detail"])
        return f"La demande a échoué (HTTP {exc.response.status_code})."
    if isinstance(exc, httpx.TimeoutException):
        return "L'API met trop de temps à répondre. Consultez les logs avant de réessayer."
    return "Impossible de joindre l'API. Vérifiez que les conteneurs sont démarrés."
