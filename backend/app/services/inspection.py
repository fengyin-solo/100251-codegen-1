"""信号设备巡检业务规则：计划流转、巡检项校验、问题挂载与复核归档。"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "inspection"
STATUS_PENDING = "待下发"
STATUS_EXECUTING = "执行中"
STATUS_REVIEWED = "已复核"
PLAN_REQUIRED_FIELDS = ["巡检计划编号", "巡检日期", "所属车站"]
ITEM_REQUIRED_FIELDS = ["巡检项", "设备编号", "巡检内容"]
NORMAL = "正常"
ABNORMAL = "异常"
WAITING = "待巡检"
CONCLUSIONS = [NORMAL, ABNORMAL]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _text(values: dict[str, Any], key: str) -> str:
    return str(values.get(key) or "").strip()


class InspectionService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [deepcopy(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("巡检计划编号", ""))
                or keyword in str(row.get("所属车站", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, plan_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, plan_id)
        return deepcopy(row) if row is not None else None

    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        """整单校验通过后才写库；任一巡检项缺失或重复都不创建计划。"""
        errors = [
            f"缺少必填字段：{field}"
            for field in PLAN_REQUIRED_FIELDS
            if not _text(values, field)
        ]

        raw_items = values.get("巡检项")
        if not isinstance(raw_items, list) or not raw_items:
            raw_items = []
            errors.append("缺少必填字段：巡检项（计划至少包含一个巡检项）")

        normalized_items: list[dict[str, str]] = []
        seen_names: set[str] = set()
        for index, raw_item in enumerate(raw_items, start=1):
            if not isinstance(raw_item, dict):
                errors.append(f"第 {index} 个巡检项格式不正确，需提供巡检项、设备编号和巡检内容")
                continue

            item_name = _text(raw_item, "巡检项") or f"第 {index} 个巡检项"
            missing = [
                field
                for field in ITEM_REQUIRED_FIELDS
                if not _text(raw_item, field)
            ]
            if missing:
                errors.append(f"巡检项「{item_name}」缺少：{'、'.join(missing)}")
                continue

            normalized_name = _text(raw_item, "巡检项")
            if normalized_name in seen_names:
                errors.append(f"巡检项「{normalized_name}」在同一份计划中重复登记，已当场拦下")
                continue
            seen_names.add(normalized_name)
            normalized_items.append({
                "巡检项": normalized_name,
                "设备编号": _text(raw_item, "设备编号"),
                "巡检内容": _text(raw_item, "巡检内容"),
                "巡检标准": _text(raw_item, "巡检标准"),
            })

        if errors:
            return None, errors

        rows = store.rows(MODULE)
        plan_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        operator = _text(values, "操作人") or "值班管理员"
        checklist = [
            {
                "id": item_id,
                **item,
                "清单结论": WAITING,
            }
            for item_id, item in enumerate(normalized_items, start=1)
        ]
        records = [
            {
                "巡检项ID": item["id"],
                "巡检项": item["巡检项"],
                "记录结论": WAITING,
                "执行人": None,
                "执行时间": None,
                "执行备注": None,
                "问题列表": [],
            }
            for item in checklist
        ]
        plan = {
            "id": plan_id,
            "status": STATUS_PENDING,
            "pending": True,
            "abnormal": False,
            "archived": False,
            "巡检计划编号": _text(values, "巡检计划编号"),
            "巡检日期": _text(values, "巡检日期"),
            "所属车站": _text(values, "所属车站"),
            "作业班组": _text(values, "作业班组"),
            "巡检清单": checklist,
            "巡检记录明细": records,
            "下发人": None,
            "下发时间": None,
            "最近执行人": None,
            "复核人": None,
            "复核时间": None,
            "复核结论": None,
            "驳回原因": None,
            "操作轨迹": [
                {
                    "动作": "登记计划",
                    "操作人": operator,
                    "时间": _now(),
                    "原状态": None,
                    "新状态": STATUS_PENDING,
                    "原因": None,
                }
            ],
        }
        rows.append(plan)
        return deepcopy(plan), []

    def dispatch(self, plan_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        plan, message = self._mutable_plan(plan_id)
        if plan is None:
            return None, message
        operator, message = self._required_operator(values)
        if not operator:
            return None, message
        if plan["status"] != STATUS_PENDING:
            return None, f"当前状态为「{plan['status']}」，只有待下发计划可以下发"

        plan["status"] = STATUS_EXECUTING
        plan["下发人"] = operator
        plan["下发时间"] = _now()
        self._append_history(plan, "下发计划", operator, STATUS_PENDING, STATUS_EXECUTING)
        return deepcopy(plan), "巡检计划已下发，现场可开始执行"

    def execute_item(
        self,
        plan_id: int,
        item_id: int,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        plan, message = self._mutable_plan(plan_id)
        if plan is None:
            return None, message
        if plan["status"] != STATUS_EXECUTING:
            return None, f"当前状态为「{plan['status']}」，不能登记巡检记录"
        operator, message = self._required_operator(values)
        if not operator:
            return None, message

        checklist_item, record, message = self._find_item_pair(plan, item_id)
        if checklist_item is None or record is None:
            return None, message

        checklist_conclusion = _text(values, "清单结论")
        record_conclusion = _text(values, "记录结论")
        if not checklist_conclusion:
            return None, f"巡检项「{checklist_item['巡检项']}」缺少清单结论"
        if not record_conclusion:
            return None, f"巡检项「{checklist_item['巡检项']}」缺少巡检记录明细结论"
        if checklist_conclusion not in CONCLUSIONS:
            return None, f"巡检项「{checklist_item['巡检项']}」清单结论只能是：正常、异常"
        if record_conclusion not in CONCLUSIONS:
            return None, f"巡检项「{checklist_item['巡检项']}」记录结论只能是：正常、异常"
        if checklist_conclusion != record_conclusion:
            return (
                None,
                f"巡检项「{checklist_item['巡检项']}」结论对不上：清单结论为「{checklist_conclusion}」，"
                f"巡检记录明细结论为「{record_conclusion}」"
            )

        if checklist_conclusion == ABNORMAL:
            issue_description = _text(values, "问题描述")
            if not record["问题列表"]:
                if not issue_description:
                    return None, f"巡检项「{checklist_item['巡检项']}」结论为异常时，必须写明现场问题"
                issue_no = 1
                record["问题列表"].append(
                    self._build_issue(plan_id, item_id, issue_no, issue_description, values, operator)
                )
            elif issue_description:
                issue_no = len(record["问题列表"]) + 1
                record["问题列表"].append(
                    self._build_issue(plan_id, item_id, issue_no, issue_description, values, operator)
                )
        elif record["问题列表"]:
            return None, f"巡检项「{checklist_item['巡检项']}」已挂现场问题，不能登记为正常"

        checklist_item["清单结论"] = checklist_conclusion
        record["记录结论"] = record_conclusion
        record["执行人"] = operator
        record["执行时间"] = _now()
        record["执行备注"] = _text(values, "执行备注") or None
        plan["最近执行人"] = operator
        plan["abnormal"] = self._has_abnormal_item(plan)
        self._append_history(
            plan,
            "登记巡检记录",
            operator,
            STATUS_EXECUTING,
            STATUS_EXECUTING,
            说明=f"{checklist_item['巡检项']}：{record_conclusion}",
        )
        return deepcopy(plan), f"巡检项「{checklist_item['巡检项']}」执行记录已保存"

    def register_issue(
        self,
        plan_id: int,
        item_id: int,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        plan, message = self._mutable_plan(plan_id)
        if plan is None:
            return None, message
        if plan["status"] != STATUS_EXECUTING:
            return None, f"当前状态为「{plan['status']}」，不能登记现场问题"
        operator, message = self._required_operator(values)
        if not operator:
            return None, message

        checklist_item, record, message = self._find_item_pair(plan, item_id)
        if checklist_item is None or record is None:
            return None, message
        description = _text(values, "问题描述")
        if not description:
            return None, f"巡检项「{record['巡检项']}」缺少现场问题描述"

        issue_no = len(record["问题列表"]) + 1
        record["问题列表"].append(
            self._build_issue(plan_id, item_id, issue_no, description, values, operator)
        )
        checklist_item["清单结论"] = ABNORMAL
        record["记录结论"] = ABNORMAL
        record["执行人"] = operator
        record["执行时间"] = _now()
        record["执行备注"] = _text(values, "执行备注") or record.get("执行备注")
        plan["最近执行人"] = operator
        plan["abnormal"] = True
        self._append_history(
            plan,
            "登记现场问题",
            operator,
            STATUS_EXECUTING,
            STATUS_EXECUTING,
            说明=f"{record['巡检项']}：{description}",
        )
        return deepcopy(plan), f"现场问题已挂到巡检项「{record['巡检项']}」"

    def review(self, plan_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        plan, message = self._mutable_plan(plan_id)
        if plan is None:
            return None, message
        if plan["status"] != STATUS_EXECUTING:
            return None, f"当前状态为「{plan['status']}」，不能提交复核"
        operator, message = self._required_operator(values)
        if not operator:
            return None, message

        review_result = _text(values, "复核结论") or _text(values, "action")
        if review_result not in ("通过", "驳回"):
            return None, "复核结论只能是「通过」或「驳回」"

        if review_result == "驳回":
            reason = _text(values, "原因") or _text(values, "驳回原因")
            if not reason:
                return None, "复核驳回必须写清退回执行中的原因"
            plan["status"] = STATUS_EXECUTING
            plan["复核人"] = operator
            plan["复核时间"] = _now()
            plan["复核结论"] = "未通过"
            plan["驳回原因"] = reason
            plan["pending"] = True
            self._append_history(plan, "复核驳回", operator, STATUS_EXECUTING, STATUS_EXECUTING, reason)
            return deepcopy(plan), "复核未通过，计划已退回执行中"

        errors = self._review_errors(plan)
        if errors:
            return None, "；".join(errors)

        plan["status"] = STATUS_REVIEWED
        plan["pending"] = False
        plan["abnormal"] = self._has_abnormal_item(plan)
        plan["archived"] = True
        plan["复核人"] = operator
        plan["复核时间"] = _now()
        plan["复核结论"] = "通过"
        self._append_history(plan, "复核通过", operator, STATUS_EXECUTING, STATUS_REVIEWED)
        return deepcopy(plan), "巡检计划复核通过并归档，归档后不可再改动"

    def _mutable_plan(self, plan_id: int) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"
        if bool(plan.get("archived")) or plan.get("status") == STATUS_REVIEWED:
            return None, "巡检计划已归档（已复核），不允许再改动"
        return plan, ""

    def _required_operator(self, values: dict[str, Any]) -> tuple[str | None, str]:
        operator = _text(values, "操作人")
        if not operator:
            return None, "缺少操作人，无法记录交班后可追溯的执行人"
        return operator, ""

    def _find_item_pair(
        self,
        plan: dict[str, Any],
        item_id: int,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
        checklist_item = next(
            (item for item in plan["巡检清单"] if int(item.get("id", 0)) == item_id),
            None,
        )
        record = next(
            (item for item in plan["巡检记录明细"] if int(item.get("巡检项ID", 0)) == item_id),
            None,
        )
        if checklist_item is None or record is None:
            return None, None, f"巡检项 {item_id} 不在巡检计划 {plan['巡检计划编号']} 中"
        return checklist_item, record, ""

    def _build_issue(
        self,
        plan_id: int,
        item_id: int,
        issue_no: int,
        description: str,
        values: dict[str, Any],
        operator: str,
    ) -> dict[str, Any]:
        return {
            "问题编号": f"ISS-{plan_id:03d}-{item_id:02d}-{issue_no:02d}",
            "问题描述": description,
            "问题等级": _text(values, "问题等级") or "一般",
            "登记人": operator,
            "登记时间": _now(),
        }

    def _review_errors(self, plan: dict[str, Any]) -> list[str]:
        records = {int(item["巡检项ID"]): item for item in plan["巡检记录明细"]}
        errors: list[str] = []
        for checklist_item in plan["巡检清单"]:
            item_id = int(checklist_item["id"])
            name = checklist_item["巡检项"]
            record = records.get(item_id)
            if record is None:
                errors.append(f"巡检项「{name}」缺少巡检记录明细")
                continue
            if not record.get("执行人") or not record.get("执行时间"):
                errors.append(f"巡检项「{name}」尚未完成执行登记")
            checklist_conclusion = checklist_item.get("清单结论")
            record_conclusion = record.get("记录结论")
            if checklist_conclusion == WAITING or record_conclusion == WAITING:
                errors.append(f"巡检项「{name}」结论未登记完整")
            elif checklist_conclusion != record_conclusion:
                errors.append(
                    f"巡检项「{name}」清单结论「{checklist_conclusion}」与记录结论「{record_conclusion}」对不上"
                )
            if record_conclusion == ABNORMAL and not record.get("问题列表"):
                errors.append(f"巡检项「{name}」结论为异常，但未挂现场问题")
        return errors

    def _has_abnormal_item(self, plan: dict[str, Any]) -> bool:
        return any(
            record.get("记录结论") == ABNORMAL or record.get("问题列表")
            for record in plan["巡检记录明细"]
        )

    def _append_history(
        self,
        plan: dict[str, Any],
        action: str,
        operator: str,
        from_status: str | None,
        to_status: str | None,
        reason: str | None = None,
        *,
        说明: str | None = None,
    ) -> None:
        plan["操作轨迹"].append({
            "动作": action,
            "操作人": operator,
            "时间": _now(),
            "原状态": from_status,
            "新状态": to_status,
            "原因": reason,
            "说明": 说明,
        })
