#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦饭搭子 · 午餐省钱官 —— 凑单最优解引擎
============================================

这是「麦麦饭搭子」Skill 的算法内核：给定一份麦当劳门店菜单、用户手上可用的
优惠券，以及人数 / 预算 / 热量 / 忌口等约束，求解出**实付金额最低**的一餐组合。

它不依赖任何第三方库，也不直接联网：菜单和券由 Skill 通过麦当劳 MCP 的工具
（query-meals / query-store-coupons / available-coupons / list-nutrition-foods …）
拉取后以 JSON 传进来，算完再交回 Agent 去做 calculate-price / create-order。

求解策略（两层）
----------------
1. **快速解 (solve_fast)**：贪心构造保底篮子，再对每张券用有界背包 DP 求
   "花最少的钱把篮子顶过门槛" 的加购方案。秒级出结果，用作剪枝种子。
2. **精确解 (solve_exact)**：以快速解为下界种子，做带剪枝的深度优先搜索。
   剪枝依据：任何分支的实付下界 = 当前小计 - 全局最大可能优惠；一旦该下界
   不低于已有最优解即可整枝剪掉。菜单规模在阈值内时给出**全局最优解**。

菜单特别大（> 22 项）或搜索触顶时会自动退回快速解，并在结果里注明。

许可：本文件是麦当劳程序员节创意开发大赛参赛作品的一部分，仅供学习交流。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

BUCKET = 0.5           # 价格分桶步长（元）
INF = float("inf")
EXACT_MENU_LIMIT = 22  # 超过这个规模不再走精确搜索
NODE_BUDGET = 4_000_000


# --------------------------------------------------------------------------
# 数据模型
# --------------------------------------------------------------------------
@dataclass
class Item:
    """菜单中的一项可售餐品（单品或套餐）。"""

    code: str
    name: str
    price: float
    calories: float = 0.0
    category: str = ""
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        return cls(
            code=str(d.get("code") or d.get("productCode") or ""),
            name=str(d.get("name") or d.get("productName") or ""),
            price=float(d.get("price") or 0.0),
            calories=float(d.get("calories") or d.get("energy") or 0.0),
            category=str(d.get("category") or ""),
            tags=list(d.get("tags") or []),
        )


@dataclass
class Coupon:
    """
    优惠券，支持四种常见形态：

    - threshold   : 满 threshold 减 discount
    - fixed       : 直接立减 discount（可带门槛）
    - percent     : 打 rate 折（0.85 表示 8.5 折），最多减 cap
    - second_half : target_code 第二份半价
    """

    cid: str
    name: str
    kind: str = "threshold"
    threshold: float = 0.0
    discount: float = 0.0
    rate: float = 0.0
    cap: float = INF
    target_code: str = ""
    scope_tags: List[str] = field(default_factory=list)
    stackable: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Coupon":
        cap = d.get("cap")
        return cls(
            cid=str(d.get("id") or d.get("couponId") or ""),
            name=str(d.get("name") or d.get("couponName") or ""),
            kind=str(d.get("kind") or d.get("type") or "threshold").lower(),
            threshold=float(d.get("threshold") or 0.0),
            discount=float(d.get("discount") or 0.0),
            rate=float(d.get("rate") or 0.0),
            cap=float(cap) if cap not in (None, "") else INF,
            target_code=str(d.get("target_code") or d.get("targetCode") or ""),
            scope_tags=list(d.get("scope_tags") or d.get("scopeTags") or []),
            stackable=bool(d.get("stackable") or False),
        )


