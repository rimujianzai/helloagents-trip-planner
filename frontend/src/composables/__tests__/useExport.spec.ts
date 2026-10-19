import { beforeEach, describe, expect, it, vi } from 'vitest'
import { exportPlanAsImage, exportPlanAsPDF } from '../useExport'

// html2canvas / jsPDF 都是真·浏览器渲染库，happy-dom 里跑不了真渲染。
// mock 掉它们，只验证 useExport 自己的编排逻辑：克隆、样式改写、地图快照、清理。
const html2canvasMock = vi.fn()
vi.mock('html2canvas', () => ({
  default: (...args: unknown[]) => html2canvasMock(...args)
}))

const addImageMock = vi.fn()
const addPageMock = vi.fn()
const saveMock = vi.fn()
vi.mock('jspdf', () => ({
  default: class FakeJsPDF {
    addImage = addImageMock
    addPage = addPageMock
    save = saveMock
  }
}))

function buildFixture() {
  document.body.innerHTML = ''

  const main = document.createElement('div')
  main.className = 'main-content'
  main.style.width = '800px'
  main.innerHTML = `
    <div class="ant-card">
      <div class="ant-card-head">标题</div>
      <div class="ant-card-body">
        <div class="budget-total">总计</div>
        <div class="budget-item">门票</div>
      </div>
    </div>
    <div id="amap-container"><canvas></canvas></div>
  `
  document.body.appendChild(main)

  // 伪造地图 canvas：toDataURL 返回一张 1x1 png
  const canvas = main.querySelector('canvas') as HTMLCanvasElement
  vi.spyOn(canvas, 'toDataURL').mockReturnValue('data:image/png;base64,MAPSNAP')

  // 拦截 <a download> 的点击（happy-dom 里 click 会触发导航逻辑，不能真点）
  const clickSpy = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(clickSpy)

  return { main, canvas, clickSpy }
}

describe('useExport', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    html2canvasMock.mockReset()
    addImageMock.mockReset()
    addPageMock.mockReset()
    saveMock.mockReset()
    // 默认让 html2canvas 返回可用的 canvas
    html2canvasMock.mockResolvedValue({
      toDataURL: () => 'data:image/png;base64,RENDERED',
      width: 800,
      height: 2000
    })
  })

  it('导出图片：离屏容器被创建、地图快照注入、卡片样式改写、最后清理', async () => {
    const { main, canvas, clickSpy } = buildFixture()
    const toDataSpy = vi.spyOn(canvas, 'toDataURL')

    await exportPlanAsImage('杭州')

    // html2canvas 收到的容器不在文档流里（-9999px 离屏）
    expect(html2canvasMock).toHaveBeenCalledTimes(1)
    const container = html2canvasMock.mock.calls[0][0] as HTMLElement
    expect(container.style.position).toBe('absolute')
    expect(container.style.left).toBe('-9999px')
    expect(container.style.width).toBe(main.offsetWidth + 'px')

    // 地图 canvas 被替换成快照 <img>
    const mapSlot = container.querySelector('#amap-container') as HTMLElement
    expect(mapSlot.innerHTML).toContain('data:image/png;base64,MAPSNAP')
    expect(mapSlot.querySelector('img')).not.toBeNull()
    expect(toDataSpy).toHaveBeenCalledWith('image/png')

    // antd 卡片类被改写成适合打印的静态样式
    // 注意：composable 会把 .ant-card 的 className 清空，所以只能通过子元素反查
    const head = container.querySelector('.ant-card-head') as HTMLElement
    const card = head.parentElement as HTMLElement
    expect(card.className).toBe('') // 类名清空，防止 scoped 样式干扰
    // happy-dom 保留原值 '#ffffff'，浏览器里是 'rgb(255, 255, 255)' —— 两者都算对
    expect(['#ffffff', 'rgb(255, 255, 255)']).toContain(card.style.backgroundColor)

    // 触发了下载
    expect(clickSpy).toHaveBeenCalledTimes(1)

    // 渲染完成后容器已从 body 移除（无残留）
    expect(document.body.contains(container)).toBe(false)
  })

  it('导出 PDF：单页只 addImage 一次，内容超高自动分页', async () => {
    buildFixture()

    // 让渲染结果非常高 → 触发分页循环
    html2canvasMock.mockResolvedValue({
      toDataURL: () => 'data:image/png;base64,RENDERED',
      width: 800,
      height: 8000 // 8000/800 宽高比 → PDF 高约 2100mm，远超一页 297mm
    })

    await exportPlanAsPDF('杭州')

    expect(addImageMock).toHaveBeenCalled()
    expect(saveMock).toHaveBeenCalledWith(expect.stringContaining('旅行计划_杭州_'))
    // 分页数 = ceil(总高/297)，肯定不止一页
    expect(addPageMock.mock.calls.length).toBeGreaterThan(0)
    // addImage 次数 = 页数
    expect(addImageMock.mock.calls.length).toBe(addPageMock.mock.calls.length + 1)
  })

  it('页面上没有 .main-content 时抛错（不静默成功）', async () => {
    document.body.innerHTML = ''
    await expect(exportPlanAsImage('杭州')).rejects.toThrow('未找到内容元素')
    await expect(exportPlanAsPDF('杭州')).rejects.toThrow('未找到内容元素')
    expect(html2canvasMock).not.toHaveBeenCalled()
  })

  it('html2canvas 抛异常时容器也会被清理（finally 兜底）', async () => {
    buildFixture()
    html2canvasMock.mockRejectedValue(new Error('渲染失败'))

    await expect(exportPlanAsImage('杭州')).rejects.toThrow('渲染失败')

    // 离屏容器不能泄漏在 body 里
    const leftovers = Array.from(document.body.children).filter(
      (el) => (el as HTMLElement).style.left === '-9999px'
    )
    expect(leftovers).toHaveLength(0)
  })
})
