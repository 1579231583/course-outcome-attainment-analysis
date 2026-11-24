function authHeaders(extra = {}) {
  const token = localStorage.getItem('obe_token')
  const h = { ...extra }
  if (token) h['Authorization'] = `Bearer ${token}`
  return h
}

async function request(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  })
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const data = await res.json()
      msg = data.detail || data.message || msg
    } catch {
      // ignore
    }
    throw new Error(msg)
  }
  return res.json()
}

export async function downloadBlob(url, filename, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: authHeaders(options.headers || {}),
  })
  if (!res.ok) {
    let msg = `下载失败 (${res.status})`
    try {
      const data = await res.json()
      msg = data.detail || msg
    } catch {
      // ignore
    }
    throw new Error(msg)
  }
  const blob = await res.blob()
  const linkUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = linkUrl
  a.download = filename
  a.click()
  URL.revokeObjectURL(linkUrl)
}

export const api = {
  // 1. 认证与账号
  login: (payload) =>
    request('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  register: (payload) =>
    request('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  adminListUsers: () => request('/api/admin/users'),
  adminCreateUser: (payload) =>
    request('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  adminToggleUser: (id) => request(`/api/admin/users/${id}/toggle`, { method: 'PATCH' }),
  adminResetPassword: (id, password = '123456') =>
    request(`/api/admin/users/${id}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    }),
  adminOverview: () => request('/api/admin/overview'),

  // 2. 第一层：公共教学大纲库
  listSyllabuses: () => request('/api/syllabuses'),
  previewSyllabusPdf: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return request('/api/syllabuses/preview-pdf', { method: 'POST', body: fd })
  },
  publishSyllabuses: (courses) =>
    request('/api/syllabuses/publish-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ courses }),
    }),
  deleteSyllabus: (id) => request(`/api/syllabuses/${id}`, { method: 'DELETE' }),

  // 3. 第二层：统考期末试卷库（按 大纲 + 学期）
  downloadSyllabusPaperTpl: (syllabusId, courseName = '课程', semester = '') => {
    const q = semester ? `?semester=${encodeURIComponent(semester)}` : ''
    return downloadBlob(
      `/api/syllabuses/${syllabusId}/paper-template${q}`,
      `${courseName}_期末试卷结构模板.xlsx`
    )
  },
  previewSyllabusPaper: (syllabusId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/api/syllabuses/${syllabusId}/paper-preview`, { method: 'POST', body: fd })
  },
  saveSyllabusPaper: (syllabusId, payload) =>
    request(`/api/syllabuses/${syllabusId}/papers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deleteExamPaper: (paperId) => request(`/api/exam-papers/${paperId}`, { method: 'DELETE' }),

  // 4. 第三层：教师班级分析任务
  listTasks: () => request('/api/tasks'),
  createTask: (payload) =>
    request('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  getTask: (id) => request(`/api/tasks/${id}`),
  updateTaskRules: (id, payload) =>
    request(`/api/tasks/${id}/rules`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  downloadTaskPaperTpl: (id, courseName = '课程') =>
    downloadBlob(`/api/tasks/${id}/paper-template`, `${courseName}_期末试卷结构模板.xlsx`),
  importTaskPaperExcel: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/api/tasks/${id}/paper-import`, { method: 'POST', body: fd })
  },
  downloadTaskDailyTpl: (id, className = '') =>
    downloadBlob(`/api/tasks/${id}/template/daily`, `${className || '班级'}_平时成绩模板.xlsx`),
  downloadTaskFinalTpl: (id, className = '') =>
    downloadBlob(`/api/tasks/${id}/template/final`, `${className || '班级'}_期末小题成绩模板.xlsx`),
  parseTaskScores: (id, dailyFile, finalFile, dailyMap = null, finalMap = null) => {
    const fd = new FormData()
    fd.append('daily_file', dailyFile)
    fd.append('final_file', finalFile)
    if (dailyMap) fd.append('daily_map', JSON.stringify(dailyMap))
    if (finalMap) fd.append('final_map', JSON.stringify(finalMap))
    return request(`/api/tasks/${id}/parse-scores`, { method: 'POST', body: fd })
  },
  calculateTask: (id, payload) =>
    request(`/api/tasks/${id}/calculate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  updateTaskNotes: (id, payload) =>
    request(`/api/tasks/${id}/notes`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  exportTaskBundle: (id, filename = '课程归档材料.zip') =>
    downloadBlob(`/api/tasks/${id}/export-bundle`, filename),
  deleteTask: (id) => request(`/api/tasks/${id}`, { method: 'DELETE' }),
}
