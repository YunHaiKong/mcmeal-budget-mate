#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦麦饭搭子 · 单元测试与随机对拍
================================

运行：python tests/test_optimize.py

- 单元测试覆盖：满减券、第二份半价、折扣券、忌口过滤、热量上下限、预算约束。
- 随机对拍：随机生成小规模菜单与券，用**独立实现的暴力枚举**作为标准答案，
  与 optimize.solve 的精确解逐例比对，确保剪枝搜索不会漏掉更优解。
"""

from __future__ import annotations

import itertools
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import optimize as opt  # noqa: E402


def brute_force(menu, coupons, cons):
    """独立实现的暴力枚举，作为对拍标准答案。"""
    pool = opt.filter_menu(menu, cons)
    if not pool:
        return None
    index = {it.code: it for it in pool}
    codes = [it.code for it in pool]
    best = None

    # 枚举每个 code 的份数（0..qty_cap），总份数 <= max_items
    ranges = [range(0, cons.qty_cap + 1) for _ in codes]
    for combo in itertools.product(*ranges):
        if sum(combo) == 0 or sum(combo) > cons.max_items:
            continue
        basket = opt.Basket({c: q for c, q in zip(codes, combo) if q})
        items = basket.items(index)
        sub = basket.subtotal(index)
        _c, d = opt.best_coupon(coupons, items)
        payable = round(max(0.0, sub - d), 2)
        ok, _ = opt.feasible(basket, index, cons, payable)
        if not ok:
            continue
        cal = basket.calories(index)
        cand = (payable, cal, basket.n_items())
        if best is None or cand < best[0]:
            best = (cand, basket, payable)
    return best


def mk(code, name, price, cal, tags):
    return opt.Item(code=code, name=name, price=price, calories=cal, tags=tags)


DEMO_MENU = [
    mk("D001", "板烧鸡腿堡", 22.0, 470, ["主食"]),
    mk("D002", "巨无霸", 25.0, 520, ["主食", "含牛肉"]),
    mk("D003", "麦辣鸡腿堡", 21.0, 490, ["主食"]),
    mk("D005", "麦香鱼", 16.0, 340, ["主食"]),
    mk("S001", "中薯条", 11.5, 340, ["小食"]),
    mk("S002", "小薯条", 9.0, 230, ["小食"]),
    mk("S004", "玉米杯", 8.0, 90, ["小食", "低卡"]),
    mk("R002", "小可乐", 8.0, 110, ["饮品"]),
    mk("R003", "无糖可乐", 9.5, 1, ["饮品", "低卡"]),
    mk("C002", "麦香鱼套餐", 27.0, 640, ["主食", "套餐", "小食", "饮品"]),
]


class TestBasics(unittest.TestCase):
    def test_threshold_coupon(self):
        # 必须同时有主食/饮品/小食且 3 份起，最低小计 16+8+8=32，用券后 25
        cons = opt.Constraints(people=3, budget=45, max_items=6,
                               must_include_tags=["主食", "饮品", "小食"])
        coupons = [opt.Coupon(cid="A", name="满30减7", kind="threshold", threshold=30, discount=7)]
        res = opt.solve(DEMO_MENU, coupons, cons)
        self.assertIsNotNone(res)
        self.assertTrue(res.exact)
        self.assertEqual(res.coupon.cid, "A")
        self.assertAlmostEqual(res.payable, 25.0, places=6)

    def test_coupon_not_worth_it(self):
        """为了凑门槛多买东西反而更贵时，求解器应当选择不用券。"""
        cons = opt.Constraints(people=1, budget=40, max_items=4, must_include_tags=["主食"])
        coupons = [opt.Coupon(cid="A", name="满30减7", kind="threshold", threshold=30, discount=7)]
        res = opt.solve(DEMO_MENU, coupons, cons)
        self.assertIsNotNone(res)
        self.assertIsNone(res.coupon)          # 16 元的麦香鱼裸买最划算
        self.assertAlmostEqual(res.payable, 16.0, places=6)

    def test_second_half(self):
        # 2 人、每人至少 300 kcal -> 麦香鱼×2 = 32 元，第二份半价后 24 元
        cons = opt.Constraints(people=2, budget=40, max_items=4,
                               must_include_tags=["主食"], min_calories_per_person=300)
        coupons = [opt.Coupon(cid="B", name="麦香鱼第二份半价", kind="second_half", target_code="D005")]
        res = opt.solve(DEMO_MENU, coupons, cons)
        self.assertEqual(res.coupon.cid, "B")
        self.assertGreaterEqual(res.basket.counts.get("D005", 0), 2)
        self.assertAlmostEqual(res.payable, 24.0, places=6)

    def test_percent_coupon(self):
        cons = opt.Constraints(people=2, budget=60, max_items=6, must_include_tags=["主食"])
        coupons = [opt.Coupon(cid="C", name="全场9折", kind="percent", rate=0.9, cap=6)]
        res = opt.solve(DEMO_MENU, coupons, cons)
        self.assertIsNotNone(res)
        self.assertLess(res.payable, res.subtotal)

    def test_exclude_tags(self):
        cons = opt.Constraints(people=2, budget=80, max_items=4,
                               must_include_tags=["主食"], exclude_tags=["含牛肉"])
        res = opt.solve(DEMO_MENU, [], cons)
        self.assertNotIn("D002", res.basket.counts)

    def test_calorie_ceiling(self):
        cons = opt.Constraints(people=1, budget=80, max_items=4,
                               must_include_tags=["主食"], max_calories_per_person=450)
        res = opt.solve(DEMO_MENU, [], cons)
        self.assertLessEqual(res.calories, 450)

    def test_calorie_floor(self):
        cons = opt.Constraints(people=2, budget=200, max_items=6,
                               min_calories_per_person=800)
        res = opt.solve(DEMO_MENU, [], cons)
        self.assertGreaterEqual(res.calories, 1600)

    def test_tight_budget_infeasible(self):
        cons = opt.Constraints(people=1, budget=5, max_items=4, must_include_tags=["主食"])
        self.assertIsNone(opt.solve(DEMO_MENU, [], cons))

    def test_no_coupon(self):
        cons = opt.Constraints(people=1, budget=40, max_items=2, must_include_tags=["主食"])
        res = opt.solve(DEMO_MENU, [], cons)
        self.assertIsNone(res.coupon)
        self.assertEqual(res.discount, 0.0)


class TestRandomCrossCheck(unittest.TestCase):
    """随机对拍：与独立暴力枚举比对，20 例。"""

    def test_random_instances(self):
        rng = random.Random(20261011)
        for case in range(20):
            n = rng.randint(5, 9)
            menu = []
            for i in range(n):
                menu.append(mk(
                    f"X{i}", f"商品{i}",
                    round(rng.choice([8, 9, 9.5, 11, 12, 16, 17, 22, 25, 32]) * 1.0, 2),
                    rng.choice([90, 150, 230, 340, 430, 490, 520, 640, 810]),
                    rng.choice([["主食"], ["小食"], ["饮品"], ["主食", "套餐"]]),
                ))
            coupons = []
            for j in range(rng.randint(0, 3)):
                kind = rng.choice(["threshold", "threshold", "percent", "second_half"])
                if kind == "threshold":
                    coupons.append(opt.Coupon(cid=f"P{j}", name=f"满减{j}", kind="threshold",
                                              threshold=rng.choice([25, 30, 45]), discount=rng.choice([5, 7, 12])))
                elif kind == "percent":
                    coupons.append(opt.Coupon(cid=f"P{j}", name=f"折扣{j}", kind="percent",
                                              rate=0.9, cap=6))
                else:
                    coupons.append(opt.Coupon(cid=f"P{j}", name=f"半价{j}", kind="second_half",
                                              target_code=menu[0].code))
            cons = opt.Constraints(
                people=rng.randint(1, 2),
                budget=rng.choice([30, 40, 50, 80, 999]),
                max_items=rng.randint(2, 5),
                qty_cap=2,
                must_include_tags=rng.choice([[], ["主食"], ["主食", "饮品"]]),
            )
            with self.subTest(case=case):
                bf = brute_force(menu, coupons, cons)
                got = opt.solve(menu, coupons, cons)
                if bf is None:
                    self.assertIsNone(got, f"case{case} 暴力枚举无解但搜索给出了解")
                else:
                    self.assertIsNotNone(got, f"case{case} 暴力枚举有解但搜索无解")
                    self.assertAlmostEqual(
                        got.payable, bf[2], places=6,
                        msg=f"case{case} 实付不一致：搜索={got.payable} 暴力={bf[2]}",
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
