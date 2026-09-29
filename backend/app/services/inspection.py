"""信号设备巡检业务规则。

一份巡检计划由「巡检清单（巡检项）+ 巡检记录明细 + 现场问题 + 流转记录」组成，
计划状态只有三种：待下发 → 执行中 → 已复核；复核不通过时退回执行中，
在巡检记录里留下退回原因，执行人可以刷新后接着干。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "inspection"

STATUS_DRAFT = "待下发"
STATUS_DOING = "执行中"
STATUS_REVIEWED = "已复核"
STATUS_ORDER = [STATUS_DRAFT, STATUS_DOING, STATUS_REVIEWED]

REQUIRED_PLAN_FIELDS = ["计划编号", "巡检名称", "巡检日期", "设备范围", "班组"]
REQUIRED_ITEM_FIELDS = ["巡检项名称"]
# 巡检结论（巡检清单与巡检记录明细共用一套口径，保证两边对得上）
CONCLUSION_NORMAL = "正常"
CONCLUSION_ABNORMAL = "异常"
CONCLUSIONS = [CONCLUSION_NORMAL, CONCLUSION_ABNORMAL]

# 现场问题处理状态
ISSUE_OPEN = "未处理"
ISSUE_DONE = "已处理"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _operator(values: dict[str, Any]) -> str:
    return str(values.get("operator") or values.get("操作人") or "").strip()


def _item_key(item: dict[str, Any]) -> str:
    """同一份计划内的判重键：优先巡检项编号，没有就按巡检项名称。"""
    code = str(item.get("巡检项编号") or "").strip()
    if code:
        return f"编号:{code}"
    return f"名称:{str(item.get('巡检项编号') or item.get('巡检项名称') or '').strip()}"


class InspectionService:
    def _next_item_id(self) -> int:
        """巡检项全局自增 id；用实例计数器避免一次建多项时取到同一最大值。"""
        if not hasattr(self, "_item_seq"):
            self._item_seq = max(
                (
                    int(item.get("id", 0))
                    for plan in store.rows(MODULE)
                    for item in plan.get("items", [])
                ),
                default=0,
            )
        self._item_seq += 1
        return self._item_seq

    def _next_issue_id(self) -> int:
        if not hasattr(self, "_issue_seq"):
            self._issue_seq = max(
                (
                    int(issue.get("id", 0))
                    for plan in store.rows(MODULE)
                    for item in plan.get("items", [])
                    for issue in item.get("问题", [])
                ),
                default=0,
            )
        self._issue_seq += 1
        return self._issue_seq

    # ---------- 读取 ----------
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("计划编号", ""))
                or keyword in str(row.get("巡检名称", ""))
                or keyword in str(row.get("设备范围", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [self._snapshot(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return self._snapshot(row) if row else None

    # ---------- 建计划 ----------
    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """登记巡检计划。计划为空、必填字段或巡检项缺失时不落库，并说明缺什么。"""
        missing = [f for f in REQUIRED_PLAN_FIELDS if not str(values.get(f) or "").strip()]
        raw_items = values.get("items") or values.get("巡检清单") or []
        if not isinstance(raw_items, list) or not raw_items:
            missing.append("巡检清单（至少一个巡检项）")

        item_errors: list[str] = []
        cleaned_items: list[dict[str, Any]] = []
        if isinstance(raw_items, list):
            seen: set[str] = set()
            for index, raw in enumerate(raw_items, start=1):
                item = raw if isinstance(raw, dict) else {}
                name = str(item.get("巡检项名称") or "").strip()
                if not name:
                    item_errors.append(f"第{index}项缺少巡检项名称")
                    continue
                key = _item_key(item)
                if key in seen:
                    item_errors.append(
                        f"巡检项「{item.get('巡检项编号') or name}」在本计划内重复登记"
                    )
                    continue
                seen.add(key)
                cleaned_items.append(self._new_item(item, name))

        if missing or item_errors:
            details = []
            if missing:
                details.append("缺少必填内容：" + "、".join(missing))
            details.extend(item_errors)
            return None, "；".join(details)

        rows = store.rows(MODULE)
        plan_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        plan: dict[str, Any] = {
            "id": plan_id,
            "status": STATUS_DRAFT,
            "pending": True,
            "abnormal": False,
            "计划编号": str(values.get("计划编号") or "").strip(),
            "巡检名称": str(values.get("巡检名称") or "").strip(),
            "巡检日期": str(values.get("巡检日期") or "").strip(),
            "设备范围": str(values.get("设备范围") or "").strip(),
            "班组": str(values.get("班组") or "").strip(),
            "备注": str(values.get("备注") or "").strip(),
            "创建人": _operator(values) or "值班管理员",
            "创建时间": _now(),
            "下发人": None,
            "下发时间": None,
            "复核人": None,
            "复核时间": None,
            "items": cleaned_items,
            "logs": [
                {
                    "action": "登记计划",
                    "operator": _operator(values) or "值班管理员",
                    "time": _now(),
                    "detail": f"登记巡检计划，含 {len(cleaned_items)} 个巡检项",
                }
            ],
        }
        rows.append(plan)
        return self._snapshot(plan), ""

    def _new_item(self, raw: dict[str, Any], name: str) -> dict[str, Any]:
        item_id = self._next_item_id()
        code = str(raw.get("巡检项编号") or "").strip()
        return {
            "id": item_id,
            "巡检项编号": code or f"ITEM-{item_id:04d}",
            "巡检项名称": name,
            "检查内容": str(raw.get("检查内容") or "").strip(),
            "设备编号": str(raw.get("设备编号") or "").strip(),
            # 巡检记录明细：未执行前结论为空
            "结论": None,
            "执行人": None,
            "执行时间": None,
            "问题": [],
        }

    # ---------- 巡检项维护 ----------
    def add_item(self, plan_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"
        if plan["status"] == STATUS_REVIEWED:
            return None, "巡检计划已复核归档，不允许再增删巡检项"

        missing = [f for f in REQUIRED_ITEM_FIELDS if not str(values.get(f) or "").strip()]
        if missing:
            return None, f"缺少必填内容：{'、'.join(missing)}，巡检项未落库"

        candidate = {
            "巡检项编号": str(values.get("巡检项编号") or "").strip(),
            "巡检项名称": str(values.get("巡检项名称") or "").strip(),
        }
        key = _item_key(candidate)
        hit = next((item for item in plan["items"] if _item_key(item) == key), None)
        if hit is not None:
            label = candidate["巡检项编号"] or candidate["巡检项名称"]
            return None, f"巡检项「{label}」在本计划内已登记，不能重复登记"

        item = self._new_item(candidate, candidate["巡检项名称"])
        item["检查内容"] = str(values.get("检查内容") or "").strip()
        item["设备编号"] = str(values.get("设备编号") or "").strip()
        plan["items"].append(item)
        plan["logs"].append({
            "action": "补充巡检项",
            "operator": _operator(values) or "值班管理员",
            "time": _now(),
            "detail": f"补充巡检项「{item['巡检项编号']} {item['巡检项名称']}」",
        })
        return self._snapshot(plan), ""

    # ---------- 巡检记录 ----------
    def save_record(self, plan_id: int, item_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"
        if plan["status"] == STATUS_DRAFT:
            return None, "计划尚未下发，不能登记巡检记录"
        if plan["status"] == STATUS_REVIEWED:
            return None, "巡检计划已复核归档，巡检记录不允许再改动"
        if self._pending_review(plan):
            return None, "计划已提交复核，需等复核通过或退回后才能继续登记"

        item = self._find_item(plan, item_id)
        if item is None:
            return None, f"巡检项 {item_id} 不属于该计划或不存在"

        conclusion = str(values.get("结论") or "").strip()
        if conclusion not in CONCLUSIONS:
            return None, f"巡检结论只能是「{CONCLUSION_NORMAL}」或「{CONCLUSION_ABNORMAL}」"

        operator = _operator(values)
        if not operator:
            return None, "缺少执行人，巡检记录不落库"

        previous = item.get("结论")
        item["结论"] = conclusion
        item["执行人"] = operator
        item["执行时间"] = _now()
        if conclusion == CONCLUSION_NORMAL:
            # 改判正常后，历史现场问题保留但标记清楚（不静默删除）
            for issue in item["问题"]:
                if issue["处理状态"] == ISSUE_OPEN:
                    issue["处理状态"] = ISSUE_DONE
                    issue["处理说明"] = "巡检项改判正常，随单关闭"
        plan["abnormal"] = self._has_abnormal(plan)
        detail = f"巡检项「{item['巡检项名称']}」结论：{conclusion}"
        if previous and previous != conclusion:
            detail += f"（原结论：{previous}）"
        plan["logs"].append({
            "action": "登记巡检记录",
            "operator": operator,
            "time": item["执行时间"],
            "detail": detail,
        })
        return self._snapshot(plan), ""

    # ---------- 现场问题：挂到具体巡检项 ----------
    def add_issue(self, plan_id: int, item_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"
        if plan["status"] != STATUS_DOING:
            return None, "只有执行中的计划可以登记现场问题"
        if self._pending_review(plan):
            return None, "计划已提交复核，需等复核结论后再登记问题"

        item = self._find_item(plan, item_id)
        if item is None:
            return None, f"巡检项 {item_id} 不属于该计划或不存在，问题未挂载"

        description = str(values.get("问题描述") or "").strip()
        if not description:
            return None, "缺少问题描述，现场问题不落库"
        operator = _operator(values)
        if not operator:
            return None, "缺少登记人，现场问题不落库"

        issue_id = self._next_issue_id()
        issue = {
            "id": issue_id,
            "问题描述": description,
            "严重程度": str(values.get("严重程度") or "一般").strip() or "一般",
            "登记人": operator,
            "登记时间": _now(),
            "处理状态": ISSUE_OPEN,
            "处理人": None,
            "处理时间": None,
            "处理说明": None,
        }
        item["问题"].append(issue)
        if item.get("结论") != CONCLUSION_ABNORMAL:
            item["结论"] = CONCLUSION_ABNORMAL
            item["执行人"] = item.get("执行人") or operator
            item["执行时间"] = item.get("执行时间") or _now()
        plan["abnormal"] = True
        plan["logs"].append({
            "action": "登记现场问题",
            "operator": operator,
            "time": issue["登记时间"],
            "detail": f"巡检项「{item['巡检项名称']}」登记问题：{description}",
        })
        return self._snapshot(plan), ""

    def resolve_issue(self, plan_id: int, item_id: int, issue_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"
        if plan["status"] == STATUS_REVIEWED:
            return None, "巡检计划已复核归档，问题处理记录不允许再改动"
        item = self._find_item(plan, item_id)
        if item is None:
            return None, f"巡检项 {item_id} 不存在"
        issue = next((x for x in item["问题"] if int(x.get("id", 0)) == issue_id), None)
        if issue is None:
            return None, f"问题 {issue_id} 未挂在该巡检项下"
        note = str(values.get("处理说明") or "").strip()
        if not note:
            return None, "缺少处理说明"
        operator = _operator(values)
        if not operator:
            return None, "缺少处理人"
        issue["处理状态"] = ISSUE_DONE
        issue["处理人"] = operator
        issue["处理时间"] = _now()
        issue["处理说明"] = note
        plan["logs"].append({
            "action": "处理现场问题",
            "operator": operator,
            "time": issue["处理时间"],
            "detail": f"巡检项「{item['巡检项名称']}」问题处理完成：{note}",
        })
        return self._snapshot(plan), ""

    # ---------- 状态流转 ----------
    def run_action(self, plan_id: int, action: str, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"

        if action == "下发":
            if plan["status"] == STATUS_REVIEWED:
                return None, "巡检计划已复核归档，不允许再下发或改动"
            if plan["status"] != STATUS_DRAFT:
                return None, f"当前状态为「{plan['status']}」，不能重复下发"
            operator = _operator(values)
            if not operator:
                return None, "缺少下发人"
            plan["status"] = STATUS_DOING
            plan["下发人"] = operator
            plan["下发时间"] = _now()
            self._append_log(plan, "下发", operator, f"计划下发至{plan['班组']}开始执行")
            return self._snapshot(plan), "巡检计划已下发，进入执行中"

        if action == "提交复核":
            if plan["status"] == STATUS_DRAFT:
                return None, "计划尚未下发，不能提交复核"
            if plan["status"] == STATUS_REVIEWED:
                return None, "巡检计划已复核归档"
            if self._pending_review(plan):
                return None, "计划已在复核队列，请勿重复提交"
            operator = _operator(values)
            if not operator:
                return None, "缺少提交人"
            errors = self.check_consistency(plan)
            if errors:
                return None, "清单与记录对不上，复核已拦下：" + "；".join(errors)
            plan["logs"].append({
                "action": "提交复核",
                "operator": operator,
                "time": _now(),
                "detail": "全部巡检项执行完毕，提交复核",
            })
            plan["reviews"] = plan.get("reviews", [])
            plan["reviews"].append({
                "round": len(plan["reviews"]) + 1,
                "结论": None,
                "提交人": operator,
                "提交时间": _now(),
                "复核人": None,
                "复核时间": None,
                "退回原因": None,
            })
            return self._snapshot(plan), "已提交复核，等待复核结论"

        if action == "复核通过":
            if plan["status"] != STATUS_DOING or not self._pending_review(plan):
                return None, "没有待复核的提交，不能复核通过"
            operator = _operator(values)
            if not operator:
                return None, "缺少复核人"
            review = plan["reviews"][-1]
            review["结论"] = "通过"
            review["复核人"] = operator
            review["复核时间"] = _now()
            plan["status"] = STATUS_REVIEWED
            plan["pending"] = False
            plan["复核人"] = operator
            plan["复核时间"] = review["复核时间"]
            self._append_log(plan, "复核通过", operator, "复核通过，计划归档")
            return self._snapshot(plan), "复核通过，巡检计划已归档"

        if action == "复核退回":
            if plan["status"] != STATUS_DOING or not self._pending_review(plan):
                return None, "没有待复核的提交，不能退回"
            reason = str(values.get("退回原因") or values.get("reason") or "").strip()
            if not reason:
                return None, "复核退回必须写清退回原因"
            operator = _operator(values)
            if not operator:
                return None, "缺少复核人"
            review = plan["reviews"][-1]
            review["结论"] = "退回"
            review["复核人"] = operator
            review["复核时间"] = _now()
            review["退回原因"] = reason
            # 状态回到执行中，退回原因写进巡检记录（流转记录），执行人刷新即可看到
            self._append_log(
                plan,
                "复核退回",
                operator,
                f"复核未通过，退回执行中。原因：{reason}",
            )
            return self._snapshot(plan), f"已退回执行中：{reason}"

        return None, f"动作「{action}」不属于信号设备巡检可执行范围"

    # ---------- 一致性核对：清单 vs 记录明细 ----------
    def check_consistency(self, plan: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        items = plan.get("items", [])
        if not items:
            return ["巡检清单为空"]
        for item in items:
            label = f"{item.get('巡检项编号', '')} {item.get('巡检项名称', '')}".strip()
            conclusion = item.get("结论")
            if not conclusion:
                errors.append(f"巡检项「{label}」尚未登记巡检结论")
            elif conclusion not in CONCLUSIONS:
                errors.append(f"巡检项「{label}」结论「{conclusion}」不在允许范围内")
            open_issues = [x for x in item.get("问题", []) if x.get("处理状态") == ISSUE_OPEN]
            if open_issues and conclusion != CONCLUSION_ABNORMAL:
                errors.append(
                    f"巡检项「{label}」挂有 {len(open_issues)} 条未处理问题，但结论不是异常"
                )
            if conclusion == CONCLUSION_ABNORMAL and not item.get("问题"):
                errors.append(f"巡检项「{label}」结论为异常，但未登记现场问题")
            if conclusion and not item.get("执行人"):
                errors.append(f"巡检项「{label}」缺少执行人")
        return errors

    def consistency_report(self, plan_id: int) -> tuple[dict[str, Any] | None, str]:
        plan = store.find(MODULE, plan_id)
        if plan is None:
            return None, f"巡检计划 {plan_id} 不存在"
        errors = self.check_consistency(plan)
        return {
            "plan_id": plan_id,
            "ok": not errors,
            "errors": errors,
            "items": [
                {
                    "巡检项编号": item.get("巡检项编号"),
                    "巡检项名称": item.get("巡检项名称"),
                    "结论": item.get("结论"),
                    "执行人": item.get("执行人"),
                    "问题数": len(item.get("问题", [])),
                }
                for item in plan.get("items", [])
            ],
        }, ""

    # ---------- 内部工具 ----------
    def _find_item(self, plan: dict[str, Any], item_id: int) -> dict[str, Any] | None:
        return next((x for x in plan.get("items", []) if int(x.get("id", 0)) == item_id), None)

    def _pending_review(self, plan: dict[str, Any]) -> bool:
        reviews = plan.get("reviews") or []
        return bool(reviews and reviews[-1].get("结论") is None)

    def _has_abnormal(self, plan: dict[str, Any]) -> bool:
        return any(
            item.get("结论") == CONCLUSION_ABNORMAL or item.get("问题")
            for item in plan.get("items", [])
        )

    def _append_log(self, plan: dict[str, Any], action: str, operator: str, detail: str) -> None:
        plan.setdefault("logs", []).append(
            {"action": action, "operator": operator, "time": _now(), "detail": detail}
        )

    def _snapshot(self, plan: dict[str, Any]) -> dict[str, Any]:
        """给前端的视图：补出列表用的派生字段，不改动仓库里的原始计划。"""
        snap = dict(plan)
        items = plan.get("items", [])
        total = len(items)
        done = sum(1 for item in items if item.get("结论"))
        abnormal = sum(1 for item in items if item.get("结论") == CONCLUSION_ABNORMAL)
        issues = sum(len(item.get("问题", [])) for item in items)
        open_issues = sum(
            1 for item in items for x in item.get("问题", []) if x.get("处理状态") == ISSUE_OPEN
        )
        snap["巡检项数"] = total
        snap["已检项数"] = done
        snap["异常项数"] = abnormal
        snap["问题数"] = issues
        snap["未处理问题"] = open_issues
        snap["待复核"] = self._pending_review(plan)
        snap["进度"] = f"{done}/{total}"
        if self._pending_review(plan):
            snap["计划状态"] = "待复核"
        else:
            snap["计划状态"] = plan.get("status")
        snap["abnormal"] = self._has_abnormal(plan)
        return snap


# ---------- 示例数据 ----------
def _seed() -> None:
    """首次加载时铺几条不同阶段的巡检计划，方便交班后直接看到效果。"""
    if store.rows(MODULE):
        return

    def item(idx: int, name: str, conclusion: str | None, operator: str | None, issues: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return {
            "id": idx,
            "巡检项编号": f"ITEM-{idx:04d}",
            "巡检项名称": name,
            "检查内容": f"{name}外观、电气特性与机械强度检查",
            "设备编号": f"S-{idx:03d}",
            "结论": conclusion,
            "执行人": operator,
            "执行时间": "2026-09-29 09:30" if operator else None,
            "问题": issues or [],
        }

    plans = [
        {
            "id": 1,
            "status": STATUS_REVIEWED,
            "pending": False,
            "abnormal": True,
            "计划编号": "XJ-2026-0918",
            "巡检名称": "9月中旬信号设备例行巡检",
            "巡检日期": "2026-09-18",
            "设备范围": "甲站Ⅰ场信号机、转辙机",
            "班组": "信号一工班",
            "备注": "已归档样例，用于验证归档后不可改",
            "创建人": "王建国",
            "创建时间": "2026-09-17 17:40",
            "下发人": "王建国",
            "下发时间": "2026-09-18 08:05",
            "复核人": "李审核",
            "复核时间": "2026-09-18 16:20",
            "items": [
                item(1, "进站信号机显示距离测试", CONCLUSION_NORMAL, "张执行"),
                item(2, "S3信号机灯泡寿命检查", CONCLUSION_ABNORMAL, "张执行", [
                    {
                        "id": 1,
                        "问题描述": "主灯丝累计点灯时长接近寿命上限",
                        "严重程度": "一般",
                        "登记人": "张执行",
                        "登记时间": "2026-09-18 10:12",
                        "处理状态": ISSUE_DONE,
                        "处理人": "赵维修",
                        "处理时间": "2026-09-18 14:30",
                        "处理说明": "更换主灯泡并复测合格",
                    }
                ]),
                item(3, "1#道岔转辙机动作电流测试", CONCLUSION_NORMAL, "陈巡检"),
            ],
            "reviews": [
                {
                    "round": 1,
                    "结论": "通过",
                    "提交人": "张执行",
                    "提交时间": "2026-09-18 15:10",
                    "复核人": "李审核",
                    "复核时间": "2026-09-18 16:20",
                    "退回原因": None,
                }
            ],
            "logs": [
                {"action": "登记计划", "operator": "王建国", "time": "2026-09-17 17:40", "detail": "登记巡检计划，含 3 个巡检项"},
                {"action": "下发", "operator": "王建国", "time": "2026-09-18 08:05", "detail": "计划下发至信号一工班开始执行"},
                {"action": "登记现场问题", "operator": "张执行", "time": "2026-09-18 10:12", "detail": "巡检项「S3信号机灯泡寿命检查」登记问题：主灯丝累计点灯时长接近寿命上限"},
                {"action": "提交复核", "operator": "张执行", "time": "2026-09-18 15:10", "detail": "全部巡检项执行完毕，提交复核"},
                {"action": "复核通过", "operator": "李审核", "time": "2026-09-18 16:20", "detail": "复核通过，计划归档"},
            ],
        },
        {
            "id": 2,
            "status": STATUS_DOING,
            "pending": True,
            "abnormal": True,
            "计划编号": "XJ-2026-0929",
            "巡检名称": "9月下旬信号设备例行巡检",
            "巡检日期": "2026-09-29",
            "设备范围": "乙站Ⅱ场轨道电路、应答器",
            "班组": "信号二工班",
            "备注": "上一班已检两项，交班后继续",
            "创建人": "王建国",
            "创建时间": "2026-09-28 17:20",
            "下发人": "王建国",
            "下发时间": "2026-09-29 08:00",
            "复核人": None,
            "复核时间": None,
            "items": [
                item(4, "15-23DG轨道电路轨面电压测试", CONCLUSION_NORMAL, "张执行"),
                item(5, "应答器报文读取校核", CONCLUSION_ABNORMAL, "张执行", [
                    {
                        "id": 2,
                        "问题描述": "B-205应答器接收电平低于门限",
                        "严重程度": "严重",
                        "登记人": "张执行",
                        "登记时间": "2026-09-29 10:45",
                        "处理状态": ISSUE_OPEN,
                        "处理人": None,
                        "处理时间": None,
                        "处理说明": None,
                    }
                ]),
                item(6, "计轴磁头安装间隙检查", None, None),
                item(7, "电缆盒绝缘电阻摇测", None, None),
            ],
            "reviews": [],
            "logs": [
                {"action": "登记计划", "operator": "王建国", "time": "2026-09-28 17:20", "detail": "登记巡检计划，含 4 个巡检项"},
                {"action": "下发", "operator": "王建国", "time": "2026-09-29 08:00", "detail": "计划下发至信号二工班开始执行"},
                {"action": "登记巡检记录", "operator": "张执行", "time": "2026-09-29 09:30", "detail": "巡检项「15-23DG轨道电路轨面电压测试」结论：正常"},
                {"action": "登记现场问题", "operator": "张执行", "time": "2026-09-29 10:45", "detail": "巡检项「应答器报文读取校核」登记问题：B-205应答器接收电平低于门限"},
            ],
        },
        {
            "id": 3,
            "status": STATUS_DRAFT,
            "pending": True,
            "abnormal": False,
            "计划编号": "XJ-2026-1006",
            "巡检名称": "国庆前信号设备专项巡检",
            "巡检日期": "2026-10-06",
            "设备范围": "甲乙站全站信号机",
            "班组": "信号一工班",
            "备注": "",
            "创建人": "王建国",
            "创建时间": "2026-09-29 11:00",
            "下发人": None,
            "下发时间": None,
            "复核人": None,
            "复核时间": None,
            "items": [
                item(8, "X1信号机灯端电压测量", None, None),
                item(9, "X2信号机灯端电压测量", None, None),
            ],
            "reviews": [],
            "logs": [
                {"action": "登记计划", "operator": "王建国", "time": "2026-09-29 11:00", "detail": "登记巡检计划，含 2 个巡检项"},
            ],
        },
        {
            "id": 4,
            "status": STATUS_DOING,
            "pending": True,
            "abnormal": False,
            "计划编号": "XJ-2026-0928-R",
            "巡检名称": "电源屏专项巡检（复核退回样例）",
            "巡检日期": "2026-09-28",
            "设备范围": "丙站信号电源屏",
            "班组": "信号三工班",
            "备注": "首轮复核被退回，刷新后可见退回原因",
            "创建人": "王建国",
            "创建时间": "2026-09-28 08:30",
            "下发人": "王建国",
            "下发时间": "2026-09-28 09:00",
            "复核人": None,
            "复核时间": None,
            "items": [
                item(10, "电源屏Ⅰ路输入电压测试", CONCLUSION_NORMAL, "孙巡检"),
                item(11, "电源屏Ⅱ路切换试验", CONCLUSION_NORMAL, "孙巡检"),
            ],
            "reviews": [
                {
                    "round": 1,
                    "结论": "退回",
                    "提交人": "孙巡检",
                    "提交时间": "2026-09-28 15:00",
                    "复核人": "李审核",
                    "复核时间": "2026-09-28 16:00",
                    "退回原因": "Ⅱ路切换试验未记录切换时间，且无切换前后电压数据，请补测后重新提交",
                }
            ],
            "logs": [
                {"action": "登记计划", "operator": "王建国", "time": "2026-09-28 08:30", "detail": "登记巡检计划，含 2 个巡检项"},
                {"action": "下发", "operator": "王建国", "time": "2026-09-28 09:00", "detail": "计划下发至信号三工班开始执行"},
                {"action": "提交复核", "operator": "孙巡检", "time": "2026-09-28 15:00", "detail": "全部巡检项执行完毕，提交复核"},
                {"action": "复核退回", "operator": "李审核", "time": "2026-09-28 16:00", "detail": "复核未通过，退回执行中。原因：Ⅱ路切换试验未记录切换时间，且无切换前后电压数据，请补测后重新提交"},
            ],
        },
    ]
    store.rows(MODULE).extend(plans)


_seed()
