# HelloAgents 智能旅行助手 🌍✈️

基于 HelloAgents 框架构建的智能旅行规划助手，集成高德地图 MCP 服务，提供个性化的旅行计划生成、可视化展示与分享能力。

## ✨ 功能特点

- 🤖 **AI 驱动的旅行规划**：基于 HelloAgents 框架的 SimpleAgent，智能生成详细的多日旅程
- 🗺️ **高德地图集成**：通过 MCP 协议接入高德地图服务，支持景点搜索、路线规划、天气查询、地图可视化
- 🧠 **智能工具调用**：Agent 自动调用高德地图 MCP 工具，获取实时 POI、路线和天气信息
- 🎨 **现代化前端**：Vue 3 + TypeScript + Vite，响应式设计，流畅的用户体验
- 📤 **行程导出**：支持将行程导出为图片或 PDF，便于保存与分享
- 🔗 **链接分享**：行程数据通过 gzip + base64 编码进 URL，无需后端存储即可分享；编辑保存后地址栏链接自动同步为最新版本
- ✏️ **实时编辑**：支持在结果页调整景点顺序、删除景点，预算自动重算
- 📊 **真实进度**：SSE 推送各阶段执行进度，进度条与后端实际执行同步，不再是定时器估算
- 🛡️ **降级语义**：当 LLM 输出与城市/天数不匹配时，自动降级为 fallback 模式并给出提示
- 📱 **完整功能**：包含住宿、交通、餐饮和景点游览时间推荐

## 🏗️ 技术栈

### 后端
- **框架**：HelloAgents（基于 SimpleAgent）
- **API**：FastAPI + Pydantic v2
- **MCP 工具**：amap-mcp-server（高德地图）
- **LLM**：支持多种 LLM 提供商（OpenAI、DeepSeek 等）
- **测试**：pytest（27 个用例覆盖核心逻辑）
- **类型契约**：Pydantic schemas 作为唯一真相源

### 前端
- **框架**：Vue 3（组合式 API + `<script setup>`）+ TypeScript
- **构建工具**：Vite
- **UI 组件库**：Ant Design Vue
- **地图服务**：高德地图 JavaScript API
- **HTTP 客户端**：Axios
- **测试**：Vitest + happy-dom（17 个用例覆盖 3 个 composable）
- **类型生成**：openapi-typescript（从 FastAPI OpenAPI  schema 自动生成）

## 📁 项目结构

```
helloagents-trip-planner/
├── backend/                              # 后端服务 (FastAPI + HelloAgents)
│   ├── app/
│   │   ├── agents/
│   │   │   ├── trip_planner_agent.py     # 多智能体编排：景点 / 天气 / 酒店 / 规划
│   │   │   └── stateless_agent.py        # 无状态 Agent 封装
│   │   ├── api/
│   │   │   ├── main.py                   # FastAPI 应用入口（含 lifespan 日志配置）
│   │   │   └── routes/
│   │   │       ├── trip.py               # 计划生成（普通 + SSE 流式）+ 健康检查
│   │   │       └── map.py                # 地图 / POI / 配图 / 天气 / 路线（已合并原 poi.py）
│   │   ├── models/
│   │   │   └── schemas.py                # Pydantic v2 数据模型（唯一真相源）
│   │   ├── services/
│   │   │   ├── amap_service.py           # 高德地图服务封装
│   │   │   ├── llm_service.py            # LLM 客户端
│   │   │   ├── unsplash_service.py       # Unsplash 配图服务
│   │   │   └── persistent_mcp.py         # MCP 常驻会话管理
│   │   ├── config.py                     # 配置管理
│   │   └── logging_config.py             # 根日志配置（幂等设计）
│   ├── tests/
│   │   ├── test_planner_agent.py         # Agent 核心逻辑测试（27 个用例）
│   │   └── test_schemas.py               # Schemas 契约测试
│   ├── scripts/
│   │   └── dump_openapi.py               # 导出 openapi.json 用于类型生成
│   ├── run.py                            # 后端启动脚本
│   ├── requirements.txt
│   ├── .env.example
│   └── .gitignore
├── frontend/                             # 前端应用 (Vue3 + TypeScript + Vite)
│   ├── src/
│   │   ├── views/
│   │   │   ├── Home.vue                  # 首页：填写旅行需求
│   │   │   └── Result.vue                # 结果页：行程骨架（状态/生命周期/调度）
│   │   ├── components/
│   │   │   └── result/
│   │   │       ├── BudgetCard.vue        # 预算卡片展示
│   │   │       ├── WeatherCards.vue      # 天气预报卡片
│   │   │       └── DayItinerary.vue      # 每日行程（景点/酒店/餐饮/编辑操作）
│   │   ├── composables/                  # 可复用逻辑（组合式函数）
│   │   │   ├── useExport.ts              # 导出图片/PDF（DOM 克隆 + 离屏渲染）
│   │   │   ├── useAmap.ts                # 高德地图封装（初始化/标记/路线/销毁）
│   │   │   ├── usePlanShare.ts           # 行程分享（gzip + base64 URL 编码）
│   │   │   └── __tests__/                # Vitest 测试（16 个用例）
│   │   │       ├── useExport.spec.ts
│   │   │       ├── useAmap.spec.ts
│   │   │       └── usePlanShare.spec.ts
│   │   ├── services/
│   │   │   └── api.ts                    # 后端 API 封装 (axios)
│   │   ├── types/
│   │   │   ├── index.ts                  # 业务类型定义（手写）
│   │   │   └── api.d.ts                  # API 类型（openapi-typescript 自动生成）
│   │   ├── App.vue
│   │   ├── main.ts
│   │   └── env.d.ts
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── vitest.config.ts
│   ├── .env.example
│   └── .gitignore
├── .vscode/                              # 共享编辑器配置
├── start.bat                             # 一键启动前后端
└── README.md
```