@dataclass
class Basket:
    """一篮子餐品：code -> 份数。"""

    counts: Dict[str, int] = field(default_factory=dict)

    def items(self, index: Dict[str, Item]) -> List[Item]:
        out: List[Item] = []
        for code, q in self.counts.items():
            if q > 0 and code in index:
                out.extend([index[code]] * q)
        return out

    def subtotal(self, index: Dict[str, Item]) -> float:
        return round(sum(index[c].price * q for c, q in self.counts.items() if c in index), 2)

    def n_items(self) -> int:
        return sum(self.counts.values())

    def calories(self, index: Dict[str, Item]) -> float:
        return round(sum(index[c].calories * q for c, q in self.counts.items() if c in index), 1)

    def copy(self) -> "Basket":
        return Basket(dict(self.counts))

    def add(self, code: str, n: int = 1) -> None:
        self.counts[code] = self.counts.get(code, 0) + n


@dataclass
class Result:
    basket: Basket
    coupon: Optional[Coupon]
    subtotal: float
    discount: float
    payable: float
    calories: float
    n_items: int
    savings_rate: float
    exact: bool = False
    note: str = ""


@dataclass
class Constraints:
    people: int = 1
    budget: float = INF
    max_calories_per_person: float = INF
    min_calories_per_person: float = 0.0
    must_include_tags: List[str] = field(default_factory=list)
    exclude_tags: List[str] = field(default_factory=list)
    max_items: int = 8
    qty_cap: int = 2

    @classmethod
    def from_dict(cls, d: dict) -> "Constraints":
        d = d or {}
        def _num(key, default):
            v = d.get(key)
            return float(v) if v not in (None, "") else default
        return cls(
            people=int(d.get("people") or 1),
            budget=_num("budget", INF),
            max_calories_per_person=_num("max_calories_per_person", INF),
            min_calories_per_person=_num("min_calories_per_person", 0.0),
            must_include_tags=list(d.get("must_include_tags") or []),
            exclude_tags=list(d.get("exclude_tags") or []),
            max_items=int(d.get("max_items") or 8),
            qty_cap=int(d.get("qty_cap") or 2),
        )


# --------------------------------------------------------------------------
# 优惠计算
# --------------------------------------------------------------------------
def scope_match(coupon: Coupon, basket_items: Sequence[Item]) -> bool:
    """券的适用范围是否匹配篮子。scope_tags 为空表示全场通用。"""
    if not coupon.scope_tags:
        return True
    present = {t for it in basket_items for t in it.tags} | {it.category for it in basket_items}
    return any(t in present for t in coupon.scope_tags)


