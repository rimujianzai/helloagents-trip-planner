import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAmap } from '../useAmap'
import type { TripPlan } from '@/types'

// 用假 AMap 命名空间替代真实 SDK（真实 SDK 要联网 + 消耗配额）。
// 记录构造参数，就能断言「地图中心点」这类关键行为。
function makeFakeAMap() {
  const constructed: { marker: unknown[]; map: unknown[]; polyline: unknown[] } = {
    marker: [],
    map: [],
    polyline: []
  }
  const added: unknown[] = []
  const mapInstances: FakeMap[] = []

  class FakeMap {
    // add 用 vi.fn 包一层，方便断言调用次数
    add = vi.fn((items: unknown) => {
      if (Array.isArray(items)) added.push(...items)
      else added.push(items)
    })
    remove = vi.fn()
    clearMap = vi.fn()
    destroy = vi.fn()
    setFitView = vi.fn()
    // 真实签名是 new AMap.Map(container, options) —— 两个参数
    constructor(_container: unknown, options: unknown) {
      constructed.map.push(options)
      mapInstances.push(this)
    }
  }
  class FakeMarker {
    constructor(options: unknown) {
      constructed.marker.push(options)
      Object.assign(this, options)
    }
    on = vi.fn()
    getPosition = () => (this as { position?: number[] }).position
  }
  class FakePolyline {
    constructor(options: unknown) {
      constructed.polyline.push(options)
    }
  }
  class FakeInfoWindow {
    setContent = vi.fn()
    open = vi.fn()
  }
  class FakePixel {
    constructor(public x: number, public y: number) {}
  }

  const namespace = {
    Map: FakeMap,
    Marker: FakeMarker,
    Polyline: FakePolyline,
    InfoWindow: FakeInfoWindow,
    Pixel: FakePixel
  }

  return { namespace, constructed, added, mapInstances }
}

const loadMock = vi.fn()
vi.mock('@amap/amap-jsapi-loader', () => ({
  default: {
    load: (opts: unknown) => loadMock(opts)
  }
}))

function makePlan(attrs: Array<{ lon?: number; lat?: number }>): TripPlan {
  return {
    city: '测试城',
    start_date: '2026-10-20',
    end_date: '2026-10-21',
    days: [
      {
        date: '2026-10-20',
        day_index: 0,
        description: 'd',
        transportation: 't',
        accommodation: 'a',
        attractions: attrs.map((a, i) => ({
          name: `景点${i}`,
          address: '地址',
          location:
            a.lon != null && a.lat != null
              ? { longitude: a.lon, latitude: a.lat }
              : undefined,
          visit_duration: 60,
          description: 'd',
          // 以下三个字段后端一定会返回（category / poi_id 允许为 null，
          // ticket_price 有默认值 0）。类型改为从 openapi 派生后，
          // mock 数据也得给全，否则编译期就过不去。
          category: null,
          poi_id: null,
          ticket_price: 0
        })),
        meals: []
      }
    ],
    weather_info: [],
    overall_suggestions: 's',
    // 后端必定返回该字段（false = 正常计划，true = 降级占位），
    // 类型从 openapi 派生后 mock 必须给全
    is_fallback: false
  }
}

describe('useAmap', () => {
  beforeEach(() => {
    loadMock.mockReset()
  })

  it('初始中心取第一个有坐标的景点，而不是写死北京', async () => {
    const { namespace, constructed } = makeFakeAMap()
    loadMock.mockResolvedValue(namespace)

    const amap = useAmap()
    const ok = await amap.initMap(
      makePlan([
        { lon: 120.14, lat: 30.25 }, // 杭州西湖
        { lon: 120.16, lat: 30.26 }
      ])
    )

    expect(ok).toBe(true)
    const mapOptions = constructed.map[0] as { center: number[] }
    // 回归测试：这里曾经写死 [116.39, 39.91]（北京），请求上海/杭州时先闪一下北京
    expect(mapOptions.center[0]).toBeCloseTo(120.14)
    expect(mapOptions.center[1]).toBeCloseTo(30.25)
  })

  it('没有任何坐标时才回退到北京默认点', async () => {
    const { namespace, constructed } = makeFakeAMap()
    loadMock.mockResolvedValue(namespace)

    const amap = useAmap()
    await amap.initMap(makePlan([{ lon: undefined, lat: undefined }]))

    const mapOptions = constructed.map[0] as { center: number[] }
    expect(mapOptions.center).toEqual([116.397128, 39.916527])
  })

  it('坐标判空用 != null：经纬度为 0 是合法坐标，不会被丢掉', async () => {
    const { namespace, constructed } = makeFakeAMap()
    loadMock.mockResolvedValue(namespace)

    const amap = useAmap()
    await amap.initMap(
      makePlan([
        { lon: 0, lat: 0 }, // 本初子午线 × 赤道：合法！真值判断会把它吃掉
        { lon: 120, lat: 30 }
      ])
    )

    // 两个标记都建出来
    expect(constructed.marker).toHaveLength(2)
  })

  it('无坐标的景点不建标记', async () => {
    const { namespace, constructed } = makeFakeAMap()
    loadMock.mockResolvedValue(namespace)

    const amap = useAmap()
    await amap.initMap(
      makePlan([{ lon: undefined, lat: undefined }, { lon: 120, lat: 30 }])
    )

    expect(constructed.marker).toHaveLength(1)
  })

  it('refreshMarkers 先 clearMap 再重建（编辑保存后不叠标记）', async () => {
    const { namespace, mapInstances } = makeFakeAMap()
    loadMock.mockResolvedValue(namespace)

    const amap = useAmap()
    await amap.initMap(makePlan([{ lon: 120, lat: 30 }]))

    const mapInstance = mapInstances[0]
    const markersAfterInit = mapInstance.add.mock.calls.length

    amap.refreshMarkers(makePlan([{ lon: 120.1, lat: 30.1 }]))

    // 重建前必须先清空：clearMap 被调用，且重新 add 了标记
    expect(mapInstance.clearMap).toHaveBeenCalled()
    expect(mapInstance.add.mock.calls.length).toBe(markersAfterInit + 1)
  })

  it('destroy 后地图实例被销毁', async () => {
    const { namespace, mapInstances } = makeFakeAMap()
    loadMock.mockResolvedValue(namespace)

    const amap = useAmap()
    await amap.initMap(makePlan([{ lon: 120, lat: 30 }]))
    amap.destroy()
    expect(mapInstances[0].destroy).toHaveBeenCalled()
  })

  it('initMap 失败（如 key 无效）返回 false 而不是抛异常', async () => {
    loadMock.mockRejectedValue(new Error('INVALID_USER_KEY'))
    const amap = useAmap()
    const ok = await amap.initMap(makePlan([{ lon: 120, lat: 30 }]))
    expect(ok).toBe(false)
  })
})