## 🚀 快速开始

### 前提条件

- Python 3.10+
- Node.js 18+
- 高德地图 API 密钥（Web 服务 API 和 Web 端 JS API）
- LLM API 密钥（OpenAI / DeepSeek 等）

### 后端安装

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入你的 API 密钥

# 启动后端服务
uvicorn app.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端安装

```bash
cd frontend

# 安装依赖
npm install

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入高德地图 Web API Key 和 Web 端 JS API Key

# 启动开发服务器
npm run dev

# 打开浏览器访问 http://localhost:5173
```

### 类型自动生成（可选）

当后端 schemas 变更后，前端类型需要同步：

```bash
# 1. 导出后端 OpenAPI schema
cd backend
python scripts/dump_openapi.py

# 2. 生成前端类型
cd ../frontend
npx openapi-typescript ../backend/openapi.json -o src/types/api.d.ts
```

> `src/types/api.d.ts` 顶部有自动生成的注释，请勿手动修改该文件。

## 🧪 测试

### 后端测试（pytest）

```bash
cd backend
pytest tests/ -v
```

覆盖范围（27 个用例）：
- `test_planner_agent.py`：输入净化、JSON 提取、输出语义校验、降级逻辑、字段净化
- `test_schemas.py`：Pydantic schemas 边界值、类型转换、默认值、roundtrip 序列化

### 前端测试（Vitest）

```bash
cd frontend
npm run test
```

覆盖范围（17 个用例，3 个文件）：
- `useExport.spec.ts`：`prepareExportContainer` DOM 克隆与样式改写
- `useAmap.spec.ts`：地图初始化、标记收集、中心点动态计算、生命周期销毁
- `usePlanShare.spec.ts`：gzip/base64 编解码、URL 构建与解析、大数据 roundtrip、`updateUrlHash` 覆盖旧链接

## 📝 使用指南

1. **填写旅行信息**：在首页输入目的地城市、旅行日期和天数、交通方式偏好、住宿偏好、旅行风格标签
2. **生成旅行计划**：点击"生成旅行计划"按钮
3. **系统处理流程**：
   - 调用 HelloAgents Agent 生成初步计划
   - Agent 自动调用高德地图 MCP 工具搜索景点
   - Agent 获取天气信息和路线规划
   - 后端进行输出语义校验（城市/天数匹配），不匹配则降级为 fallback 模式
   - 整合所有信息生成完整行程
4. **查看与编辑结果**：
   - 每日详细行程（景点、酒店、餐饮）
   - 景点地图标记与路线规划
   - 天气预报卡片
   - 预算统计卡片
   - **编辑模式**：可上移/下移/删除景点，预算自动重算