def coupon_discount(coupon: Coupon, basket_items: Sequence[Item]) -> float:
    """某张券作用在给定篮子上的优惠金额（元）。不满足条件返回 0。"""
    subtotal = round(sum(i.price for i in basket_items), 2)
    if not scope_match(coupon, basket_items):
        return 0.0
    k = coupon.kind
    if k in ("threshold", "满减"):
        return round(coupon.discount, 2) if subtotal >= coupon.threshold else 0.0
    if k in ("fixed", "立减"):
        return round(coupon.discount, 2) if subtotal >= coupon.threshold else 0.0
    if k in ("percent", "折扣"):
        return round(min(subtotal * (1.0 - coupon.rate), coupon.cap), 2)
    if k in ("second_half", "第二份半价"):
        n = sum(1 for i in basket_items if i.code == coupon.target_code)
        if n >= 2:
            price = next(i.price for i in basket_items if i.code == coupon.target_code)
            return round(price * 0.5 * (n // 2), 2)
        return 0.0
    return 0.0


def best_coupon(coupons: Iterable[Coupon], basket_items: Sequence[Item]) -> Tuple[Optional[Coupon], float]:
    """在一篮子餐品上挑出优惠力度最大的券（默认一单只用一张券）。"""
    best: Optional[Coupon] = None
    best_d = 0.0
    for c in coupons:
        d = coupon_discount(c, basket_items)
        if d > best_d:
            best, best_d = c, d
    return best, round(best_d, 2)


def max_possible_discount(coupons: Sequence[Coupon], pool: Sequence[Item], cons: Constraints) -> float:
    """
    全局最大可能优惠（用在剪枝里，必须是上界，宁可高估不可低估）。
    用"最贵的满编篮子"来估。
    """
    top = sorted(pool, key=lambda x: -x.price)[: max(cons.max_items, 1)]
    items: List[Item] = []
    for it in top:
        items.extend([it] * cons.qty_cap)
    sub = sum(i.price for i in items)
    best = 0.0
    for c in coupons:
        k = c.kind
        if k in ("threshold", "满减", "fixed", "立减"):
            best = max(best, c.discount)
        elif k in ("percent", "折扣"):
            best = max(best, min(sub * (1.0 - c.rate), c.cap))
        elif k in ("second_half", "第二份半价"):
            price = next((i.price for i in pool if i.code == c.target_code), 0.0)
            best = max(best, price * 0.5 * cons.qty_cap)
    return round(best, 2)


# --------------------------------------------------------------------------
# 预处理与约束校验
# --------------------------------------------------------------------------
def filter_menu(menu: Sequence[Item], cons: Constraints) -> List[Item]:
    """剔除含忌口标签的餐品，并按单价从高到低排序（便于搜索剪枝）。"""
    out: List[Item] = []
    for it in menu:
        blob = set(it.tags) | {it.category, it.name}
        if any(x in blob for x in cons.exclude_tags):
            continue
        if it.price <= 0:
            continue
        out.append(it)
    out.sort(key=lambda x: (-x.price, -x.calories))
    return out


def feasible(basket: Basket, index: Dict[str, Item], cons: Constraints, payable: float) -> Tuple[bool, str]:
    n = basket.n_items()
    if n < cons.people:
        return False, f"份数不足（{n} < {cons.people} 人）"
    if n > cons.max_items:
        return False, f"份数超上限（{n} > {cons.max_items}）"
    items = basket.items(index)
    tags = {t for it in items for t in it.tags}
    missing = [t for t in cons.must_include_tags if t not in tags]
    if missing:
        return False, f"缺少必备品类：{'、'.join(missing)}"
    cal = basket.calories(index)
    if cal > cons.people * cons.max_calories_per_person + 1e-9:
        return False, f"热量超标（{cal} > {cons.people * cons.max_calories_per_person}）"
    if cal < cons.people * cons.min_calories_per_person - 1e-9:
        return False, f"热量不足（{cal} < {cons.people * cons.min_calories_per_person}）"
    if payable > cons.budget + 1e-9:
        return False, f"超预算（实付 {payable} > {cons.budget}）"
    return True, ""


# --------------------------------------------------------------------------
# 第一层：快速解
# --------------------------------------------------------------------------
def _build_base(pool: Sequence[Item], cons: Constraints, must_tags: Sequence[str]) -> Optional[Basket]:
    """贪心构造一个满足硬约束的保底篮子。"""
    index = {it.code: it for it in pool}
    basket = Basket()
    price_asc = sorted(pool, key=lambda x: (x.price, -x.calories))

    for tag in must_tags:
        if any(tag in it.tags for it in basket.items(index)):
            continue
        cands = [it for it in price_asc if tag in it.tags]
        if not cands:
            return None
        basket.add(cands[0].code)

    while basket.n_items() < cons.people:
        if not price_asc:
            return None
        basket.add(price_asc[0].code)

    guard = 0
    while basket.calories(index) < cons.people * cons.min_calories_per_person and guard < 200:
        guard += 1
        cheapest, cheapest_cost = None, INF
        for it in pool:
            if basket.counts.get(it.code, 0) >= cons.qty_cap or it.calories <= 0:
                continue
            if basket.n_items() >= cons.max_items:
                break
            cost = it.price / it.calories
            if cost < cheapest_cost:
                cheapest, cheapest_cost = it, cost
        if cheapest is None:
            break
        basket.add(cheapest.code)
    return basket


def _min_add_to_reach(
    pool: Sequence[Item],
    basket: Basket,
    need: float,
    max_extra_items: int,
    qty_cap: int,
) -> Optional[Basket]:
    """
    在 basket 基础上追加最便宜的若干餐品，使小计 >= 原小计 + need。
    有界背包 DP：dp[i][j] = 用 i 件加购、金额分桶为 j 时的最小花费。
    """
    if need <= 1e-9:
        return basket.copy()
    if max_extra_items <= 0:
        return None

    max_price = max((it.price for it in pool), default=0.0)
    steps = int(math.ceil((need + max_price + BUCKET) / BUCKET))
    dp = [[INF] * (steps + 1) for _ in range(max_extra_items + 1)]
    choice: List[List[Optional[Tuple[str, int]]]] = [[None] * (steps + 1) for _ in range(max_extra_items + 1)]
    dp[0][0] = 0.0

    for i in range(max_extra_items):
        row = dp[i]
        for j in range(steps + 1):
            if row[j] == INF:
                continue
            for it in pool:
                allowed = qty_cap - basket.counts.get(it.code, 0)
                if allowed <= 0:
                    continue
                for q in range(1, allowed + 1):
                    if i + q > max_extra_items:
                        break
                    nj = j + int(round(it.price * q / BUCKET))
                    if nj > steps:
                        continue
                    cost = row[j] + it.price * q
                    if cost < dp[i + q][nj] - 1e-9:
                        dp[i + q][nj] = cost
                        choice[i + q][nj] = (it.code, q)

    target = int(math.ceil(need / BUCKET))
    best_state, best_cost = None, INF
    for i in range(max_extra_items + 1):
        for j in range(target, steps + 1):
            if dp[i][j] < best_cost - 1e-9:
                best_cost, best_state = dp[i][j], (i, j)
    if best_state is None:
        return None

    price_of = {it.code: it.price for it in pool}
    i, j = best_state
    newb = basket.copy()
    while i > 0 and choice[i][j] is not None:
        code, q = choice[i][j]  # type: ignore[misc]
        newb.add(code, q)
        j -= int(round(price_of[code] * q / BUCKET))
        i -= q
    return newb


def solve_fast(menu: Sequence[Item], coupons: Sequence[Coupon], cons: Constraints) -> Optional[Result]:
    """贪心 + DP 的快速解，用作精确搜索的种子，也用于大规模菜单的降级。"""
    pool = filter_menu(menu, cons)
    if not pool:
        return None
    index = {it.code: it for it in pool}

    base = _build_base(pool, cons, cons.must_include_tags)
    if base is None:
        return None

    baskets: List[Basket] = [base.copy()]
    for c in coupons:
        # 若券指定了商品（第二份半价），先把它锚进保底篮子
        anchors = list(cons.must_include_tags)
        if c.kind in ("second_half", "第二份半价") and c.target_code:
            b = base.copy()
            need_cnt = 2 - b.counts.get(c.target_code, 0)
            if need_cnt > 0 and b.n_items() + need_cnt <= cons.max_items:
                b.add(c.target_code, need_cnt)
                baskets.append(b)
                base_for_reach = b
            else:
                base_for_reach = b
        else:
            base_for_reach = base

        need = max(0.0, c.threshold - base_for_reach.subtotal(index))
        extra = cons.max_items - base_for_reach.n_items()
        nb = _min_add_to_reach(pool, base_for_reach, need, extra, cons.qty_cap)
        baskets.append(base_for_reach.copy())
        if nb is not None:
            baskets.append(nb)

    return _pick_best(baskets, index, coupons, cons, exact=False)


def _pick_best(
    baskets: Sequence[Basket],
    index: Dict[str, Item],
    coupons: Sequence[Coupon],
    cons: Constraints,
    exact: bool,
) -> Optional[Result]:
    best: Optional[Result] = None
    for b in baskets:
        items = b.items(index)
        sub = b.subtotal(index)
        c, d = best_coupon(coupons, items)
        payable = round(max(0.0, sub - d), 2)
        ok, _ = feasible(b, index, cons, payable)
        if not ok:
            continue
        cal = b.calories(index)
        res = Result(b, c, sub, d, payable, cal, b.n_items(),
                     round(d / sub, 4) if sub else 0.0, exact=exact)
        if best is None or (res.payable, res.calories, res.n_items) < (best.payable, best.calories, best.n_items):
            best = res
    if best is not None:
        best.note = describe(best, index)
    return best


# --------------------------------------------------------------------------
# 第二层：精确解（带下界剪枝的 DFS）
# --------------------------------------------------------------------------
def solve_exact(
    menu: Sequence[Item],
    coupons: Sequence[Coupon],
    cons: Constraints,
    seed: Optional[Result] = None,
    node_budget: int = NODE_BUDGET,
) -> Optional[Result]:
    """
    全局最优搜索。剪枝依据：任一分支的实付下界 = 当前小计 - 全局最大可能优惠，
    一旦该下界不低于当前最优解，整枝剪掉。节点数超预算则抛 TimeoutError。
    """
    pool = filter_menu(menu, cons)
    if not pool:
        return None
    index = {it.code: it for it in pool}
    codes = [it.code for it in pool]
    prices = [it.price for it in pool]
    cals = [it.calories for it in pool]
    n = len(codes)

    # must 标签位掩码
    must = list(dict.fromkeys(cons.must_include_tags))
    tag_bits = {t: 1 << k for k, t in enumerate(must)}
    full_mask = (1 << len(must)) - 1
    node_mask = []
    for it in pool:
        m = 0
        for t in it.tags:
            if t in tag_bits:
                m |= tag_bits[t]
        node_mask.append(m)
    for t in must:
        if not any(t in it.tags for it in pool):
            return None

    maxD = max_possible_discount(coupons, pool, cons)
    best: Optional[Result] = seed
    best_payable = seed.payable if seed else INF
    counts = [0] * n
    nodes = 0
    budget = node_budget

    class Timeout(Exception):
        pass

    def record(nn: int, sub: float, cal: float) -> None:
        nonlocal best, best_payable
        if nn < cons.people or nn > cons.max_items:
            return
        if cal > cons.people * cons.max_calories_per_person + 1e-9:
            return
        if cal < cons.people * cons.min_calories_per_person - 1e-9:
            return
        if sub > cons.budget + maxD + 1e-9:
            return
        items = [index[codes[k]] for k in range(n) for _ in range(counts[k])]
        c, d = best_coupon(coupons, items)
        payable = round(max(0.0, sub - d), 2)
        if payable > cons.budget + 1e-9:
            return
        if best is None or (payable, cal, nn) < (best.payable, best.calories, best.n_items):
            basket = Basket({codes[k]: counts[k] for k in range(n) if counts[k]})
            best = Result(basket, c, round(sub, 2), d, payable, round(cal, 1), nn,
                          round(d / sub, 4) if sub else 0.0, exact=True)
            best_payable = payable

    def dfs(i: int, nn: int, sub: float, cal: float, mask: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > budget:
            raise Timeout()
        # 下界剪枝
        if sub - maxD >= best_payable - 1e-9:
            return
        if i == n:
            if mask == full_mask:
                record(nn, sub, cal)
            return
        limit = min(cons.qty_cap, cons.max_items - nn)
        # 先试 0 份（小计最小），配合剪枝可快速收敛
        for q in range(0, limit + 1):
            counts[i] = q
            dfs(i + 1, nn + q, sub + prices[i] * q, cal + cals[i] * q,
                mask | node_mask[i] if q else mask)
        counts[i] = 0

    try:
        dfs(0, 0, 0.0, 0.0, 0)
    except Timeout:
        if best is not None:
            best.note = describe(best, index) + "｜搜索触顶，已退回近似最优"
            return best
        return None

    if best is not None:
        best.exact = True
        best.note = describe(best, index)
    return best


def solve(menu: Sequence[Item], coupons: Sequence[Coupon], cons: Constraints, force_fast: bool = False) -> Optional[Result]:
    """对外主入口：优先给精确解，规模过大时退回快速解。"""
    pool = filter_menu(menu, cons)
    fast = solve_fast(menu, coupons, cons)
    if force_fast or len(pool) > EXACT_MENU_LIMIT:
        if fast is not None:
            fast.note = describe(fast, {it.code: it for it in pool}) + "｜菜单规模较大，使用快速解"
        return fast
    exact = solve_exact(menu, coupons, cons, seed=fast)
    return exact or fast


def describe(res: Result, index: Dict[str, Item]) -> str:
    parts = [f"{index[c].name}×{q}" for c, q in sorted(res.basket.counts.items(), key=lambda kv: -index[kv[0]].price)]
    cname = res.coupon.name if res.coupon else "无可用券"
    return f"{' + '.join(parts)}｜券：{cname}"


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------
def render(res: Result, index: Dict[str, Item], cons: Constraints) -> str:
    L: List[str] = []
    L.append("=" * 52)
    L.append("  麦麦饭搭子 · 午餐省钱官   最优方案")
    L.append("=" * 52)
    budget = ("¥%.2f" % cons.budget) if cons.budget < INF else "不限"
    L.append(f"  人数：{cons.people} 人    预算：{budget}")
    L.append("-" * 52)
    for code, q in sorted(res.basket.counts.items(), key=lambda kv: -index[kv[0]].price):
        it = index[code]
        L.append(f"  · {it.name} ×{q:<2}  ¥{it.price * q:>7.2f}   {int(it.calories * q):>5} kcal")
    L.append("-" * 52)
    L.append(f"  小计          ¥{res.subtotal:.2f}")
    if res.coupon:
        L.append(f"  优惠券        -¥{res.discount:.2f}   （{res.coupon.name}）")
    else:
        L.append("  优惠券        无")
    L.append(f"  实付          ¥{res.payable:.2f}   省 {res.savings_rate * 100:.1f}%")
    L.append(f"  总热量        {int(res.calories)} kcal   人均 {int(res.calories / max(cons.people, 1))} kcal")
    L.append(f"  求解方式      {'精确最优 ✅' if res.exact else '快速近似'}")
    L.append("=" * 52)
    return "\n".join(L)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    menu = [Item.from_dict(x) for x in cfg.get("menu", [])]
    coupons = [Coupon.from_dict(x) for x in cfg.get("coupons", [])]
    cons = Constraints.from_dict(cfg.get("constraints") or cfg)
    return menu, coupons, cons, cfg


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="麦麦饭搭子 · 凑单最优解引擎")
    ap.add_argument("--input", "-i", required=True, help="输入 JSON 路径")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    ap.add_argument("--fast", action="store_true", help="只用快速解，跳过精确搜索")
    ap.add_argument("--out", "-o", default="", help="把结果写入文件")
    args = ap.parse_args(argv)

    menu, coupons, cons, _ = load_config(args.input)
    if not menu:
        print("菜单为空：请先通过 MCP 的 query-meals 拉取门店菜单。", file=sys.stderr)
        return 2

    res = solve(menu, coupons, cons, force_fast=args.fast)
    if res is None:
        print("在当前约束下找不到可行方案，建议放宽预算或热量限制。", file=sys.stderr)
        return 3

    index = {it.code: it for it in filter_menu(menu, cons)}
    text_out = render(res, index, cons)

    payload = {
        "basket": res.basket.counts,
        "items": [{"code": c, "name": index[c].name, "price": index[c].price, "qty": q}
                  for c, q in res.basket.counts.items()],
        "coupon": {"id": res.coupon.cid, "name": res.coupon.name} if res.coupon else None,
        "subtotal": res.subtotal,
        "discount": res.discount,
        "payable": res.payable,
        "calories": res.calories,
        "n_items": res.n_items,
        "savings_rate": res.savings_rate,
        "exact": res.exact,
        "summary": res.note,
    }

    if args.json:
        text_out = json.dumps(payload, ensure_ascii=False, indent=2)

    print(text_out)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
