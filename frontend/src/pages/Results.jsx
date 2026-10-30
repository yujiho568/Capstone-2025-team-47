import React, { useEffect, useMemo, useState } from 'react';

function Results() {
  const API_BASE = '/api/v1';

  const [me, setMe] = useState(null);
  const [meLoading, setMeLoading] = useState(true);
  const [meErr, setMeErr] = useState(null);

  const [creds, setCreds] = useState([]); // [{name, region, ...}]
  const [credErr, setCredErr] = useState(null);
  const [selectedCred, setSelectedCred] = useState('');

  const [items, setItems] = useState([]);   // 전체 탐지 결과
  const [loadErr, setLoadErr] = useState(null);
  const [loading, setLoading] = useState(false);

  const [threshold, setThreshold] = useState('all'); // all | 50 | 70
  const [analysisFilter, setAnalysisFilter] = useState('all');
  const [initialFilter, setInitialFilter] = useState('all'); // all | 0 | 1
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};

  // 로그인 사용자
  useEffect(() => {
    const run = async () => {
      setMeLoading(true);
      setMeErr(null);
      try {
        const res = await fetch(`${API_BASE}/users/me`, {
          headers: { 'Content-Type': 'application/json', ...authHeader },
          credentials: 'include',
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || `me 실패 (${res.status})`);
        setMe(data);
      } catch (e) {
        setMeErr(e.message);
      } finally {
        setMeLoading(false);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 자격증명 목록
  useEffect(() => {
    if (!me?.id) return;
    const run = async () => {
      setCredErr(null);
      try {
        const res = await fetch(`${API_BASE}/credentials/${me.id}/list`, {
          headers: { 'Content-Type': 'application/json', ...authHeader },
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || `credentials 실패 (${res.status})`);
        setCreds(data || []);
        if (data?.length) setSelectedCred(data[0].name);
      } catch (e) {
        setCredErr(e.message);
      }
    };
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.id]);

  // 결과 로드
  const fetchResults = async (credName) => {
    if (!me?.id || !credName) return;
    setLoading(true);
    setLoadErr(null);
    setPage(1);
    try {
      const url = `${API_BASE}/ueba-results/${me.id}?credential_name=${encodeURIComponent(
        credName
      )}&limit=500&order=desc`;
      const res = await fetch(url, { headers: { 'Content-Type': 'application/json', ...authHeader } });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `results 실패 (${res.status})`);

      setItems(
        (data || []).map((r) => ({
          id: r.id,
          ts: r.timestamp,
          eventName: r.event_name,
          risk: Number(r.risk),
          init: r.initial_session ? 1 : 0,
          key: r.s3_key,
          cred: r.source_credential_name || '',
          userIdStr: r.user_id_str || '',
          analysisKind: r.analysis_kind || 'legacy',
          analysisVersion: r.analysis_version || '-',
          modelVersion: r.model_version || '-',
          supersedesKey: r.supersedes_key || '',
        }))
      );
    } catch (e) {
      setLoadErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedCred) fetchResults(selectedCred);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCred]);

  const level = (risk) => (risk >= 70 ? '위험' : risk >= 50 ? '경고' : '정상');
  const levelColor = (risk) => (risk >= 70 ? '#ef4444' : risk >= 50 ? '#f59e0b' : '#10b981');

  const fmtTs = (ts) => {
    if (!ts) return '-';
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(
      d.getMinutes()
    )}:${pad(d.getSeconds())}`;
  };

  // 필터링
  const filtered = useMemo(() => {
    let arr = items || [];
    if (analysisFilter !== 'all') arr = arr.filter(it => it.analysisKind === analysisFilter);
    if (threshold === '50') arr = arr.filter((it) => Number(it.risk) >= 50);
    if (threshold === '70') arr = arr.filter((it) => Number(it.risk) >= 70);
    if (initialFilter === '0') arr = arr.filter((it) => it.init === 0);
    if (initialFilter === '1') arr = arr.filter((it) => it.init === 1);
    return arr;
  }, [items, threshold, initialFilter, analysisFilter]);

  // 요약
  const counts = useMemo(() => {
    let total = filtered.length;
    let warn = 0;
    let danger = 0;
    for (const it of filtered) {
      if (it.risk >= 70) danger++;
      else if (it.risk >= 50) warn++;
    }
    return { total, warn, danger };
  }, [filtered]);

  // 페이지네이션
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageData = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page]);

  const goto = (p) => setPage(Math.min(totalPages, Math.max(1, p)));

  if (meLoading) return <div style={{ padding: 24 }}>사용자 정보를 불러오는 중...</div>;
  if (meErr) return <div style={{ padding: 24, color: '#ef4444' }}>오류: {meErr}</div>;

  return (
    <div className="page" style={{ maxWidth: 1200, margin: '0 auto', padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        {loading && <p role="status">결과를 불러오는 중...</p>}
      <h1 style={{ fontSize: 24, fontWeight: 700 }}>Results</h1>
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <label style={{ fontWeight: 600 }}>자격 증명</label>
        <select
          value={selectedCred}
          onChange={(e) => setSelectedCred(e.target.value)}
          disabled={(creds?.length || 0) === 0}
          style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #d1d5db' }}
        >
          {(creds || []).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name} {c.region ? `(${c.region})` : ''}
            </option>
          ))}
        </select>

        <label style={{ fontWeight: 600 }}>Risk Filter</label>
        <select
          value={threshold}
          onChange={(e) => {
            setThreshold(e.target.value);
            setPage(1);
          }}
          style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #d1d5db' }}
        >
          <option value="all">전체</option>
          <option value="50">경고 이상 (≥50)</option>
          <option value="70">위험 이상 (≥70)</option>
        </select>

        <label style={{ fontWeight: 600 }}>분석 이력</label>
        <select value={analysisFilter} onChange={e => { setAnalysisFilter(e.target.value); setPage(1); }}>
          <option value="all">전체 이력 (동일 이벤트의 수정 전·후 포함)</option>
          <option value="realtime">실시간 결과</option>
          <option value="reanalysis">과거 재분석</option>
          <option value="legacy">이전 형식</option>
        </select>
        <label style={{ fontWeight: 600 }}>세션 구분</label>
        <select
          value={initialFilter}
          onChange={(e) => {
            setInitialFilter(e.target.value);
            setPage(1);
          }}
          style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #d1d5db' }}
        >
          <option value="all">전체</option>
          <option value="0">전체 세션</option>
          <option value="1">초기 세션</option>
        </select>

        {/* <button
          onClick={() => fetchResults(selectedCred)}
          disabled={loading || !selectedCred}
          style={{ padding: '8px 12px', borderRadius: 8, border: '1px solid #d1d5db', background: loading ? '#e5e7eb' : 'white' }}
        >
          {loading ? '불러오는 중...' : '새로 불러오기'}
        </button> */}

        {credErr && <span style={{ color: '#ef4444' }}>자격증명 오류: {credErr}</span>}
        {loadErr && <span style={{ color: '#ef4444' }}>데이터 오류: {loadErr}</span>}
      </div>

      {/* 요약 배지 */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={{ padding: '6px 10px', borderRadius: 999, background: '#f3f4f6', color: '#111827' }}>
          총 {counts.total}개 결과 (이력 기준)
        </span>
        <span style={{ padding: '6px 10px', borderRadius: 999, background: '#fffbeb', color: '#92400e' }}>
          경고 {counts.warn}건 (≥50)
        </span>
        <span style={{ padding: '6px 10px', borderRadius: 999, background: '#fee2e2', color: '#991b1b' }}>
          위험 {counts.danger}건 (≥70)
        </span>
      </div>

      {/* 테이블 */}
      <div style={{ overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: 12 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              <th style={th}>시간</th>
              <th style={th}>eventName</th>
              <th style={th}>세션</th>
              <th style={th}>risk</th>
              <th style={th}>상태</th>
              <th style={th}>분석 이력</th>
              <th style={th}>S3 Key</th>
            </tr>
          </thead>
          <tbody>
            {pageData.length === 0 ? (
              <tr>
                <td colSpan={7} style={{ padding: 16, textAlign: 'center', color: '#6b7280' }}>
                  데이터가 없습니다.
                </td>
              </tr>
            ) : (
              pageData.map((it) => (
                <tr key={it.id} style={{ borderTop: '1px solid #f3f4f6' }}>
                  <td style={td}>{fmtTs(it.ts)}</td>
                  <td style={td}>{it.eventName || '-'}</td>
                  <td style={td}>{it.init === 0 ? 'total' : 'initial'}</td>
                  <td style={{ ...td, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                    {Number(it.risk).toFixed(4)}
                  </td>
                  <td style={{ ...td, fontWeight: 600, color: levelColor(it.risk) }}>{level(it.risk)}</td>
                  <td style={td} title={it.supersedesKey ? `이전 결과: ${it.supersedesKey}` : '이전 결과 없음'}>
                    {it.analysisKind === 'reanalysis' ? '과거 재분석' : it.analysisKind === 'realtime' ? '실시간' : '이전 형식'}
                    <br />모델: {it.modelVersion}<br />분석: {it.analysisVersion}
                  </td>
                  <td style={{ ...td, maxWidth: 380, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {it.key}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 페이지네이션 */}
      <div style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
        <button
          onClick={() => goto(page - 1)}
          disabled={page <= 1}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #d1d5db', background: page <= 1 ? '#f3f4f6' : 'white' }}
        >
          이전
        </button>
        <span style={{ color: '#6b7280' }}>
          {page} / {totalPages}
        </span>
        <button
          onClick={() => goto(page + 1)}
          disabled={page >= totalPages}
          style={{ padding: '6px 10px', borderRadius: 8, border: '1px solid #d1d5db', background: page >= totalPages ? '#f3f4f6' : 'white' }}
        >
          다음
        </button>
      </div>
    </div>
  );
}

const th = { textAlign: 'left', padding: 10, borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' };
const td = { padding: 10, verticalAlign: 'top' };

export default Results;
