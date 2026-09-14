# 第 23 课:前端基础回顾:Vue3 组合式 API 与 TypeScript

> 所属模块:模块五「工程化:从"能跑"到"能上线"」(第 19–24 课)
> 预计时长:1.5–2 小时(含动手实验;需要前端跑起来对照)
> 配套大纲:[课程大纲.md](./课程大纲.md) | [学习建议.md](./学习建议.md)
> 前置课程:[第22课-配置安全与提示词注入.md](./第22课-配置安全与提示词注入.md)

---

## 本课在课程中的位置

```
模块一 打地基
模块二 Agent 原理
模块三 多智能体编排
模块四 服务层与数据质量
模块五 工程化   ← 你在这里(第 23 课)
模块六 产品化与进阶
```

后端工程化(日志、测试、Bug、安全)全部就位,本课与下一课处理前端。你从第 2 课起就一直在读 `Home.vue`,但从未系统过一遍 Vue3 的语言基础——本课补上:**`<script setup>`、ref/reactive/computed/watch、props/emit、TypeScript 接口**,全部用你仓库里的真实代码当教材。核心精读对象是 `frontend/src/types/index.ts`(95 行)与后端 `schemas.py` 的**逐字段对照**——前后端数据契约正是靠这两个文件人工维护的,而你会亲手发现契约上的一处真实漂移。实验给 Home 表单补上自定义校验规则,与后端 `travel_days` 的 `ge=1, le=30` 全链路对齐。

## 学习目标

完成本课后,你应该能够:

1. 读通 `<script setup>` 组件的三段结构(template/script/style)与组合式 API 的响应式模型;
2. 区分 `ref` 与 `reactive` 的适用场景,说清 `watch` 在 Home.vue 日期联动里扮演的角色;
3. 逐字段核对 `types/index.ts` 与 `schemas.py` 的契约,指出 TS 类型与 Pydantic 模型的三处"不对等"及其原因;
4. 用 Ant Design Vue 的 `rules` 给表单加自定义校验,并解释"前后端各校验一遍"为什么不是重复劳动。

## 课前自检

- [ ] 前端能 `npm run dev` 跑起来,填表单能生成一次行程(第 3 课的成果);
- [ ] 你在 `Home.vue` 里改过任意一行并看到热更新生效;
- [ ] 知道 TypeScript 与 JavaScript 的关系("JS + 类型标注,编译期检查");
- [ ] 记得 `schemas.py` 里 `TripRequest` 有哪些字段(第 2 课追踪过它的旅程)。

---

## 23.1 `<script setup>`:Vue3 组件的默认形态

一个 `.vue` 单文件组件(SFC)分三段:`<template>`(结构)、`<script setup lang="ts">`(逻辑)、`<style scoped>`(样式)。`<script setup>` 是 Vue3 的编译语法糖:**在这个块里声明的变量、函数、import 的组件,自动暴露给同文件的 template 使用**,不需要 Vue2 时代的 `export default { data(), methods: ... }` 样板。

本项目共三个组件,恰好是三个复杂度台阶:

- `App.vue`(28 行):`<script setup>` 里**一个字都没有**——纯模板组件,只放布局和 `<router-view />`;
- `Home.vue`(654 行):表单交互,响应式状态 + 事件处理的主战场;
- `Result.vue`(1391 行):下节课的解剖对象。

## 23.2 响应式三件套:ref / reactive / watch

组合式 API 的核心问题只有一个:**怎么让"数据变化"自动驱动"界面更新"**。三个工具各管一摊:

**`ref(x)`** 包装单个值,`.value` 读写;在 template 里使用时自动解包(不用写 `.value`)。Home.vue 215–217 行:

```typescript
const loading = ref(false)          // 提交按钮的 loading 态
const loadingProgress = ref(0)      // 进度条百分比
const loadingStatus = ref('')       // 进度文案
```

**`reactive(obj)`** 包装整个对象,属性直接读写(无 `.value`)。Home.vue 224–233 行的表单数据:

```typescript
const formData = reactive<TripFormState>({
  city: '',
  start_date: null,
  end_date: null,
  travel_days: 1,
  transportation: '公共交通',
  accommodation: '经济型酒店',
  preferences: [],
  free_text_input: ''
})
```

`ref` vs `reactive` 的选型经验:**单值用 ref,成组表单用 reactive;reactive 的陷阱是整体替换会丢失响应式**(`formData = {...}` 不行,只能逐属性改)——所以表单复位要写成 `Object.assign(formData, {...})`。

**`watch(source, cb)`** 监听变化执行副作用。Home.vue 236–249 行是全项目最有教学价值的一段——日期联动自动算天数:

