import httpx

from app.config import Settings


async def get_proxmox_stats(settings: Settings) -> dict:
    if not settings.proxmox_configured:
        return {"error": "Proxmox not configured. Set PROXMOX_* vars in .env."}

    host = settings.proxmox_base_url
    node = settings.proxmox_node
    headers: dict[str, str] = {}
    auth = None

    if settings.proxmox_token_id and settings.proxmox_token_secret:
        headers["Authorization"] = (
            f"PVEAPIToken={settings.proxmox_token_id}={settings.proxmox_token_secret}"
        )
    elif settings.proxmox_user and settings.proxmox_password:
        auth = (settings.proxmox_user, settings.proxmox_password)

    verify = settings.proxmox_verify_ssl

    try:
        async with httpx.AsyncClient(verify=verify, timeout=15.0) as client:
            status_resp = await client.get(
                f"{host}/api2/json/nodes/{node}/status",
                headers=headers,
                auth=auth,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()["data"]

            storage_resp = await client.get(
                f"{host}/api2/json/nodes/{node}/storage",
                headers=headers,
                auth=auth,
            )
            storage_resp.raise_for_status()
            storage_list = storage_resp.json()["data"]
    except httpx.HTTPStatusError as exc:
        return {"error": f"Proxmox HTTP {exc.response.status_code}: {exc.response.text[:200]}"}
    except httpx.RequestError as exc:
        return {"error": f"Proxmox connection failed: {exc}"}

    cpu_percent = round(float(status_data.get("cpu", 0)) * 100, 1)
    used_total = 0
    size_total = 0
    for s in storage_list:
        used_total += int(s.get("used", 0) or 0)
        size_total += int(s.get("total", 0) or 0)

    storage_percent = round((used_total / size_total) * 100, 1) if size_total else 0.0

    return {
        "cpu_percent": cpu_percent,
        "storage_used_bytes": used_total,
        "storage_total_bytes": size_total,
        "storage_percent": storage_percent,
    }