5. **分享与导出**：
   - 点击"分享行程"生成可复制的链接（数据编码在 URL hash 中）
   - **编辑后保存时地址栏 hash 会自动更新**，直接复制地址栏即可分享最新版本
   - 点击"导出图片/PDF"保存行程为文件

## 🔧 核心实现

### 1. 多 Agent 协作架构

后端采用 4 个 Specialist Agent 分工协作：

| Agent | 职责 | 输出 |
|-------|------|------|
| AttractionAgent | 搜索并筛选景点 | `attractions` 列表 |
| WeatherAgent | 查询旅行期间天气 | `weather_info` 列表 |
| HotelAgent | 推荐住宿 | `accommodation` |
| PlannerAgent | 整合以上信息生成每日行程 | `TripPlan` |

由 `trip_planner_agent.py` 中的 `MultiAgentTripPlanner` 统一编排，确保输出符合 `TripRequest` 约束。

### 2. 降级语义三层设计

当 LLM 输出不符合预期时，系统通过三层机制保证用户体验：

1. **字段层**：`is_fallback` 布尔标记本次计划是否由规则兜底生成
2. **消息层**：`fallback_message` 说明降级原因（如"城市不匹配"、"天数不匹配"）
3. **UI 层**：前端检测到 `is_fallback` 时显示 banner 提示，同时仍展示可用内容

### 3. 前端 Composable 设计

将复杂逻辑从组件中抽离为可复用的组合式函数：

- **`useExport.ts`**：DOM 克隆 → 注入地图快照 → 改写 antd 卡片为打印友好样式 → html2canvas / html2pdf 渲染
- **`useAmap.ts`**：高德地图 SDK 封装，支持动态中心点计算（取第一个有坐标景点，无则回退北京）
- **`usePlanShare.ts`**：`CompressionStream` gzip 压缩 + base64 URL 安全编码，解码时逆向解压；`updateUrlHash` 在保存编辑后把最新计划写回地址栏

### 4. Result.vue 组件拆分

原 `Result.vue` 1,449 行拆分为：

- `Result.vue`（646 行）：页面骨架、状态管理、生命周期、编辑调度、分享/导出调用
- `BudgetCard.vue`（87 行）：纯展示，接收 `budget` prop
- `WeatherCards.vue`（89 行）：纯展示，接收 `weatherInfo` prop
- `DayItinerary.vue`（325 行）：每日行程，包含景点卡片、编辑操作（上移/下移/删除）、酒店与餐饮展示

### 5. SSE 真实进度

早期前端的进度条是 `setInterval` 每 1.5s 硬涨 5%，与后端实际执行毫无关系——显示"正在查询天气"时后端可能还在搜景点。

现在改为：

- **后端** `POST /api/trip/plan-stream` 返回 `text/event-stream`，`MultiAgentTripPlanner.plan_trip_async` 接受可选的异步进度回调，在各阶段完成时推送事件：

  | stage | percent | 触发时机 |
  |-------|---------|----------|
  | `search` | 15 | 三路并行搜索启动 |
  | `sub` | 28 / 38 / 48 | 景点 / 天气 / 酒店各自完成 |
  | `plan` | 60 | 开始生成行程 |
  | `parse` | 90 | 校验并整理数据 |
  | `done` | 100 | 完成，`data` 字段携带最终 `TripPlan` |

- **前端** 用 `fetch` + `ReadableStream` 手动解析 SSE（`EventSource` 只支持 GET，无法携带 JSON 请求体），进度取 `Math.max` 防止三路乱序导致回跳。
- 后端每 15s 发一条 `: keep-alive` 注释行保活；客户端断开时取消后台任务，避免白跑一次 LLM 调用。

## 📋 优化记录

本项目经过四轮系统优化，共完成 **25 项**代码与架构改进：

### 第一轮（bc60478）—— 健壮性与边界处理

1. 降级语义三层设计（`is_fallback` + `fallback_message` + UI banner）
2. 坐标判空修复（`!= null` 避免吃掉经纬度 0）
3. 健康检查端点瘦身（移除 MCP 握手，避免启动阻塞）
4. 用户输入净化（`sanitize_input` 限制长度、过滤危险字符）
5. API 密钥冲突检测（Web 服务 Key vs JS API Key 混用提示）
6. 消除硬编码 URL（前端 API baseURL 改为相对路径 `/api`）
7. 配图请求分批并发（Unsplash 6 张分 3 批 × 2 并发）
8. InfoWindow 复用（避免重复创建 DOM 节点）
9. 地图组件清理（`onUnmounted` 销毁地图实例，防止内存泄漏）

