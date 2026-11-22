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
  // 认证
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

  // 课程与配置
  getConfig: (courseId) =>
    request(courseId ? `/api/config?course_id=${courseId}` : '/api/config'),
  saveConfig: (payload) =>
    request('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  listCourses: () => request('/api/courses'),
  createCourse: (payload) =>
    request('/api/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  deleteCourse: (id) => request(`/api/courses/${id}`, { method: 'DELETE' }),

  // 公共模板库（含批量 Excel 导入）
  listPublicTemplates: () => request('/api/templates/courses'),
  applyTemplate: (id) => request(`/api/templates/${id}/apply`, { method: 'POST' }),
  importCourseTemplateExcel: (file, isPublic = true) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('is_public', isPublic ? 'true' : 'false')
    return request('/api/templates/import-excel', { method: 'POST', body: fd })
  },
  importCourseTemplateBatch: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return request('/api/templates/import-excel-batch', { method: 'POST', body: fd })
  },
  previewCourseTemplateBatch: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return request('/api/templates/preview-excel-batch', { method: 'POST', body: fd })
  },
  previewSyllabusPdfBatch: (files) => {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    return request('/api/templates/preview-syllabus-pdf', { method: 'POST', body: fd })
  },
  publishCourseTemplateBatch: (courses) =>
    request('/api/templates/publish-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ courses }),
    }),
  downloadPaperTemplate: (courseId, courseName = '课程') =>
    downloadBlob(
      `/api/courses/${courseId}/paper-template`,
      `${courseName}_期末试卷结构模板.xlsx`
    ),
  importPaperExcel: (courseId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/api/courses/${courseId}/paper-import`, { method: 'POST', body: fd })
  },
  previewPaperExcel: (courseId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/api/courses/${courseId}/paper-preview`, { method: 'POST', body: fd })
  },
  savePaperJson: (courseId, paper) =>
    request(`/api/courses/${courseId}/paper-save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper }),
    }),

  // 名单与解析
  uploadRoster: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/roster/upload', { method: 'POST', body: fd })
  },
  parseFiles: (dailyFile, finalFile, courseId = null, dailyMap = null, finalMap = null) => {
    const fd = new FormData()
    fd.append('daily_file', dailyFile)
    fd.append('final_file', finalFile)
    if (courseId) fd.append('course_id', String(courseId))
    if (dailyMap) fd.append('daily_map', JSON.stringify(dailyMap))
    if (finalMap) fd.append('final_map', JSON.stringify(finalMap))
    return request('/api/parse', { method: 'POST', body: fd })
  },
  parseSample: (courseId = null) =>
    request(courseId ? `/api/parse-sample?course_id=${courseId}` : '/api/parse-sample', {
      method: 'POST',
    }),

  // 计算、终极 4-Sheet 导出与诊断
  calculateRecords: (payload) =>
    request('/api/calculate-records', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  exportRecords: (payload, filename = '达成度数据分析表.xlsx') =>
    downloadBlob('/api/export-records', filename, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  analyzeDiagnostics: (payload) =>
    request('/api/diagnostics/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  // 历史报告
  listReports: (courseId) =>
    request(courseId ? `/api/reports?course_id=${courseId}` : '/api/reports'),
  getReport: (id) => request(`/api/reports/${id}`),
  updateReportNotes: (id, analysisText, improvementNotes) =>
    request(`/api/reports/${id}/notes`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        analysis_text: analysisText,
        improvement_notes: improvementNotes,
      }),
    }),
  deleteReport: (id) => request(`/api/reports/${id}`, { method: 'DELETE' }),

  // 管理员端
  adminListUsers: () => request('/api/admin/users'),
  adminCreateUser: (payload) =>
    request('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  adminToggleUser: (id) =>
    request(`/api/admin/users/${id}/toggle`, { method: 'PATCH' }),
  adminResetPassword: (id, password = '123456') =>
    request(`/api/admin/users/${id}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    }),
  adminOverview: () => request('/api/admin/overview'),
}
