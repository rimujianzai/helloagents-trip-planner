import { beforeEach, describe, expect, it } from 'vitest'
import { buildShareLink, readPlanFromUrl, isSharedUrl, updateUrlHash } from '../usePlanShare'
import type { TripPlan } from '@/types'

// usePlanShare 依赖三类浏览器 API：
// - btoa/atob：Node 16+ 全局自带
// - CompressionStream/DecompressionStream：Node 18+ 全局自带（happy-dom 环境继承）
// - location：happy-dom 提供
// 这个测试同时是在验证「运行环境真的有这些 API」—— 缺了就该在 CI 里暴露出来。

const plan: TripPlan = {
  city: '杭州',
  start_date: '2026-10-20',
  end_date: '2026-10-22',
  days: [
    {
      date: '2026-10-20',
      day_index: 0,
      description: '第一天',
      transportation: '公共交通',
      accommodation: '经济型酒店',
      attractions: [
        {
          name: '西湖',
          address: '杭州市西湖区',
          location: { longitude: 120.14, latitude: 30.25 },
          visit_duration: 120,
          description: '湖'
        }
      ],
      meals: [{ type: 'breakfast', name: '早餐' }]
    }
  ],
  weather_info: [],
  overall_suggestions: '总体建议',
  is_fallback: false
}

describe('usePlanShare', () => {
  beforeEach(() => {
    location.hash = ''
  })

  it('编码后再解码能得到原计划（gzip 往返无损）', async () => {
    // 小数据 gzip+base64 后可能反而更大（压缩头 + base64 膨胀 4/3），
    // 用足够大的重复文本让压缩率体现出来
    const bigPlan: TripPlan = {
      ...plan,
      overall_suggestions: '建议重复内容。'.repeat(200)
    }
    const link = await buildShareLink(bigPlan)
    expect(link).toContain('#plan=')

    const encoded = link.split('#plan=')[1]
    const raw = JSON.stringify(bigPlan)
    expect(encoded.length).toBeLessThan(raw.length)

    // 模拟对方打开链接
    location.hash = `#plan=${encoded}`
    const decoded = await readPlanFromUrl()
    expect(decoded).toEqual(bigPlan)
  })

  it('URL 里没有 #plan= 时返回 null', async () => {
    expect(await readPlanFromUrl()).toBeNull()
  })

  it('hash 被篡改时返回 null 而不是抛异常', async () => {
    location.hash = '#plan=not-valid-base64!!!'
    expect(await readPlanFromUrl()).toBeNull()
  })

  it('isSharedUrl 只认 #plan= 前缀', () => {
    location.hash = '#plan=abc'
    expect(isSharedUrl()).toBe(true)
    location.hash = '#other=1'
    expect(isSharedUrl()).toBe(false)
    location.hash = ''
    expect(isSharedUrl()).toBe(false)
  })

  it('分享链接包含 origin 和 pathname（不带旧 hash）', async () => {
    location.hash = '#something-old'
    const link = await buildShareLink(plan)
    expect(link.startsWith(`${location.origin}${location.pathname}#plan=`)).toBe(true)
    expect(link).not.toContain('something-old')
  })

  it('updateUrlHash 用最新计划覆盖地址栏旧链接', async () => {
    // 模拟「编辑前生成的旧分享链接还挂在地址栏」的场景
    location.hash = '#plan=stale-old-version'

    await updateUrlHash(plan)

    expect(isSharedUrl()).toBe(true)
    expect(location.hash).not.toContain('stale-old-version')

    // 覆盖后必须能解回最新计划 —— 这正是「改完复制地址栏发人」的正确性保证
    const decoded = await readPlanFromUrl()
    expect(decoded).toEqual(plan)
  })
})