### 第二轮（fbc941f）—— 架构重构与测试

10. 抽离 `useExport.ts`（消除 292 行导出逻辑重复）
11. 抽离 `useAmap.ts`（消除 137 行地图逻辑重复）
12. 抽离 `usePlanShare.ts`（消除内联分享逻辑）
13. 输出语义校验（`_validate_plan` 检查城市/天数匹配，硬伤直接降级）
14. JSON 提取健壮化（`_extract_json_str` 三档提取 + 正则去尾随逗号）
15. 同步/异步去重（`plan_trip` 委托 `asyncio.run(plan_trip_async())`）
16. 预算重算（删除景点后按剩余景点 `ticket_price` 重新求和）
17. 地图初始中心动态计算（取第一个有坐标景点，无则回退北京）
18. 统一日志配置（`logging_config.py` 幂等设计）
19. 后端 pytest 测试（27 个用例覆盖核心逻辑）

### 第三轮（16e0fed）—— 组件化与类型安全

20. `Result.vue` 拆分为 3 个子组件（1,449 行 → 646 行）
21. 前端 Vitest 测试（16 个用例覆盖 3 个 composable）
22. openapi-typescript 类型自动生成（`api.d.ts` 从 `openapi.json` 生成）

### 第四轮（cd0e623）—— 一致性、可分享与可观测

23. **编辑结果写入分享链接**：`saveChanges` 调用 `updateUrlHash` 把最新计划写回地址栏 hash（`history.replaceState`，不新增历史记录），解决「改完直接复制地址栏发人，对方看到的还是改前版本」
24. **合并 `poi.py` 与 `map.py`**：POI 详情、搜索、配图统一收敛到 `/api/map/*` 一个路由文件，消除「同一能力两套接口」的歧义（原 `/poi/search` 与 `/map/poi` 重复，已删除后者为唯一入口）
25. **SSE 替代假进度条**：新增 `POST /api/trip/plan-stream`，Agent 各阶段完成即推事件，前端进度条反映真实执行进度；客户端断开时自动取消后台任务

## 📄 API 文档

启动后端服务后，访问 `http://localhost:8000/docs` 查看完整的 Swagger UI 文档。

主要端点：
- `POST /api/trip/plan` - 生成旅行计划
- `POST /api/trip/plan-stream` - 生成旅行计划（SSE 实时进度）
- `GET /api/trip/health` - 旅行规划服务健康检查
- `GET /api/map/poi` - 搜索 POI（唯一入口）
- `GET /api/map/poi/detail/{poi_id}` - POI 详情
- `GET /api/map/photo` - 景点配图（Unsplash）
- `GET /api/map/weather` - 查询天气
- `POST /api/map/route` - 规划路线
- `GET /api/map/health` - 地图服务健康检查

## 🔮 后续可扩展方向

三项高优先级问题已全部解决，以下为可选的进一步演进方向：

1. **编辑持久化到后端**：当前编辑结果保存在 sessionStorage 并同步进 URL，跨设备/跨浏览器仍不共享；如需多人协作可加轻量存储（SQLite / Redis）。
2. **按路由拆包**：构建产物主 chunk 约 2.1 MB，可用动态 `import()` 把结果页、导出库（html2canvas / jsPDF）拆成独立 chunk。
3. **SSE 断线重连**：当前客户端断开即取消任务，可引入 `Last-Event-ID` 与任务缓存，实现刷新页面后继续接收进度。

## 🤝 贡献指南

欢迎提交 Pull Request 或 Issue！

## 📜 开源协议

CC BY-NC-SA 4.0

## 🙏 致谢

- [HelloAgents](https://github.com/datawhalechina/Hello-Agents) - 智能体教程
- [HelloAgents 框架](https://github.com/jjyaoao/HelloAgents) - 智能体框架
- [高德地图开放平台](https://lbs.amap.com/) - 地图服务
- [amap-mcp-server](https://github.com/sugarforever/amap-mcp-server) - 高德地图 MCP 服务器

---

**HelloAgents 智能旅行助手** - 让旅行计划变得简单而智能 🌈