```typescript
watch([() => formData.start_date, () => formData.end_date], ([start, end]) => {
  if (start && end) {
    const days = end.diff(start, 'day') + 1      // 含头含尾: 1号到3号算 3 天
    if (days > 0 && days <= 30) {
      formData.travel_days = days
    } else if (days > 30) {
      message.warning('旅行天数不能超过30天')      // 对齐后端 le=30
      formData.end_date = null
    } else {
      message.warning('结束日期不能早于开始日期')   // 对齐后端 ge=1
      formData.end_date = null
    }
  }
})
```

三个细节:源写成函数 `() => formData.start_date` 是因为 reactive 对象的属性要在 getter 里取;`end.diff(start, 'day') + 1` 的"+1"是"含头含尾"的日期语义;两个分支处理的就是本课实验要"正规化"的两条校验——现在它们靠 `message.warning` + 清空值兜底,实验里你会把它们升级成表单内联规则。另一个值得注意的空白:全项目几乎没用过 `computed`(计算属性)——派生值现在都存进了状态。`travel_days` 其实可以从日期推导(变成 `computed`),这正是选做作业:

```typescript
// computed 的样子:像 ref 一样用,值由 getter 自动派生、自动缓存
const travelDays = computed(() => {
  if (!formData.start_date || !formData.end_date) return 0
  const days = formData.end_date.diff(formData.start_date, 'day') + 1
  return (days > 0 && days <= 30) ? days : 0        // 0 表示"日期不合法"
})
```

**ref / reactive / computed / watch 的分工一句话版:ref 装单值,reactive 装成组状态,computed 装"由别处算出来的值",watch 装"值变了之后要干的副作用"。** 表单校验里的 `message.warning` 就是典型副作用——它不属于任何状态,所以放 watch 而不是 computed。

## 23.3 组件通信:props / emit 与 v-model

**props** 是父传子的单向数据流,**emit** 是子通知父的事件通道,`v-model` 则是"props + emit"的语法糖封装。本项目的现实是:**三个视图之间目前没有任何组件级通信**——Home 把结果写进 `sessionStorage`(`Home.vue` 299 行),Result 再读出来(330 行),靠浏览器存储而非 props 传数据。所以你在仓库里找不到自定义的 props/emit 用例——**第一次真正需要它们,就是第 24 课拆分 Result.vue 的时候**。本课先把语法立起来:

```typescript
// 子组件 DayCard.vue(第 24 课会出现)
const props = defineProps<{ day: DayPlan; editMode: boolean }>()
const emit = defineEmits<{ (e: 'move', dir: 'up' | 'down'): void; (e: 'delete'): void }>()
```

```html
<!-- 父组件里使用 -->
<DayCard :day="day" :edit-mode="editMode" @move="moveAttraction" @delete="deleteAttraction" />
```

用一个 20 行的迷你组件把这套语法完整走一遍(它就是第 24 课 `DayCard` 的练习预演)。新建 `components/RatingTag.vue`:

```vue
<template>
  <span class="rating-tag" @click="$emit('change', props.modelValue + 1)">
    评分: {{ props.modelValue }} ⭐(点击 +1)
  </span>
</template>

<script setup lang="ts">
const props = defineProps<{ modelValue: number }>()       // 只收,不改
const emit = defineEmits<{ (e: 'change', value: number): void }>()   // 只上报
</script>
```

父组件里 `<RatingTag v-model="rating" />` 即可双向绑定——因为 `v-model` 在子组件侧的展开规则就是:接收 `modelValue` prop、emit `update:modelValue` 事件(Ant Design Vue 的 `v-model:value` 只是给 prop 换了个名字)。**记住这条展开规则,第 24 课拆组件时你写的每一个 emit 都符合它。**

**v-model 的现成用例**倒是满屏都是——全部来自 Ant Design Vue 组件:`a-input v-model:value="formData.city"`(39 行)、`a-date-picker`(56、70 行)、`a-select`(105、118 行)、`a-checkbox-group`(132 行)、`a-textarea`(155 行)。Vue3 的 `v-model:value` 等价于 `:value="x"` + `@update:value="x = $event"`——理解这个展开式,你就明白任何组件库的双向绑定。

## 23.4 TypeScript 接口与前后端数据契约

`frontend/src/types/index.ts`(95 行)是前端的"法律",`schemas.py`(207 行)是后端的"法律"。**没有工具保证它们一致——这是全项目最重要的工程事实之一**,必须靠人肉对照维护。逐字段过一遍:

