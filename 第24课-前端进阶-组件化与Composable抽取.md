# 第 24 课:前端进阶:组件化与 Composable 抽取

> 所属模块:模块五「工程化:从"能跑"到"能上线"」(第 19–24 课)
> 预计时长:2–2.5 小时(本课实验是真实的重构,请预留完整的整块时间并先提交一次 git)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第23课-前端基础回顾-Vue3组合式API与TypeScript.md](./第23课-前端基础回顾-Vue3组合式API与TypeScript.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化   ← 你在这里(第 24 课)
模块六 产品化与进阶
```

第 1 课你就被预告过这个数字:1391 行——`Result.vue`,全项目最大的文件。五节课的工程化训练(日志、测试、审查、安全、类型)都是为了今天这一刀:**把它拆成 4–5 个职责单一的组件加一个 `useTripPlan` composable,功能一行不少。** 拆完之后,模块五立碑收官:日志 + 测试 + 5 个 Bug 修复 + 组件化,合并成一个完整的"工程化 PR"。

> 行号说明:本课行号基于 2026-09-11 的 main 分支的 `Result.vue`(1391 行)。重构过程中行号会移动,**先通读一遍本课的职责地图再动刀**;第 25 课的地图实验将直接以你拆出的 `TripMap.vue` 为对象。

## 学习目标

完成本课后,你应该能够:

1. 说清单文件组件过大的四类代价,并给"按职责拆分"定出可操作的原则;
2. 把有状态逻辑抽成 composable(`useTripPlan`),说清 composable 与组件的分工边界;
3. 在正确场景使用 `provide/inject`,并知道什么时候**不该**用它;
4. 完成一次"功能不变"的真实重构,并用手动回归清单验证。

## 课前自检

- [ ] 第 23 课的类型对照你已经做过一遍,知道 `TripPlan` 的完整形状;
- [ ] 你已经**提交了一次 git**(`git add -A && git commit -m "before refactor"`),随时可以回滚;
- [ ] 生成过一次真实行程,Result 页的地图、编辑模式、导出图片/PDF 都亲手点过一遍(重构前必须知道"正常长什么样");
- [ ] 知道 `<script setup>` 里 `defineProps` / `defineEmits` 的写法(第 23 课 23.3)。

---

## 24.1 解剖 1391 行:Result.vue 的职责地图

先别动手,先画地图。通读 `Result.vue`,按行号切成块:

| 行号区间 | 职责 | 规模 |
|---|---|---|
| 1–308 | template:页面头、侧导航、概览、预算、地图容器、每日行程、天气 | 308 行 |
| 320–327 | 状态声明:`tripPlan`、`editMode`、`originalPlan`、`attractionPhotos` 等 | 8 行 |
| 329–339 | `onMounted`:读 sessionStorage → 加载图片 → 初始化地图 | 11 行 |
| 341–352 | `goBack` 返回与侧导航滚动定位 `scrollToSection` | 12 行 |
| 354–415 | 编辑模式:进入/保存/取消、删景点、移景点 | 62 行 |
| 417–425 | `getMealLabel` 餐饮标签 | 9 行 |
| 427–491 | 景点图片:批量加载、SVG 占位图、加载失败兜底 | 65 行 |
| **493–787** | **导出:`exportAsImage`(496–630)与 `exportAsPDF`(632–787)** | **295 行** |
| **789–913** | **地图:`initMap`(790–813)、`addAttractionMarkers`(816–878)、`drawRoutes`(881–913)** | **125 行** |
| 916–1390 | style:全局卡片样式、`:deep()` 覆盖、动画 | 475 行 |

这张地图上有两个值得你先冷笑一声的事实:

1. **导出两个函数有约 250 行近乎逐行复制**(506–614 与 643–754:同样的容器复制、同样的地图截图处理、同样的卡片样式修整),区别只有结尾"存成 PNG"还是"转 PDF"。复制粘贴是组件化要消灭的头号敌人——本课的 `ExportButton` 会把它们合并成一个共享流程。
2. **`exportMapContainer` 出现了两处**(520–523 行图片版、652–659 行 PDF 版),都在从 `#amap-container` 的 canvas 抓快照——**导出功能对地图实例有隐藏依赖**,这决定了拆分时的接口设计(24.4 详谈)。

### 巨型组件的四种代价

1. **改不敢改**:475 行样式里大量 `:deep(.ant-card)` 是全局性覆盖,改一处 hover 效果,不知道会波及哪些卡片;
2. **不可复用**:想把"每日行程卡片"单独用在别处?不存在,它和地图、导出、图片加载搅在一起;
3. **不可测试**:第 20 课后端测试全绿,前端呢?1391 行的组件连"想测"都无从下刀;
4. **协作冲突**:多人同时改这个文件,git 冲突是必然。

### 动刀之前:先建立回归基线

重构的验收标准是"功能不变",所以**拆之前**必须把"功能长什么样"固定下来,否则拆完你连"没变坏"都无法证明。花五分钟做三件事:

1. 生成一次真实行程,把 Result 页**从上到下截一组图**(概览、预算、地图、每日行程、天气);
2. 分别导出一份图片和一份 PDF,存进 `docs/lesson24-baseline/`;
3. 进出一次编辑模式,改一个地址再取消,确认恢复。

后面实验的回归清单就是在和这组基线对照。**没有基线的重构,验收全靠感觉——这恰是本课要戒掉的东西。**

## 24.2 组件拆分原则:按职责,不按行数

拆分不是"每 300 行切一刀"。三条判断标准:

1. **职责单一**:一段代码只回答一个问题("怎么画地图" vs "怎么编辑行程")——用 24.1 的地图即可切出候选;
2. **复用性**:它会在两个地方出现吗?`DayCard` 每天渲染一次是"多实例",`BudgetPanel` 独立成块是"可组合",`getMealLabel` 这种 9 行纯函数不值得单开组件(留在工具层);
3. **依赖方向**:父 → 子只能通过 props 下传,子 → 父只能通过 emit 上报(第 23 课 23.3)。**发现"子组件必须知道太多父级状态"时,说明切口选错了。**

据此确定拆分蓝图(4 个必做组件 + 1 个选做 + 1 个 composable):

| 新文件 | 承接的旧行号 | 接口设计 |
|---|---|---|
| `components/TripMap.vue` | template 111–116;script 789–913 | props: `tripPlan`;`defineExpose` 一个 `getSnapshot()`(导出用) |
| `components/DayCard.vue` | template 122–253;script 354–415 的两个操作函数 | props: `day`、`editMode`;emits: `move` / `delete` |
| `components/BudgetPanel.vue` | template 84–108 | props: `budget: Budget` |
| `components/ExportButton.vue` | template 20–34;script 493–787(合并重复) | 无 props;通过注入/模板引用拿地图快照 |
| `components/WeatherPanel.vue`(选做) | template 257–287 | props: `weatherInfo: WeatherInfo[]` |
| `composables/useTripPlan.ts` | 320–327、329–339、354–415、427–491 | 见 24.3 |

`Result.vue` 从 1391 行缩到约 200 行,变成纯粹的**编排层**:装配组件、持有布局、串侧导航。

拆分的**顺序**也是方法论的一部分:从依赖最少的纯展示组件(`BudgetPanel`)开始,最后才动有隐藏耦合的(`TripMap`,被导出功能依赖)。每一步都保持"可运行的中间态",任何一个 commit 单独 checkout 出来都应该能用——这是重构与重写的分界线:**重构是 保持行为的一系列小步移动,重写是赌一把大的**。

## 24.3 Composable:把有状态逻辑从视图里剥出来

组件是"结构 + 状态 + 样式"的捆绑体,composable 则**只带走状态与逻辑,不带任何模板**——这是 Vue3 组合式 API 的复用单元。命名约定 `useXxx`,内部正常用 ref/computed/watch,最后**把状态与操作函数打包返回**。

`frontend/src/composables/useTripPlan.ts` 的设计(承接 24.1 表格里列出的行号):

```typescript
import { ref } from 'vue'
import type { TripPlan } from '@/types'

export function useTripPlan() {
  const tripPlan = ref<TripPlan | null>(null)          // 321 行
  const editMode = ref(false)                          // 322 行
  const originalPlan = ref<TripPlan | null>(null)      // 323 行
  const attractionPhotos = ref<Record<string, string>>({})  // 324 行

  const load = () => {                                 // 承接 329–339 行的读取部分
    const data = sessionStorage.getItem('tripPlan')
    if (data) tripPlan.value = JSON.parse(data)
    return tripPlan.value
  }

  const save = () => {                                 // 承接 366–368 行
    if (tripPlan.value) sessionStorage.setItem('tripPlan', JSON.stringify(tripPlan.value))
  }

  const enterEdit = () => {                            // 承接 355–360 行
    editMode.value = true
    originalPlan.value = JSON.parse(JSON.stringify(tripPlan.value))  // 深拷贝快照
  }

  const cancelEdit = () => {                           // 承接 381–387 行
    if (originalPlan.value) tripPlan.value = JSON.parse(JSON.stringify(originalPlan.value))
    editMode.value = false
  }

  const deleteAttraction = (dayIndex: number, attrIndex: number) => { /* 承接 390–401 行 */ }
  const moveAttraction = (dayIndex: number, attrIndex: number, dir: 'up' | 'down') => { /* 承接 404–415 行 */ }
  const loadAttractionPhotos = async () => { /* 承接 428–451 行 */ }

  return { tripPlan, editMode, attractionPhotos, load, save, enterEdit, cancelEdit,
           deleteAttraction, moveAttraction, loadAttractionPhotos }
}
```

composable 的三条纪律:**返回 ref 和函数,不返回裸值**(否则丢响应式);**不碰 DOM**(碰 DOM 是组件的事);**可组合**(useTripPlan 内部将来可以再用 usePhotos、useEditState 细分)。组件里用它:

```typescript
const { tripPlan, editMode, load, save, enterEdit, cancelEdit,
        deleteAttraction, moveAttraction, loadAttractionPhotos } = useTripPlan()
```

一个容易混淆的边界:composable 和"工具函数"(utils)差在哪?`getMealLabel`(417–425 行)这种**纯输入纯输出**的逻辑放 utils 就够;只要内部出现了 `ref`/`watch`/生命周期,**有状态、需要响应式**,就该升格成 composable。存放位置也有惯例:`frontend/src/composables/`(与 components 平级),本项目还没有这个目录——你将亲手创建它。

## 24.4 provide/inject:它解决什么,什么时候别用

props 逐层下传的痛点是"深":A 传 B、B 传 C、C 传 D,中间层被迫当搬运工(prop drilling)。`provide/inject` 让祖先**跨层**发货:

```typescript
// 祖先层
provide('tripPlan', tripPlan)          // 发
// 任意深层后代
const tripPlan = inject<Ref<TripPlan | null>>('tripPlan')   // 收
```

**本课的真实用例只有一个:导出按钮需要地图快照。** `exportAsImage` 里的地图截图逻辑(515–525 行:从 `#amap-container` 里抓 canvas `toDataURL`)在组件化后越过了组件边界——`ExportButton` 和 `TripMap` 是兄弟,谁也不包含谁。两条解法:

- **方案 A(推荐):模板引用 + `defineExpose`。** `Result.vue` 里 `<TripMap ref="mapRef" ... />`,`TripMap` 内部 `defineExpose({ getSnapshot: () => map ? mapCanvas.toDataURL(...) : null })`,`ExportButton` 通过一个 `inject` 或 props 拿到这个函数。显式、可追踪;
- **方案 B:provide/inject 直发地图实例。** `TripMap` 里 `provide('amapInstance', map)`,`ExportButton` 注入自取。更省事,但"谁在用地图"从接口上看不出来了。

判断标准:**跨 1–2 层、关系稳定的,继续用 props;跨多层的"全局-ish"资源(地图实例、当前请求上下文)才值得 provide/inject。** 把它当成"到处用的全局变量",半年后你将收获一个谁都不敢删的魔法依赖网。本课建议:快照函数走方案 A 的显式接口,provide/inject 你至少亲手写一次(选做:用 provide/inject 下发 `editMode`)。

方案 A 的完整接线(三个文件各一行关键代码):

```typescript
// TripMap.vue: 把快照能力"发布"出去
defineExpose({ getSnapshot: () => mapCanvas ? mapCanvas.toDataURL('image/png') : null })

// Result.vue: 用模板引用接住组件实例
const mapRef = ref<InstanceType<typeof TripMap> | null>(null)
// <TripMap ref="mapRef" :trip-plan="tripPlan" />  →  provide('mapSnapshot', () => mapRef.value?.getSnapshot())

// ExportButton.vue: 注入并使用
const getSnapshot = inject<() => string | null>('mapSnapshot')
```

## 24.5 动手实验:七步拆解,步步可回滚

### 任务(每步完成后浏览器热更新验证一次,红了立即修)

1. **抽 `useTripPlan`**(24.3):`Result.vue` 的状态与操作函数全部迁出,改为解构调用;地图与导出暂不动。验证:页面行为与拆前完全一致;
2. **拆 `BudgetPanel.vue`**:最简单的一块(84–108 行纯展示),props 收 `budget`。验证:预算数字正常显示;
3. **拆 `WeatherPanel.vue`(选做)**:257–287 行,props 收 `weatherInfo`;
4. **拆 `DayCard.vue`**:template 122–253 的每个 collapse-panel 内容;编辑模式里对 `item.address` 等的 `v-model` 直改 props 对象属性——**先原样保留**(说明见卡点 3),只把"删除/移动"动作改为 emit 上报,由父级调 `useTripPlan` 的函数。验证:编辑模式的改/删/移;
5. **拆 `ExportButton.vue`**:把 493–787 两个函数**合并**为一个 `buildExportCanvas(): Promise<HTMLCanvasElement>` 共享流程 + `exportAsImage` / `exportAsPDF` 两个薄出口;图片与 PDF 的差异只留在结尾十行。验证:导出图片与 PDF 逐项对比拆前产物;
6. **拆 `TripMap.vue`**:789–913 行整体迁入(含 `import AMapLoader`);`onMounted` 里的 `initMap()` 时序(329–339 行)跟着搬;`defineExpose` 快照函数;`Result.vue` 用模板引用串接导出。验证:地图渲染、Marker 点击信息窗、每日路线;
7. **清理**:删除 `Result.vue` 里所有死代码与不再使用的 import;`:deep()` 样式**跟着组件搬家**(卡片通用样式留 Result,`.hotel-card` / `.weather-card` 等专属样式进各自组件)。

### 回归清单(功能不变的验收标准)

- [ ] 从 Home 生成行程跳转 Result,概览/预算/地图/每日行程/天气全部渲染;
- [ ] 侧导航点击能滚动到对应区块(`scrollToSection` 依赖 `id` 锚点——组件化后确认 `id="overview"` 等仍存在);
- [ ] 编辑模式:改地址/时长/描述 → 保存 → 刷新页面仍在(sessionStorage 已更新);
- [ ] 取消编辑恢复原文;每天至少保留一个景点的限制仍在;
- [ ] 导出图片与 PDF:内容完整、地图有截图、分页正常(与拆前产物对比);
- [ ] 地图:Marker 编号、点击信息窗、按天分组的路线;
- [ ] `npm run build`(vue-tsc 类型检查)零错误——TS 在这次大搬迁里当你的安全网。

### 常见卡点

- **Q:拆完样式全乱了?** 九成是 `:deep()` 选择器没跟着走。`Result.vue` 里的 `:deep(.ant-card-head)` 之类覆盖了所有子组件的卡片——迁移时想清楚:通用样式(所有卡片)留 Result,专属样式(`.weather-card` 1029–1077 行、`.hotel-card` 1101–1114 行)进对应组件的 scoped style。
- **Q:导出图片里地图是空白?** `buildExportCanvas` 依赖地图 canvas 已渲染;`TripMap` 的快照函数要处理"地图未就绪"(`map` 为 null 时返回 null,导出侧降级为无图导出)——拆分前这个边界藏在共享闭包里,拆分后必须显式建模,这是重构暴露隐藏耦合的正常现象。
- **Q:`DayCard` 直接 `v-model:value="item.address"` 改了 props 的属性,这不算违反单向数据流吗?** 严格说是的(改的是 props 传入对象的**内部属性**,引用没变所以 Vue 不拦)。原代码就是这么写的(`item.address` 直改,205–211 行),本课策略是"先原样保留,功能优先";彻底的修法是 emit 一个 `update:attraction` 让父级改——留作选做,体会"理想架构"与"务实迁移"的取舍。
- **Q:`sessionStorage` 传数据的方式要不要一起改掉?** 不要。本课只做"等价重构",改动越少越好验证。Home → Result 的传值方式是另一个(产品级)议题。

## 24.6 课后作业与思考题

**必做:**

1. 完成七步拆解,回归清单全勾,`npm run build` 通过;把拆分前后的行数对比记进 `docs/lesson24-refactor-notes.md`(各文件行数 + 一句话职责);
2. 给 `DayCard.vue` 的两个 emit 补上 TypeScript 签名(`defineEmits<{ ... }>`),并在 `Result.vue` 里验证"删错参数名"会被 vue-tsc 抓住——**组件契约也要类型化**;
3. `git log --oneline` 确认每一步一个 commit,写清"第 N 步:迁移了哪些行"。

**选做(思考,可动手):**

1. 把 `DayCard` 的 `v-model` 直改 props 属性(卡点 3)重构为 emit 上报:`@update:attraction` 携带 `(dayIndex, attrIndex, patch)` 给父级,由 `useTripPlan` 统一改数据——然后回答:这次"更正确"的重构,新增了几行代码?可读性变好还是变坏了?(没有标准答案,写 100 字你的判断)
2. 用 provide/inject 下发 `editMode`,删掉传给每个 `DayCard` 的那条 prop;再回答:**如果明天要给编辑模式加"只读预览"的第三态,两种方案(Props 逐层传 vs provide/inject)谁改起来更疼?**
3. 给 `useTripPlan` 写一个最小单测(如 `moveAttraction` 边界:第一个元素上移应无效)——composable 不碰 DOM,恰恰是前端里**唯一能直接用 vitest/jest 测**的层;这也是"为什么要把逻辑抽出去"的最硬理由。

## 24.7 模块五里程碑:工程化 PR

到本课为止,模块五的六节课正好拼成一个完整的 PR(对应课程大纲"工程化 PR"里程碑与学习建议第 7 周的产出形态):

| 课次 | 改动 | 一句话验收 |
|---|---|---|
| 第 19 课 | loguru 统一日志 + request_id 全链路 | 一个 ID 能回放一次请求 |
| 第 20 课 | pytest 测试套件(≥15 条,零外部依赖) | `pytest -v` 全绿 |
| 第 21 课 | 4 个 Bug 修复 + 回归测试 + 复盘 checklist | `/api/trip/health` 说实话 |
| 第 22 课 | 密钥审计 + CORS 收紧 + 注入缓解三防线 | 注入实验报告 |
| 第 23 课 | 表单校验 + 类型契约对齐 | 30 天上限前后端一致 |
| 第 24 课 | Result.vue 组件化(1391 → 约 200 行编排层) | 回归清单全勾 |

写一份 **`docs/lesson19-24-refactor-notes.md` 改造说明**作为 PR 的门面,结构:① 改造动机(从"能跑"到"能上线"的差距清单);② 每模块前后对比(日志可回放性、测试数、Bug 数、文件行数);③ 新目录结构图(`backend/tests/`、`frontend/src/components/`、`frontend/src/composables/`);④ 已知妥协(如 DayCard 的 props 直改、前端 console.log 未清);⑤ 回滚方式(按课次分 commit 的价值此刻兑现)。

对着大纲附录 B 自检一遍模块五的两问,答不上来就回炉:

1. **你的测试覆盖了哪些纯函数?** —— 温度校验器、JSON 提取、重试解析、查询构造、plan_trip 编排(打桩),每一条都能指到测试文件;
2. **提示词注入实验里 LLM 被攻破了吗?** —— 用你自己的实验数据回答,并说出哪道防线贡献最大。

## 下节预告

**第 25 课:地图可视化深入。** 模块六开工。你已经把地图代码亲手安放进 `TripMap.vue`——下一课深入这条全项目唯一"浏览器直连第三方 JS SDK"的链路:`AMapLoader.load` 的加载时序、Marker/InfoWindow/Polyline 三种覆盖物如何被 `tripPlan` 驱动,然后实现"按天显示/隐藏图层切换"与"Marker 点击联动日程卡片"两个真实产品功能。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
