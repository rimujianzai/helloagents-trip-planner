/**
 * 行程导出 composable
 *
 * 把 Result.vue 里 exportAsImage / exportAsPDF 两处几乎完全相同的「克隆 DOM →
 * 截图 → 下载」逻辑抽成共享实现。原先两个函数各 140+ 行、重复率 95%，改一处
 * 要改两遍（手册第 16 节 P1-2 待解决问题）。
 *
 * 这里只负责「拿到一个排版好的离屏容器」，具体的图片/PDF 渲染交给调用方，
 * 这样两个导出按钮复用同一份样式处理代码，且互不干扰。
 */
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'

/**
 * 把页面上的 `.main-content` 克隆到一个离屏容器，并就地改成适合打印的静态样式
 * （去掉 antd 卡片类、改成纯白底 + 圆角阴影，地图 canvas 换成快照图）。
 *
 * @returns 离屏容器与清理函数；若找不到内容区则返回 null
 */
function prepareExportContainer(): { container: HTMLElement; cleanup: () => void } | null {
  const source = document.querySelector('.main-content') as HTMLElement | null
  if (!source) return null

  const container = document.createElement('div')
  container.style.width = source.offsetWidth + 'px'
  container.style.backgroundColor = '#f5f7fa'
  container.style.padding = '20px'
  container.innerHTML = source.innerHTML

  // 地图是 canvas，innerHTML 克隆不到像素，需手动把画布快照塞进去
  const mapCanvas = document
    .getElementById('amap-container')
    ?.querySelector('canvas') as HTMLCanvasElement | null
  if (mapCanvas) {
    const snap = mapCanvas.toDataURL('image/png')
    const target = container.querySelector('#amap-container') as HTMLElement | null
    if (target) {
      target.innerHTML = `<img src="${snap}" style="width:100%;height:100%;object-fit:cover;" />`
    }
  }

  // 统一卡片样式 —— 这些选择器与 Result.vue 的模板结构强耦合，改模板要同步改这里
  container.querySelectorAll('.ant-card').forEach((el) => {
    const card = el as HTMLElement
    card.className = ''
    card.style.setProperty('background-color', '#ffffff')
    card.style.setProperty('border-radius', '12px')
    card.style.setProperty('box-shadow', '0 4px 12px rgba(0, 0, 0, 0.1)')
    card.style.setProperty('margin-bottom', '20px')
    card.style.setProperty('overflow', 'hidden')
  })
  container.querySelectorAll('.ant-card-head').forEach((el) => {
    const head = el as HTMLElement
    head.style.setProperty('background-color', '#667eea')
    head.style.setProperty('color', '#ffffff')
    head.style.setProperty('padding', '16px 24px')
    head.style.setProperty('font-size', '18px')
    head.style.setProperty('font-weight', '600')
  })
  container.querySelectorAll('.ant-card-body').forEach((el) => {
    const body = el as HTMLElement
    body.style.setProperty('background-color', '#ffffff')
    body.style.setProperty('padding', '24px')
  })
  container.querySelectorAll('.hotel-card').forEach((el) => {
    const card = el as HTMLElement
    const head = card.querySelector('.ant-card-head') as HTMLElement | null
    if (head) head.style.setProperty('background-color', '#1976d2')
    card.style.setProperty('background-color', '#e3f2fd')
  })
  container.querySelectorAll('.weather-card').forEach((el) => {
    ;(el as HTMLElement).style.setProperty('background-color', '#e0f7fa')
  })

  const budgetTotal = container.querySelector('.budget-total') as HTMLElement | null
  if (budgetTotal) {
    budgetTotal.style.setProperty('background-color', '#667eea')
    budgetTotal.style.setProperty('color', '#ffffff')
    budgetTotal.style.setProperty('padding', '20px')
    budgetTotal.style.setProperty('border-radius', '12px')
    budgetTotal.style.setProperty('margin-bottom', '20px')
  }
  container.querySelectorAll('.budget-item').forEach((el) => {
    const item = el as HTMLElement
    item.style.setProperty('background-color', '#f5f7fa')
    item.style.setProperty('padding', '16px')
    item.style.setProperty('border-radius', '8px')
    item.style.setProperty('margin-bottom', '12px')
  })

  container.style.position = 'absolute'
  container.style.left = '-9999px'
  document.body.appendChild(container)

  return { container, cleanup: () => document.body.removeChild(container) }
}

async function renderToCanvas(container: HTMLElement): Promise<HTMLCanvasElement> {
  return html2canvas(container, {
    backgroundColor: '#f5f7fa',
    scale: 2,
    logging: false,
    useCORS: true,
    allowTaint: true
  })
}

/** 导出为 PNG 图片并触发下载 */
export async function exportPlanAsImage(city: string): Promise<void> {
  const prepared = prepareExportContainer()
  if (!prepared) throw new Error('未找到内容元素')
  const { container, cleanup } = prepared
  try {
    const canvas = await renderToCanvas(container)
    const link = document.createElement('a')
    link.download = `旅行计划_${city}_${Date.now()}.png`
    link.href = canvas.toDataURL('image/png')
    link.click()
  } finally {
    cleanup()
  }
}

/** 导出为 PDF（A4 纵向，内容超过一页自动分页）并触发下载 */
export async function exportPlanAsPDF(city: string): Promise<void> {
  const prepared = prepareExportContainer()
  if (!prepared) throw new Error('未找到内容元素')
  const { container, cleanup } = prepared
  try {
    const canvas = await renderToCanvas(container)
    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })

    const imgWidth = 210 // A4 宽 (mm)
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    let heightLeft = imgHeight
    let position = 0
    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= 297 // A4 高 (mm)

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= 297
    }

    pdf.save(`旅行计划_${city}_${Date.now()}.pdf`)
  } finally {
    cleanup()
  }
}