| TS 接口(行号) | Pydantic 模型(行号) | 对照结论 |
|---|---|---|
| `Location`(3–6) | `Location`(54–57) | 完全一致 |
| `Attraction`(8–18) | `Attraction`(60–72) | **TS 缺 `photos`、`poi_id` 两个字段**(后端 69–70 行有)——契约漂移! |
| `Meal`(20–27) | `Meal`(75–82) | 一致(`type` 的字面量联合是 TS 更强处) |
| `Hotel`(29–38) | `Hotel`(85–94) | 一致 |
| `Budget`(40–46) | `Budget`(133–139) | 一致 |
| `DayPlan`(48–57) | `DayPlan`(97–106) | 一致 |
| `WeatherInfo`(59–67) | `WeatherInfo`(109–130) | **类型不对等,见下文** |
| `TripPlan`(69–77) | `TripPlan`(142–150) | 一致 |
| `TripFormData`(79–88) | `TripRequest`(10–33) | 形状一致,日期的"表单态/传输态"差异见 23.6 |
| `TripPlanResponse`(90–94) | `TripPlanResponse`(153–157) | 一致 |

三处"不对等"值得逐个咀嚼:

1. **`Attraction` 缺字段(真漂移)。** 后端会返回 `photos` 和 `poi_id`(69–70 行),前端接口没有声明。TS 不报错、运行也不炸,但前端代码**永远无法使用**这两个字段而不被编译器提醒——契约漂移的代价是"能力静默丢失"。选做作业里补齐它。
2. **`WeatherInfo.day_temp`:TS 是 `number`,Python 是 `Union[int, str]`(114 行)。** 为什么前端敢只写 number?因为后端 119–130 行的温度校验器保证 API 出口的一定是 int(`"25°C"` → `25`)。这是健康的分工:**后端在边界上把脏数据洗干净,前端契约才敢写死。** 类型系统的边界在哪,取决于谁负责清洗。
3. **TS 可选标记 `?` 与 Pydantic `Optional`/`default` 大体对应但语义有别**:TS 的 `?` 只说"字段可以不出现";Pydantic 的 default 说"不出现时给什么值"。`Attraction.rating?: number` 对应 `rating: Optional[float] = None`(68 行)——一个声明"可能有",一个声明"没有时是什么",后者信息更多。

还有一个必须树立的心智模型:**TS 类型在运行时不存在**。编译后所有接口声明都被擦除,后端返回什么前端就信什么。所以"类型全链路对齐"的尽头是生成工具(如 openapi-typescript 从 FastAPI 的 OpenAPI 文档自动生成 TS)——本课先人肉对齐,工具化留作方向。

## 23.5 精读 api.ts:65 行的请求出口

`frontend/src/services/api.ts`(65 行)是前端唯一的 HTTP 出口:

- 第 4 行:`const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'`——环境变量注入(第 22 课的 VITE_ 前缀知识在这里落地);
- 第 6–12 行:`axios.create`,**`timeout: 120000`(第 8 行)的 2 分钟超时**是在为慢生成兜底——第 27 课的 SSE 会让它光荣退休;
- 第 15–36 行:两个拦截器,统一打 `console.log`——这是**前端的 print 调试**(第 19 课主题在前端的投影,问题也一模一样:无级别、无开关);
- 第 41–49 行:`generateTripPlan` 把 axios 的错误归一化成 `Error`,消息优先取后端 `detail`(对齐 FastAPI 的 `HTTPException` 格式)。

顺带看一眼 `frontend/src/env.d.ts`(git 追踪列表里见过它):它声明了 `ImportMetaEnv` 上这些 `VITE_*` 变量的类型,让 `import.meta.env.VITE_API_BASE_URL` 在 TS 里不报错、还能给补全。**连"环境变量"都有自己的类型契约**——TS 的检查网在本项目里织到了每个角落。

## 23.6 精读 Home.vue 的表单设计

表单结构(template 19–202 行)分三个 `form-section`:目的地与日期 / 偏好设置 / 额外要求,全部受控于 23.2 的 `formData`。两个此前一笔带过的设计,现在值得停下来看:

**① 表单态与传输态的日期分型(219–222 行):**

```typescript
type TripFormState = Omit<TripFormData, 'start_date' | 'end_date'> & {
  start_date: Dayjs | null     // 表单里用 Dayjs(日期组件的操作对象)
  end_date: Dayjs | null
}
```

`TripFormData` 的日期是 `string`,但 `a-date-picker` 读写的是 Dayjs 对象。`Omit + 交叉类型` 在不改动线上契约的前提下,为表单声明了另一种类型——**同一份数据的两种形态**。提交时再转回去(280–283 行):

```typescript
const requestData: TripFormData = {
  ...
  start_date: formData.start_date.format('YYYY-MM-DD'),   // Dayjs → 后端要的字符串
  ...
}
```

**② 假进度条(262–277 行):** `setInterval` 每 500ms 推进 10%,"正在搜索景点 / 正在查询天气 / 正在推荐酒店"全是**本地猜的**,与后端真实进度零关联——它存在的唯一原因是"生成要等几十秒,用户需要点什么"。这个诚实的设计妥协,正是第 26/27 课 SSE 流式输出的存在理由。

