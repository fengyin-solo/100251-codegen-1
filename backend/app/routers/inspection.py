"""信号设备巡检接口：巡检计划、巡检清单、巡检记录、现场问题与复核流转。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inspection import InspectionService

router = APIRouter(prefix="/api/inspection", tags=["信号设备巡检"])

service = InspectionService()

LIST_COLUMNS = [
    "计划编号", "巡检名称", "巡检日期", "设备范围", "班组", "进度",
    "未处理问题", "计划状态",
]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按计划编号、巡检名称或设备范围检索"),
    status: str | None = Query(default=None, description="待下发、执行中、已复核"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按关键字与状态过滤巡检计划；没有数据时返回空页，不报错。"""
    if size > 200:
        size = 200
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出巡检计划清单全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "inspection", "total": total, "items": items}


@router.get("/{plan_id}/consistency")
def get_consistency(plan_id: int) -> dict[str, Any]:
    """巡检清单与巡检记录明细的对账结果：提交复核前先看这一眼。"""
    report, message = service.consistency_report(plan_id)
    if report is None:
        return {"ok": False, "message": message, "plan_id": plan_id, "errors": [message], "items": []}
    return report


@router.get("/{plan_id}", response_model=dict)
def get_entry(plan_id: int) -> dict[str, Any]:
    """读取单份巡检计划明细，含巡检清单、记录、问题与流转记录。"""
    entry = service.get_entry(plan_id)
    if entry is None:
        return {"ok": False, "message": f"巡检计划 {plan_id} 不存在"}
    return entry


@router.post("", response_model=ActionResult)
def create_plan(payload: EntryPayload) -> ActionResult:
    """登记巡检计划；计划为空或巡检项缺失时不落库，并说明缺的是哪一项。"""
    entry, message = service.create_plan(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="巡检计划已登记（待下发）", entry=entry)


@router.post("/{plan_id}/items", response_model=ActionResult)
def add_item(plan_id: int, payload: EntryPayload) -> ActionResult:
    """向计划补充巡检项；同一计划重复登记同一巡检项当场拦下。"""
    entry, message = service.add_item(plan_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="巡检项已加入清单", entry=entry)


@router.post("/{plan_id}/items/{item_id}/record", response_model=ActionResult)
def save_record(plan_id: int, item_id: int, payload: EntryPayload) -> ActionResult:
    """在具体巡检项上登记巡检记录明细（结论、执行人）。"""
    entry, message = service.save_record(plan_id, item_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="巡检记录已登记", entry=entry)


@router.post("/{plan_id}/items/{item_id}/issues", response_model=ActionResult)
def add_issue(plan_id: int, item_id: int, payload: EntryPayload) -> ActionResult:
    """现场发现的问题挂到具体巡检项上，并自动把该巡检项结论记为异常。"""
    entry, message = service.add_issue(plan_id, item_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="现场问题已挂到对应巡检项", entry=entry)


@router.post("/{plan_id}/items/{item_id}/issues/{issue_id}/resolve", response_model=ActionResult)
def resolve_issue(plan_id: int, item_id: int, issue_id: int, payload: EntryPayload) -> ActionResult:
    """登记问题处理结果。"""
    entry, message = service.resolve_issue(plan_id, item_id, issue_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message="问题处理结果已登记", entry=entry)


@router.post("/{plan_id}/actions", response_model=ActionResult)
def run_action(plan_id: int, payload: EntryPayload) -> ActionResult:
    """下发 / 提交复核 / 复核通过 / 复核退回；已归档计划一律拦下。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(plan_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
