"""信号设备巡检接口：巡检计划下发、执行、问题登记、复核与归档。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.inspection import InspectionService

router = APIRouter(prefix="/api/inspection", tags=["信号设备巡检"])

service = InspectionService()
STATUSES = ["待下发", "执行中", "已复核"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按巡检计划编号或所属车站检索"),
    status: str | None = Query(default=None, description="待下发、执行中、已复核"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按计划编号、车站和状态查询巡检计划。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出巡检计划、巡检清单与巡检记录明细。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "inspection", "total": total, "items": items}


@router.get("/{plan_id}", response_model=dict)
def get_entry(plan_id: int) -> dict[str, Any]:
    """读取单份巡检计划及逐项记录。"""
    plan = service.get_entry(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"巡检计划 {plan_id} 不存在")
    return plan


@router.post("", response_model=ActionResult)
def create_plan(payload: EntryPayload) -> ActionResult:
    """登记巡检计划；计划为空、巡检项缺失或重复时整单不落库。"""
    plan, errors = service.create_plan(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message="巡检计划已登记，当前状态为待下发", entry=plan)


@router.post("/{plan_id}/dispatch", response_model=ActionResult)
def dispatch_plan(plan_id: int, payload: EntryPayload) -> ActionResult:
    """待下发计划下发后进入执行中。"""
    plan, message = service.dispatch(plan_id, payload.values)
    if plan is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=plan)


@router.post("/{plan_id}/items/{item_id}/execute", response_model=ActionResult)
def execute_item(plan_id: int, item_id: int, payload: EntryPayload) -> ActionResult:
    """登记具体巡检项的现场结论，清单与记录明细结论必须一致。"""
    plan, message = service.execute_item(plan_id, item_id, payload.values)
    if plan is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=plan)


@router.post("/{plan_id}/items/{item_id}/issues", response_model=ActionResult)
def register_issue(plan_id: int, item_id: int, payload: EntryPayload) -> ActionResult:
    """把现场发现的问题挂到巡检记录的具体巡检项上。"""
    plan, message = service.register_issue(plan_id, item_id, payload.values)
    if plan is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=plan)


@router.post("/{plan_id}/review", response_model=ActionResult)
def review_plan(plan_id: int, payload: EntryPayload) -> ActionResult:
    """复核通过后归档；复核驳回则退回执行中并保留原因。"""
    plan, message = service.review(plan_id, payload.values)
    if plan is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=plan)
