import { useState, useRef, useEffect, useCallback } from 'react'

const SPLIT_OPTIONS = [
  { value: 'low',    label: '低 (5 段)' },
  { value: 'medium', label: '中 (10 段)' },
  { value: 'high',   label: '高 (15 段)' },
]
const TYPE_OPTIONS = [
  { value: 'video', label: '🎬 视频' },
  { value: 'image', label: '🖼 图片' },
]
const RATIO_OPTIONS = [
  { value: '16:9', label: '16:9 横屏' },
  { value: '9:16', label: '9:16 竖屏' },
]
const QUALITY_OPTIONS = [
  { value: '4k',    label: '4K' },
  { value: '1080p', label: '1080p' },
  { value: '720p',  label: '720p' },
  { value: '480p',  label: '480p' },
  { value: '360p',  label: '360p' },
]
const SOURCE_OPTIONS = [
  { value: 'pexels',  label: 'Pexels' },
  { value: 'pixabay', label: 'Pixabay' },
]

function RadioGroup({ label, options, value, onChange }) {
  return (
    <div>
      <p className="text-sm font-medium text-gray-500 mb-2">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => (
          <button
            key={opt.value}
            onClick={() => onChange(opt.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
              value === opt.value
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-700 border-gray-200 hover:border-indigo-300'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function CheckboxGroup({ label, options, values, onChange }) {
  const toggle = (v) => {
    onChange(values.includes(v) ? values.filter(x => x !== v) : [...values, v])
  }
  return (
    <div>
      <p className="text-sm font-medium text-gray-500 mb-2">{label}</p>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => (
          <button
            key={opt.value}
            onClick={() => toggle(opt.value)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-all ${
              values.includes(opt.value)
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-700 border-gray-200 hover:border-indigo-300'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [srtFile, setSrtFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [split, setSplit] = useState('medium')
  const [mediaType, setMediaType] = useState('video')
  const [ratio, setRatio] = useState('16:9')
  const [quality, setQuality] = useState('1080p')
  const [sources, setSources] = useState(['pexels'])

  const [status, setStatus] = useState('idle') // idle | analyzing | review | starting | running | done | failed
  const [logs, setLogs] = useState([])
  const [jobId, setJobId] = useState(null)
  const [srtId, setSrtId] = useState(null)
  const [segments, setSegments] = useState([])
  const [error, setError] = useState('')

  const logRef = useRef(null)
  const pollRef = useRef(null)
  const fileInputRef = useRef(null)

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logs])

  // Polling
  const startPolling = useCallback((id) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${id}/`)
        const data = await res.json()
        setLogs(data.logs || [])
        if (data.status === 'done') {
          setStatus('done')
          clearInterval(pollRef.current)
          // Auto-download
          window.location.href = `/api/jobs/${id}/download/`
        } else if (data.status === 'failed') {
          setStatus('failed')
          setError(data.error || '未知错误')
          clearInterval(pollRef.current)
        }
      } catch (e) {
        console.error(e)
      }
    }, 2000)
  }, [])

  useEffect(() => () => clearInterval(pollRef.current), [])

  const handleFile = (file) => {
    if (file && (file.name.endsWith('.srt') || file.type === 'application/x-subrip')) {
      setSrtFile(file)
      setSrtId(null)
      setSegments([])
      setStatus('idle')
      setError('')
    } else {
      alert('请选择 .srt 格式的文件')
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  const handleAnalyze = async (regenerate = false) => {
    if (!srtFile && !srtId) return
    setStatus('analyzing')
    setError('')

    const form = new FormData()
    if (regenerate && srtId) {
      form.append('srt_id', srtId)
    } else {
      form.append('srt_file', srtFile)
    }
    form.append('split', split)
    form.append('media_type', mediaType)

    try {
      const res = await fetch('/api/analyze/', { method: 'POST', body: form })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setSrtId(data.srt_id)
      setSegments(data.segments || [])
      setStatus('review')
    } catch (e) {
      setStatus(regenerate && segments.length ? 'review' : 'idle')
      setError(e.message)
    }
  }

  const updateSegment = (index, field, value) => {
    setSegments(current => current.map((segment, i) => (
      i === index ? { ...segment, [field]: value } : segment
    )))
  }

  const removeSegment = (index) => {
    setSegments(current => current.filter((_, i) => i !== index))
  }

  const addSegment = () => {
    setSegments(current => [...current, { start_time: '', segment: '', query: '' }])
  }

  const handleConfirm = async () => {
    if (!srtId || !segments.length) return
    if (sources.length === 0) { alert('请至少选择一个素材来源'); return }
    const invalidIndex = segments.findIndex(segment => !segment.segment?.trim() || !segment.query?.trim())
    if (invalidIndex >= 0) {
      setError(`第 ${invalidIndex + 1} 个片段的引用内容和搜索词不能为空`)
      return
    }

    setStatus('starting')
    setLogs([])
    setError('')

    const form = new FormData()
    form.append('srt_id', srtId)
    form.append('segments', JSON.stringify(segments))
    form.append('split', split)
    form.append('media_type', mediaType)
    form.append('ratio', ratio)
    form.append('quality', quality)
    sources.forEach(s => form.append('sources', s))

    try {
      const res = await fetch('/api/jobs/', { method: 'POST', body: form })
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.error || `HTTP ${res.status}`)
      }
      const data = await res.json()
      setJobId(data.job_id)
      setStatus('running')
      startPolling(data.job_id)
    } catch (e) {
      setStatus('review')
      setError(e.message)
    }
  }

  const handleReset = () => {
    clearInterval(pollRef.current)
    setStatus('idle')
    setLogs([])
    setError('')
    setJobId(null)
    setSrtId(null)
    setSegments([])
    setSrtFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const fileLocked = ['analyzing', 'starting', 'running'].includes(status)

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Header */}
        <div className="text-center">
          <h1 className="text-3xl font-bold text-gray-900">🎬 B-Roll Helper</h1>
          <p className="mt-1 text-gray-500 text-sm">上传 SRT 脚本，AI 自动分析并从 Pexels / Pixabay 拉取 B-Roll 素材</p>
        </div>

        {/* Upload */}
        <div
          className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${
            fileLocked ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'
          } ${
            dragging ? 'border-indigo-400 bg-indigo-50' : srtFile ? 'border-green-400 bg-green-50' : 'border-gray-200 bg-white hover:border-indigo-300'
          }`}
          onClick={() => { if (!fileLocked) fileInputRef.current?.click() }}
          onDragOver={(e) => { e.preventDefault(); if (!fileLocked) setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { if (fileLocked) e.preventDefault(); else handleDrop(e) }}
        >
          <input ref={fileInputRef} type="file" accept=".srt" className="hidden" disabled={fileLocked}
            onChange={e => handleFile(e.target.files[0])} />
          {srtFile ? (
            <div>
              <p className="text-green-600 font-medium text-lg">✅ {srtFile.name}</p>
              <p className="text-gray-400 text-sm mt-1">点击重新选择文件</p>
            </div>
          ) : (
            <div>
              <p className="text-4xl mb-2">📄</p>
              <p className="text-gray-600 font-medium">拖拽或点击上传 SRT 文件</p>
              <p className="text-gray-400 text-sm mt-1">.srt 格式</p>
            </div>
          )}
        </div>

        {/* Params */}
        {(status === 'idle' || status === 'analyzing') && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
          <h2 className="text-base font-semibold text-gray-800">参数设置</h2>
          <RadioGroup label="拆分程度" options={SPLIT_OPTIONS} value={split} onChange={setSplit} />
          <RadioGroup label="素材类型" options={TYPE_OPTIONS} value={mediaType} onChange={setMediaType} />
          <RadioGroup label="画面比例" options={RATIO_OPTIONS} value={ratio} onChange={setRatio} />
          {mediaType === 'video' && (
            <RadioGroup label="视频清晰度" options={QUALITY_OPTIONS} value={quality} onChange={setQuality} />
          )}
          <CheckboxGroup label="素材来源" options={SOURCE_OPTIONS} values={sources} onChange={setSources} />
        </div>
        )}

        {/* Generate Button */}
        {status === 'idle' && (
          <button
            onClick={() => handleAnalyze(false)}
            disabled={!srtFile}
            className="w-full py-3 rounded-xl font-semibold text-white text-base transition-all
              bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ✨ 生成搜索词并预览
          </button>
        )}

        {status === 'analyzing' && (
          <div className="bg-white rounded-xl border border-indigo-200 p-6 text-center">
            <div className="inline-flex items-center gap-3 text-indigo-700 font-medium">
              <span className="w-5 h-5 rounded-full border-2 border-indigo-200 border-t-indigo-600 animate-spin" />
              AI 正在分析脚本并生成搜索词…
            </div>
            <p className="text-sm text-gray-400 mt-2">此阶段只生成预览，不会搜索或下载素材</p>
          </div>
        )}

        {(status === 'review' || status === 'starting') && (
          <div className="space-y-4">
            <div className="bg-indigo-50 border border-indigo-200 rounded-xl p-4">
              <h2 className="font-semibold text-indigo-950">确认 B-roll 片段与搜索词</h2>
              <p className="text-sm text-indigo-700 mt-1">
                请检查或直接修改下方内容。点击“确认并开始下载”之前，系统不会访问素材网站。
              </p>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-5 grid sm:grid-cols-2 gap-5">
              <RadioGroup label="重新生成的拆分程度" options={SPLIT_OPTIONS} value={split} onChange={setSplit} />
              <RadioGroup label="重新生成的素材类型" options={TYPE_OPTIONS} value={mediaType} onChange={setMediaType} />
            </div>

            {segments.map((segment, index) => (
              <div key={index} className="bg-white rounded-xl border border-gray-200 p-5 space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-800">片段 {index + 1}</span>
                  <button type="button" onClick={() => removeSegment(index)}
                    disabled={status === 'starting'}
                    className="text-xs text-gray-400 hover:text-red-500 disabled:opacity-40">
                    删除
                  </button>
                </div>

                <label className="block">
                  <span className="text-xs font-medium text-gray-500">引用时间</span>
                  <input value={segment.start_time || ''}
                    onChange={e => updateSegment(index, 'start_time', e.target.value)}
                    disabled={status === 'starting'}
                    placeholder="例如 00:00:05"
                    className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:bg-gray-50" />
                </label>

                <label className="block">
                  <span className="text-xs font-medium text-gray-500">引用片段 / 画面内容</span>
                  <textarea value={segment.segment || ''}
                    onChange={e => updateSegment(index, 'segment', e.target.value)}
                    disabled={status === 'starting'}
                    rows={2}
                    className="mt-1 w-full resize-y rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:bg-gray-50" />
                </label>

                <label className="block">
                  <span className="text-xs font-medium text-gray-500">素材搜索词</span>
                  <input value={segment.query || ''}
                    onChange={e => updateSegment(index, 'query', e.target.value)}
                    disabled={status === 'starting'}
                    className="mt-1 w-full rounded-lg border border-indigo-200 bg-indigo-50/50 px-3 py-2 text-sm font-medium text-indigo-950 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:bg-gray-50" />
                </label>
              </div>
            ))}

            <button type="button" onClick={addSegment} disabled={status === 'starting'}
              className="w-full py-2.5 rounded-xl border border-dashed border-gray-300 text-sm text-gray-500 hover:border-indigo-300 hover:text-indigo-600 disabled:opacity-40">
              ＋ 添加片段
            </button>

            {error && <p className="text-red-600 text-sm">{error}</p>}

            <div className="grid sm:grid-cols-2 gap-3">
              <button type="button" onClick={() => handleAnalyze(true)}
                disabled={status === 'starting'}
                className="py-3 rounded-xl border border-indigo-200 bg-white text-indigo-700 font-semibold hover:bg-indigo-50 disabled:opacity-40">
                ↻ 重新生成
              </button>
              <button type="button" onClick={handleConfirm}
                disabled={status === 'starting' || !segments.length}
                className="py-3 rounded-xl bg-indigo-600 text-white font-semibold hover:bg-indigo-700 disabled:opacity-40">
                {status === 'starting' ? '正在启动…' : '✓ 确认并开始下载'}
              </button>
            </div>
          </div>
        )}

        {status === 'idle' && error && (
          <p className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700 text-sm">{error}</p>
        )}

        {/* Progress */}
        {(status === 'running' || status === 'done' || status === 'failed') && (
          <div className="bg-gray-900 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-300">
                {status === 'running' && '⏳ 正在处理...'}
                {status === 'done' && '✅ 完成！ZIP 已自动下载'}
                {status === 'failed' && '❌ 发生错误'}
              </span>
              {status === 'running' && (
                <span className="flex gap-1">
                  {[0,1,2].map(i => (
                    <span key={i} className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
                </span>
              )}
            </div>

            <div ref={logRef}
              className="h-64 overflow-y-auto font-mono text-xs text-green-300 space-y-0.5 pr-1">
              {logs.map((line, i) => (
                <div key={i} className={
                  line.includes('❌') || line.includes('⚠') ? 'text-yellow-400' :
                  line.includes('✅') || line.includes('✓') ? 'text-green-400' :
                  line.startsWith('📦') || line.startsWith('🔍') || line.startsWith('🤖') || line.startsWith('📄')
                    ? 'text-indigo-300 font-semibold' : 'text-gray-300'
                }>{line || '\u00A0'}</div>
              ))}
              {status === 'running' && <div className="text-gray-500 animate-pulse">█</div>}
            </div>

            {status === 'done' && jobId && (
              <a href={`/api/jobs/${jobId}/download/`}
                className="block text-center py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white font-medium text-sm transition-colors">
                📦 重新下载 ZIP
              </a>
            )}

            {status === 'failed' && error && (
              <p className="text-red-400 text-xs">{error}</p>
            )}

            <button onClick={handleReset}
              className="w-full py-2 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm transition-colors">
              重新开始
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
