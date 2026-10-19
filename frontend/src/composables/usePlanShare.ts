/**
 * 行程分享 composable
 *
 * 解决「结果不可分享」问题（手册第 16 节 P1-4）：原先行程只存在 sessionStorage，
 * 链接发给别人是空白页。这里把整个 TripPlan 用 gzip 压缩后 base64 编码塞进 URL
 * hash，对方打开同一链接即可还原——纯前端、无需后端、无需数据库。
 *
 * 注意：CompressionStream/DecompressionStream 需要较新的浏览器（Chrome 80+ /
 * Edge / 新版 Firefox / Safari 16.4+）。老浏览器上 sharePlan 会抛错，调用方
 * 捕获后提示「当前浏览器不支持链接分享」即可。
 */
import type { TripPlan } from '@/types'

const HASH_PREFIX = '#plan='

function bytesToBase64(bytes: Uint8Array): string {
  let bin = ''
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin)
}

function base64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const bin = atob(b64)
  // 显式分配 ArrayBuffer：TS 5.7+ 会区分 ArrayBufferLike / ArrayBuffer，
  // 直接 new Uint8Array(len) 推断出的是 ArrayBufferLike，进不了 BlobPart
  const buffer = new ArrayBuffer(bin.length)
  const bytes = new Uint8Array(buffer)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

async function gzip(text: string): Promise<string> {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))
  const buf = await new Response(stream).arrayBuffer()
  return bytesToBase64(new Uint8Array(buf))
}

async function gunzip(b64: string): Promise<string> {
  const stream = new Blob([base64ToBytes(b64)]).stream().pipeThrough(new DecompressionStream('gzip'))
  return new Response(stream).text()
}

/** 把当前计划编码进当前 URL 的 hash，返回完整可分享链接 */
export async function buildShareLink(plan: TripPlan): Promise<string> {
  const encoded = await gzip(JSON.stringify(plan))
  const base = `${location.origin}${location.pathname}`
  return `${base}${HASH_PREFIX}${encoded}`
}

/**
 * 把计划编码后直接写回地址栏 hash（不刷新页面）。
 *
 * 用途：用户编辑行程后点「保存修改」，若只写 sessionStorage，地址栏里还是
 * 编辑前的旧链接 —— 用户直接复制地址栏发给别人，对方看到的仍是改前版本。
 * 这里在保存时同步刷新 hash，保证「地址栏即最新版本」，从根上消除这个坑。
 *
 * 用 history.replaceState 而不是给 location.hash 赋值：后者会往历史栈里
 * 压一条新记录，用户点后退会退到上一个 hash（仍是本页），体验很怪。
 */
export async function updateUrlHash(plan: TripPlan): Promise<void> {
  const encoded = await gzip(JSON.stringify(plan))
  history.replaceState(null, '', `${HASH_PREFIX}${encoded}`)
}

/** 如果当前 URL 带有分享的计划，解码并返回；否则返回 null */
export async function readPlanFromUrl(): Promise<TripPlan | null> {
  if (!location.hash.startsWith(HASH_PREFIX)) return null
  const encoded = location.hash.slice(HASH_PREFIX.length)
  if (!encoded) return null
  try {
    return JSON.parse(await gunzip(encoded)) as TripPlan
  } catch (e) {
    console.error('解析分享链接失败:', e)
    return null
  }
}

/** 判断当前是否处于「通过分享链接打开」的状态 */
export function isSharedUrl(): boolean {
  return location.hash.startsWith(HASH_PREFIX)
}
