# 麦麦饭搭子 · 午餐省钱官

> 一句话说出"几个人、多少钱、不吃什么"，自动算出**实付最低**的一餐组合。

麦当劳程序员节创意开发大赛参赛作品 · 基于麦当劳 MCP 构建

---

## 为什么需要它

中午 12 点，你只有 40 分钟和 40 块钱。

打开麦当劳小程序，菜单几十项，券包七八张：满 30 减 7、满 45 减 12、板烧第二份半价、
小食满 20 减 5…… 你隐约觉得"好像凑个 45 更划算"，但到底凑哪几样、凑完人均多少卡路里、
最后实付多少钱，没人算得清。于是大多数人的选择是：随便点一个套餐，然后继续饿着或者继续胖着。

**「麦麦饭搭子」把这件纠结事变成一个可以求解的优化问题：**

> 给定菜单、可用的券、人数 / 预算 / 热量 / 忌口等约束，
> 找出**实付金额最低**的那一篮餐品。

它不是在"推荐套餐"，而是在**解一道带约束的组合优化题**——包括帮你判断
"为了用这张券多买两样，到底值不值"。

## 目标用户

- **学生党**：预算敏感，愿意为了省 8 块钱多走两步、多想一秒。
- **上班族**：午休时间短，希望点餐决策一次到位，不想在券包里翻来覆去。

## 效果示例

场景：2 个人、总预算 50 元、每人至少 500 kcal、不吃牛肉、要有主食和饮品，
门店有 17 项可售餐品、5 张券。

```bash
python scripts/optimize.py --input examples/lunch_for_two.json
```

```
====================================================
  麦麦饭搭子 · 午餐省钱官   最优方案
====================================================
  人数：2 人    预算：¥50.00
----------------------------------------------------
  · 麦香鱼套餐 ×1   ¥  27.00     640 kcal
  · 小薯条 ×2       ¥  18.00     460 kcal
----------------------------------------------------
  小计          ¥45.00
  优惠券        -¥12.00   （满 45 减 12）
  实付          ¥33.00   省 26.7%
  总热量        1100 kcal   人均 550 kcal
  求解方式      精确最优 ✅
====================================================
```

同样的约束下，"看着像最省"的直觉方案是点两套麦香鱼套餐（54 元，还超预算），
或者裸点最便宜的主食（32 元但人均只有 380 kcal，下午三点就饿）。
求解器给出的 33 元方案，恰好卡在 45 元满减门槛上——这就是算法存在的意义。

## 安装与使用

### 1. 申请麦当劳 MCP Token

按 [麦当劳 MCP Server 使用指南](https://github.com/M-China/mcd-mcp-server) 的说明，
用手机号登录后申请 MCP Token。

### 2. 在 WorkBuddy 中配置 MCP

左侧边栏【专家·技能·连接器】→【连接器】→ 右上角【自定义连接器】→【配置 MCP】，
填入：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN"
      }
    }
  }
}
```

把 `YOUR_MCP_TOKEN` 换成你自己的 Token，保存后回到【自定义连接器】把 `mcd-mcp` 启用。

> ⚠️ **不要把真实 Token 写进任何提交到仓库的文件。** 本仓库所有示例配置都使用
> `YOUR_MCP_TOKEN` 占位符，符合参赛声明的信息安全要求。

### 3. 载入本 Skill

把本目录（`SKILL.md` 在根目录）放入 WorkBuddy 的 Skill 目录：

- 用户级：`~/.workbuddy/skills/mcmeal-budget-mate/`
- 或项目级：`<项目>/.workbuddy/skills/mcmeal-budget-mate/`

然后在对话里直接说需求即可：

> 帮我用麦当劳点个午饭，两个人，一共不超过 50 块，不吃牛肉，要吃得饱一点。

### 4. 单独跑算法引擎（可选）

算法内核不依赖 MCP、不联网，可以离线跑：

```bash
# 需要 Python 3.8+
python scripts/optimize.py --input examples/lunch_for_two.json
python scripts/optimize.py --input examples/lunch_for_two.json --json   # 机器可读
python scripts/optimize.py --input examples/lunch_for_two.json --fast   # 只跑快速解
```

## 输入 JSON 结构

```json
{
  "constraints": {
    "people": 2,
    "budget": 50,
    "min_calories_per_person": 500,
    "max_calories_per_person": 900,
    "must_include_tags": ["主食", "饮品"],
    "exclude_tags": ["含牛肉"],
    "max_items": 8,
    "qty_cap": 2
  },
  "menu": [
    {"code": "D001", "name": "板烧鸡腿堡", "price": 22.0, "calories": 470, "tags": ["主食"]}
  ],
  "coupons": [
    {"id": "CP-01", "name": "满30减7", "kind": "threshold", "threshold": 30, "discount": 7},
    {"id": "CP-02", "name": "板烧第二份半价", "kind": "second_half", "target_code": "D001"}
  ]
}
```

支持的券类型：`threshold`（满减）、`fixed`（立减）、`percent`（折扣）、`second_half`（第二份半价）。

## 算法说明

算法内核在 `scripts/optimize.py`，分两层：

1. **快速解** —— 贪心构造保底篮子，再对每张券用有界背包 DP 求"花最少的钱顶过门槛"
   的加购方案。秒级出结果。
2. **精确解** —— 以快速解为下界种子，做带剪枝的深度优先搜索。剪枝依据：
   任一分支的实付下界 = 当前小计 − 全局最大可能优惠；下界不低于当前最优解即整枝剪掉。

菜单规模 > 22 项时自动退回快速解，并在结果中注明，避免搜索爆炸。

**正确性是被验证过的**，不是拍脑袋：

```bash
python tests/test_optimize.py
```

`tests/test_optimize.py` 里除了 10 个功能用例，还有一组**随机对拍**：
随机生成小规模菜单和券，用一份独立实现的暴力枚举作为标准答案，
逐例比对精确解的实付金额，确保剪枝不会漏掉更优解。

## 目录结构

```
mcmeal-budget-mate/
├── SKILL.md                  # WorkBuddy Skill 主入口（工作流程编排）
├── README.md                 # 本文件：项目介绍、安装、使用示例
├── MCP_INTEGRATION.md        # 麦当劳 MCP 的接入说明、工具清单与调用流程
├── CONTEST_DECLARATION.md    # 参赛声明（官方原文，未做任何改动）
├── workbuddy.md              # 使用 WorkBuddy 开发本项目的对话上下文
├── scripts/
│   └── optimize.py           # 凑单最优解引擎（核心算法）
├── tests/
│   └── test_optimize.py      # 单元测试 + 随机对拍
├── examples/
│   └── lunch_for_two.json    # 可离线运行的示例输入
└── mcp.example.json          # MCP 配置模板（占位符，无真实 Token）
```

## 项目创建时间

本仓库创建于 2026 年 10 月，符合活动对项目创建时间的要求。

## 免责声明

本项目为麦当劳程序员节创意开发大赛参赛作品，由参赛者独立开发，非麦当劳官方产品。
项目输出仅供参考，不构成医疗、营养或其他专业建议；餐品信息、价格及供应状态以
麦当劳官方渠道的实时结果为准。完整声明见 [CONTEST_DECLARATION.md](CONTEST_DECLARATION.md)。
