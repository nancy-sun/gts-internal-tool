from __future__ import annotations


UPLOAD_CRUMB = {"label": "上传完整报价单", "href": "/upload"}
GENERATE_CRUMB = {"label": "生成报价单", "href": "/generate"}
SEARCH_CRUMB = {"label": "查询数据库", "href": "/search"}
DATA_QUALITY_CRUMB = {"label": "数据检查", "href": "/data-quality"}
LOGS_CRUMB = {"label": "操作记录", "href": "/logs"}
HS_CRUMB = {"label": "HS Code", "href": "/hs-codes"}
SUPPLIERS_CRUMB = {"label": "供应商", "href": "/suppliers"}
MAINTENANCE_CRUMB = {"label": "系统状态", "href": "/maintenance"}


def breadcrumbs(*crumbs: dict[str, str]) -> list[dict[str, str]]:
    return list(crumbs)


def child_breadcrumbs(parent: dict[str, str], label: str) -> list[dict[str, str]]:
    return [parent, {"label": label, "href": ""}]
