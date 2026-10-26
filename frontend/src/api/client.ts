// 轻量 fetch 封装 + SSE 流解析
// VITE_API_BASE：部署到 Vercel 等平台时指向公网后端（如 https://api.example.com）；本地留空走 /api 代理
const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    }
  })
  if (!resp.ok) {
    let detail = `请求失败（HTTP ${resp.status}）`
    try {
      const data = await resp.json()
      if (data.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (resp.status === 204) return undefined as T
  return resp.json()
}

export interface SseEvent<T = any> {
  event: string
  data: T
}

/** POST JSON 并解析 SSE 事件流 */
export async function* sseStream<T = any>(path: string, body: any): AsyncGenerator<SseEvent<T>> {
  const resp = await fetch(`${API_BASE}/api${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!resp.ok) {
    let detail = `请求失败（HTTP ${resp.status}）`
    try {
      const data = await resp.json()
      if (data.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      let event = 'message'
      const dataLines: string[] = []
      for (const line of raw.split('\n')) {
        if (line.startsWith('event: ')) event = line.slice(7).trim()
        else if (line.startsWith('data: ')) dataLines.push(line.slice(6))
      }
      if (dataLines.length) {
        let data: any
        try {
          data = JSON.parse(dataLines.join('\n'))
        } catch {
          continue
        }
        yield { event, data }
      }
    }
  }
}

/** 文件上传（带进度回调），返回解析后的 JSON */
export function uploadFile<T = any>(
  path: string,
  file: File,
  onProgress?: (percent: number) => void
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE}/api${path}`)
    xhr.upload.onprogress = e => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText || '{}'))
      } else {
        let detail = `上传失败（HTTP ${xhr.status}）`
        try {
          const d = JSON.parse(xhr.responseText)
          if (d.detail) detail = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail)
        } catch {
          /* ignore */
        }
        reject(new Error(detail))
      }
    }
    xhr.onerror = () => reject(new Error('网络错误，上传失败'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}
