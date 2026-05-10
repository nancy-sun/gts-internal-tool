from __future__ import annotations


UPLOAD_CRUMB = {"label": "上传完整报价单", "href": "/upload"}
GENERATE_CRUMB = {"label": "生成报价单", "href": "/generate"}
SEARCH_CRUMB = {"label": "查询数据库", "href": "/search"}
LOGS_CRUMB = {"label": "操作记录", "href": "/logs"}
HS_CRUMB = {"label": "HS Code", "href": "/hs-codes"}


def breadcrumbs(*crumbs: dict[str, str]) -> list[dict[str, str]]:
    return list(crumbs)


def child_breadcrumbs(parent: dict[str, str], label: str) -> list[dict[str, str]]:
    return [parent, {"label": label, "href": ""}]