## 23.7 动手实验:给表单装上自定义校验

### 任务

把日期合法性从"提交后弹 warning"升级为"表单内联校验",规则与后端 `schemas.py` 15 行的 `travel_days: ge=1, le=30` 对齐。

Ant Design Vue 的 `a-form-item` 支持 `:rules`,校验器函数返回 `Promise.reject(文案)` 即报错。改造 `Home.vue`:

```typescript
// <script setup> 里
const validateEndDate = async (_rule: any, value: Dayjs | null) => {
  if (!value) return                                   // 空值交给 required 规则
  if (formData.start_date && value.isBefore(formData.start_date, 'day')) {
    return Promise.reject('结束日期不能早于开始日期')      // 对齐 schemas.py travel_days ge=1
  }
  if (formData.start_date && value.diff(formData.start_date, 'day') + 1 > 30) {
    return Promise.reject('行程不能超过 30 天')           // 对齐 schemas.py travel_days le=30
  }
}
```

```html
<!-- template 里,替换原来的 end_date 表单项规则(65 行) -->
<a-form-item name="end_date"
  :rules="[
    { required: true, message: '请选择结束日期' },
    { validator: validateEndDate, trigger: 'change' }
  ]">
```

再给 `start_date` 补一条"不得早于今天"的规则(合理产品语义,后端没管——**前端可以比后端严格,不能比后端宽松**)。完成顺序:先改 template 规则 → 填一个早于开始的结束日期,观察红字与表单拦截 → 再确认 23.2 的 `watch` 兜底逻辑仍在(双保险,不是重复代码:**rules 管用户输入路径,watch 管程序赋值路径**)。

### 完成标准

- [ ] 结束日期早于开始日期:表单内联红字,点击提交被拦截;
- [ ] 间隔 31 天:内联红字"行程不能超过 30 天";
- [ ] 间隔恰 30 天:正常通过(边界值必须亲手试);
- [ ] 后端 `/docs` 直接发 `travel_days: 31` 仍被 Pydantic 拒绝(证明后端防线未撤);
- [ ] 正常日期区间生成行程,`travel_days` 与天数显示一致。

### 常见卡点

- **Q:validator 里 `this.formData` 拿不到?** `<script setup>` 没有 this,直接闭包引用 `formData` 即可(示例代码就是这么写的)。
- **Q:改完没效果?** 三查:`trigger: 'change'` 写了没;`name="end_date"` 与 rules 挂在同一个 `a-form-item` 上;Dayjs 的 `isBefore` 第二个参数 `'day'` 表示按天比较(去掉会把当天 23:00 判晚于当天 00:01)。
- **Q:为什么两边都要校验?** 前端校验管体验(即时反馈、省一次无效请求),后端校验管安全(绕过浏览器直接 curl 的请求只有 Pydantic 拦得住)——**永远不信任单侧**。
- **Q:`rules` 报错信息没出现,但提交也被拦了?** Ant Design Vue 的表单校验状态挂在 `a-form-item` 的 `name` 上;若你把 rules 写在了内层元素或 name 拼写不一致,校验会静默失效。打开 DevTools 看该 `a-form-item` 是否带上了 `ant-form-item-with-help` 类名,即可确认规则是否被触发。

---

## 23.8 课后作业与思考题

**必做:**

1. 完成实验;把 `validateEndDate` 的三条规则写进 `docs/lesson23-notes.md` 并注明与 `schemas.py` 哪一行对齐;
2. 给 `free_text_input` 补前端长度校验(上限 200,与第 22 课你加的 `max_length=200` 对齐)——前后端同一契约,两个文件,一次对齐。

**选做(思考,可动手):**

1. 补齐 23.4 发现的契约漂移:给 `types/index.ts` 的 `Attraction` 加上 `photos?: string[]` 与 `poi_id?: string`(与 `schemas.py` 69–70 行一致)——然后体会"只加类型不动逻辑"的安全:编译过了,行为没变;
2. 把 `travel_days` 从"watch 里赋值的存储状态"改成 `computed`(由日期推导),评估哪些地方要跟着改;如果改动牵连太广,写 50 字说明为什么"看起来更优雅"的方案不一定值得。

## 下节预告

**第 24 课:前端进阶:组件化与 Composable 抽取。** `Result.vue` 的 1391 行终于要动了:地图、每日卡片、预算面板、导出四块职责如何划分,`useTripPlan` 怎么把有状态逻辑从视图里剥出来,`provide/inject` 什么时候才值得用——拆完手动回归,为模块五收官。

---

*本课行号基于 2026-09-11 的 main 分支;配套代码请在本仓库内对照阅读。*
