"""Create a Deal Review Tracker task from a purchase acknowledgement."""

from datetime import date
from typing import Protocol

from .client import get, request
from .errors import AsanaError
from .settings import PROJECT_NAME


class DealTask(Protocol):
    task_name: str
    description: str
    delivery_date: date
    period: str
    quote_number: str


class CreatedTask:
    def __init__(self, gid: str, url: str):
        self.gid = gid
        self.url = url


def create_task(task: DealTask) -> CreatedTask:
    project_gid = find_project_gid()
    settings = get(
        f"/projects/{project_gid}/custom_field_settings",
        {
            "opt_fields": ",".join(
                (
                    "custom_field.gid",
                    "custom_field.name",
                    "custom_field.resource_subtype",
                    "custom_field.enum_options.gid",
                    "custom_field.enum_options.name",
                    "custom_field.enum_options.enabled",
                )
            )
        },
    )["data"]
    created = request(
        "POST",
        "/tasks",
        {"opt_fields": "gid,permalink_url"},
        {
            "data": {
                "name": task.task_name,
                "notes": task.description,
                "projects": [project_gid],
                "custom_fields": build_custom_fields(settings, task),
            }
        },
    )["data"]
    gid = str(created["gid"])
    url = str(created.get("permalink_url") or f"https://app.asana.com/0/{project_gid}/{gid}")
    return CreatedTask(gid, url)


def build_custom_fields(settings: list[dict], task: DealTask) -> dict:
    by_name: dict[str, dict] = {}
    for setting in settings:
        field = setting.get("custom_field") or setting
        name = str(field.get("name", "")).strip().lower()
        if name:
            by_name[name] = field
    values = {
        "delivery date": task.delivery_date.isoformat(),
        "period": task.period,
        "quote number": task.quote_number,
    }
    missing = [name for name in values if name not in by_name]
    if missing:
        raise AsanaError(
            f"{PROJECT_NAME} is missing custom fields: {', '.join(missing)}",
            422,
        )
    return {by_name[name]["gid"]: field_value(by_name[name], text) for name, text in values.items()}


def field_value(field: dict, text: str):
    subtype = field.get("resource_subtype")
    if subtype == "text":
        return text
    if subtype == "date":
        return {"date": text}
    if subtype == "enum":
        for option in field.get("enum_options") or []:
            if option.get("enabled") is False:
                continue
            if str(option.get("name", "")).strip().lower() == text.lower():
                return option["gid"]
        raise AsanaError(f"Asana field {field.get('name')} has no option {text!r}", 422)
    raise AsanaError(
        f"Asana field {field.get('name')} has unsupported type {subtype}",
        422,
    )


def find_project_gid() -> str:
    matches: list[str] = []
    for workspace in get("/workspaces", {"opt_fields": "gid,name"})["data"]:
        params = {"archived": "false", "opt_fields": "gid,name", "limit": "100"}
        while True:
            page = get(f"/workspaces/{workspace['gid']}/projects", params)
            for project in page["data"]:
                if str(project.get("name", "")).strip() == PROJECT_NAME:
                    matches.append(str(project["gid"]))
            offset = (page.get("next_page") or {}).get("offset")
            if not offset:
                break
            params["offset"] = offset
    if not matches:
        raise AsanaError(f"Asana project {PROJECT_NAME!r} was not found", 404)
    if len(matches) > 1:
        raise AsanaError(f"More than one Asana project is named {PROJECT_NAME!r}", 409)
    return matches[0]
