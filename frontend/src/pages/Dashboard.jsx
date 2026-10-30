import React, { useEffect, useState } from 'react';

const CHART_PADDING = { top: 28, right: 24, bottom: 28, left: 44 };

/** 간단한 라인차트(SVG) + 툴팁 + 임계선(50/70) */
function LineChart({ title, series, width = 720, height = 260 }) {
  // series: [{ ts: Date|string, risk: number, eventName?: string }], 과거→현재 정렬 권장
  const padding = CHART_PADDING;

  const { minY, maxY, points } = React.useMemo(() => {
    const ys = (series || []).map(d => Number(d.risk)).filter(Number.isFinite);
    const minY = ys.length ? Math.min(...ys, 0) : 0;
    const maxY = ys.length ? Math.max(...ys, 1) : 1;

    const n = Math.max((series || []).length, 1);
    const plotW = width - padding.left - padding.right;
    const plotH = height - padding.top - padding.bottom;

    const xScale = (i) =>
      padding.left + (i * plotW) / Math.max(n - 1, 1);
    const yScale = (y) =>
      padding.top + plotH - ((y - minY) * plotH) / ((maxY - minY) || 1);

    const points = (series || []).map((d, i) => ({
      i,
      x: xScale(i),
      y: yScale(Number(d.risk)),
      d,
    }));
    return { minY, maxY, xScale, yScale, points };
  }, [series, width, height, padding]);

  const fmtTs = (ts) => {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const level = (r) => (r >= 70 ? '위험' : r >= 50 ? '경고' : '정상');
  const color = (r) => (r >= 70 ? '#ef4444' : r >= 50 ? '#f59e0b' : '#3b82f6');

  // polyline path
  const poly = React.useMemo(() => {
    if (!points.length) return '';
    return points.map(p => `${p.x},${p.y}`).join(' ');
  }, [points]);

  // thresholds
  // hover: x에 가장 가까운 인덱스
  const [hover, setHover] = React.useState(null); // { idx, x, y, datum }
  const onMouseMove = (e) => {
    if (!points.length) return;
    const { left } = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - left;

    // x 기준 가장 가까운 포인트 탐색
    let best = null;
    let bestDx = Infinity;
    for (const p of points) {
      const dx = Math.abs(p.x - mx);
      if (dx < bestDx) { bestDx = dx; best = p; }
    }
    if (best) setHover({ idx: best.i, x: best.x, y: best.y, datum: best.d });
  };
  const onMouseLeave = () => setHover(null);

  // 툴팁 위치 계산
  const tooltip = hover && (() => {
    const pad = 8;
    const boxW = 280, boxH = 84;
    let tx = hover.x + 10;
    let ty = hover.y - boxH - 10;
    if (tx + boxW > width - padding.right) tx = hover.x - boxW - 10;
    if (ty < padding.top) ty = hover.y + 14;
    const r = Number(hover.datum.risk);
    return (
      <g>
        {/* 가이드 라인 & 포인트 강조 */}
        <line x1={hover.x} x2={hover.x} y1={padding.top} y2={height - padding.bottom} stroke="#9ca3af" strokeDasharray="4,4" />
        <circle cx={hover.x} cy={hover.y} r={5} fill={color(r)} stroke="#111827" strokeWidth="0.5" />
        {/* 툴팁 박스 */}
        <rect x={tx} y={ty} width={boxW} height={boxH} rx="8" ry="8" fill="#ffffff" stroke="#e5e7eb" />
        <text x={tx + pad} y={ty + 18} fontSize="12" fill="#111827">
          시간: {fmtTs(hover.datum.ts)}
        </text>
        <text x={tx + pad} y={ty + 36} fontSize="12" fill="#111827">
          eventName: {hover.datum.eventName || '-'}
        </text>
        <text x={tx + pad} y={ty + 54} fontSize="12" fill="#111827">
          risk: {r.toFixed(4)}
        </text>
        <text x={tx + pad} y={ty + 72} fontSize="12" fill={color(r)}>
          상태: {level(r)}
        </text>
      </g>
    );
  })();

  // threshold y좌표 (값이 없을 때 대비해서 직접 계산)
  const yAxis50 = (() => {
    if (!series?.length) return null;
    const ys = (series || []).map(d => Number(d.risk)).filter(Number.isFinite);
    const minY = ys.length ? Math.min(...ys, 0) : 0;
    const maxY = ys.length ? Math.max(...ys, 1) : 1;
    const plotH = height - padding.top - padding.bottom;
    const y = padding.top + plotH - ((50 - minY) * plotH) / ((maxY - minY) || 1);
    return y;
  })();

  const yAxis70 = (() => {
    if (!series?.length) return null;
    const ys = (series || []).map(d => Number(d.risk)).filter(Number.isFinite);
    const minY = ys.length ? Math.min(...ys, 0) : 0;
    const maxY = ys.length ? Math.max(...ys, 1) : 1;
    const plotH = height - padding.top - padding.bottom;
    const y = padding.top + plotH - ((70 - minY) * plotH) / ((maxY - minY) || 1);
    return y;
  })();

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>{title}</div>

      <svg
        width={width}
        height={height}
        style={{ background: '#fff' }}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        {/* 축 */}
        <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} stroke="#d1d5db" />
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} stroke="#d1d5db" />

        {/* y축 min/max 라벨 */}
        <text x={4} y={padding.top + 10} fontSize="10" fill="#6b7280">{`max ${maxY.toFixed(2)}`}</text>
        <text x={4} y={height - padding.bottom} fontSize="10" fill="#6b7280">{`min ${minY.toFixed(2)}`}</text>

        {/* 임계선 */}
        {yAxis50 !== null && yAxis50 >= padding.top && yAxis50 <= height - padding.bottom && (
          <>
            <line x1={padding.left} x2={width - padding.right} y1={yAxis50} y2={yAxis50} stroke="#f59e0b" strokeDasharray="6,5" />
            <text x={width - padding.right + 4} y={yAxis50 + 4} fontSize="10" fill="#f59e0b">50</text>
          </>
        )}
        {yAxis70 !== null && yAxis70 >= padding.top && yAxis70 <= height - padding.bottom && (
          <>
            <line x1={padding.left} x2={width - padding.right} y1={yAxis70} y2={yAxis70} stroke="#ef4444" strokeDasharray="6,5" />
            <text x={width - padding.right + 4} y={yAxis70 + 4} fontSize="10" fill="#ef4444">70</text>
          </>
        )}

        {/* 라인 */}
        {poly ? (
          <polyline fill="none" stroke="#3b82f6" strokeWidth="2" points={poly} />
        ) : (
          <text x={width / 2} y={height / 2} fill="#6b7280">No Data</text>
        )}

        {/* 툴팁 */}
        {tooltip}
      </svg>

      <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280' }}>
        * 선 위로 마우스를 움직이면 시간 / eventName / risk / 상태가 표시됩니다.
      </div>
    </div>
  );
}

/** Scatter Chart (이산적 이벤트 시각화) */
function ScatterChart({ title, series, width = 720, height = 260 }) {
  // series: [{ ts: Date|string, risk: number }, ...]  // 시간 오름차순(과거→현재) 권장
  const padding = CHART_PADDING;

  const { minX, maxX, xScale, yScale } = React.useMemo(() => {
    const ys = (series || []).map(d => Number(d.risk)).filter(Number.isFinite);
    const minY = ys.length ? Math.min(...ys, 0) : 0;
    const maxY = ys.length ? Math.max(...ys, 1) : 1;

    const times = (series || []).map(d => new Date(d.ts).getTime());
    const minX = times.length ? Math.min(...times) : Date.now();
    const maxX = times.length ? Math.max(...times) : minX + 1;

    const plotW = width - padding.left - padding.right;
    const plotH = height - padding.top - padding.bottom;

    const xScale = (t) =>
      padding.left + ((t - minX) * plotW) / (maxX - minX || 1);
    const yScale = (y) =>
      padding.top + plotH - ((y - minY) * plotH) / (maxY - minY || 1);

    return { minY, maxY, minX, maxX, xScale, yScale };
  }, [series, width, height, padding]);

  const fmtTs = (ts) => {
    const d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  };

  const level = (risk) => (risk >= 70 ? '위험' : risk >= 50 ? '경고' : '정상');
  const color = (risk) => (risk >= 70 ? '#ef4444' : risk >= 50 ? '#f59e0b' : '#3b82f6');

  const y50 = series?.length ? yScale(50) : null;
  const y70 = series?.length ? yScale(70) : null;

  // Hover 상태
  const [hover, setHover] = React.useState(null); // { idx, x, y, datum }
  const points = React.useMemo(() => {
    return (series || []).map((d, i) => {
      const t = new Date(d.ts).getTime();
      const x = xScale(t);
      const y = yScale(Number(d.risk));
      return { i, x, y, d };
    });
  }, [series, xScale, yScale]);

  const onMouseMove = (e) => {
    if (!points.length) return;
    const { left, top } = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - left;
    const my = e.clientY - top;

    // 가장 가까운 점 탐색 (100개 이하면 O(n)로 충분)
    let best = null, bestDist = Infinity;
    for (const p of points) {
      const dx = p.x - mx, dy = p.y - my;
      const dist = dx * dx + dy * dy;
      if (dist < bestDist) { bestDist = dist; best = p; }
    }
    setHover(best);
  };
  const onMouseLeave = () => setHover(null);

  // 툴팁 박스 위치 (SVG 내부)
  const tooltip = hover && (() => {
    const pad = 8;
    const boxW = 220, boxH = 64;
    let tx = hover.x + 10;
    let ty = hover.y - boxH - 10;
    if (tx + boxW > width - padding.right) tx = hover.x - boxW - 10;
    if (ty < padding.top) ty = hover.y + 14;
    const r = Number(hover.d.risk);
    return (
      <g>
        {/* 가이드 라인 & 포인트 강조 */}
        <line x1={hover.x} x2={hover.x} y1={padding.top} y2={height - padding.bottom} stroke="#9ca3af" strokeDasharray="4,4" />
        <circle cx={hover.x} cy={hover.y} r={5} fill={color(r)} stroke="#111827" strokeWidth="0.5" />
        {/* 박스 */}
        <rect x={tx} y={ty} width={boxW} height={boxH} rx="8" ry="8" fill="#ffffff" stroke="#e5e7eb" />
        <text x={tx + pad} y={ty + 18} fontSize="12" fill="#111827">
          시간: {fmtTs(hover.d.ts)}
        </text>
        <text x={tx + pad} y={ty + 36} fontSize="12" fill="#111827">
          risk: {Number(r).toFixed(4)}
        </text>
        <text x={tx + pad} y={ty + 54} fontSize="12" fill={color(r)}>
          상태: {level(r)}
        </text>
      </g>
    );
  })();

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 12 }}>
      <div style={{ fontWeight: 700, marginBottom: 8 }}>{title}</div>
      <svg
        width={width}
        height={height}
        style={{ background: '#fff' }}
        onMouseMove={onMouseMove}
        onMouseLeave={onMouseLeave}
      >
        {/* 축 */}
        <line x1={padding.left} y1={height - padding.bottom} x2={width - padding.right} y2={height - padding.bottom} stroke="#d1d5db" />
        <line x1={padding.left} y1={padding.top} x2={padding.left} y2={height - padding.bottom} stroke="#d1d5db" />

        {/* x축 시작/끝 라벨 */}
        <text x={padding.left} y={height - padding.bottom + 14} fontSize="10" fill="#6b7280" textAnchor="start">
          {minX ? fmtTs(minX) : ''}
        </text>
        <text x={width - padding.right} y={height - padding.bottom + 14} fontSize="10" fill="#6b7280" textAnchor="end">
          {maxX ? fmtTs(maxX) : ''}
        </text>

        {/* 임계선 */}
        {y50 !== null && y50 >= padding.top && y50 <= height - padding.bottom && (
          <>
            <line x1={padding.left} x2={width - padding.right} y1={y50} y2={y50} stroke="#f59e0b" strokeDasharray="6,5" />
            <text x={width - padding.right + 4} y={y50 + 4} fontSize="10" fill="#f59e0b">50</text>
          </>
        )}
        {y70 !== null && y70 >= padding.top && y70 <= height - padding.bottom && (
          <>
            <line x1={padding.left} x2={width - padding.right} y1={y70} y2={y70} stroke="#ef4444" strokeDasharray="6,5" />
            <text x={width - padding.right + 4} y={y70 + 4} fontSize="10" fill="#ef4444">70</text>
          </>
        )}

        {/* 점들 */}
        {(points || []).map((p) => (
          <circle key={p.i} cx={p.x} cy={p.y} r={4} fill={color(Number(p.d.risk))} />
        ))}

        {/* 툴팁 */}
        {tooltip}
      </svg>
    </div>
  );
}

function Dashboard() {
  const API_BASE = '/api/v1';
  const [me, setMe] = useState(null);
  const [meLoading, setMeLoading] = useState(true);
  const [meErr, setMeErr] = useState(null);

  const [creds, setCreds] = useState([]);        // [{name, region, ...}]
  const [credLoading, setCredLoading] = useState(false);
  const [credErr, setCredErr] = useState(null);
  const [selectedCred, setSelectedCred] = useState('');

  const [series0, setSeries0] = useState([]);    // initial_session=0 → [{ts, risk, eventName}]
  const [series1, setSeries1] = useState([]);    // initial_session=1 → [{ts, risk, eventName}]
  const [dataErr, setDataErr] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState(null);  // {type:'success'|'error'|'info', text}

  // 기본 S3 경로 (질문에서 지정)
  const [lastSync, setLastSync] = useState(null);
  const [nextPage, setNextPage] = useState(null);

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const authHeader = React.useMemo(() => token ? { Authorization: `Bearer ${token}` } : {}, [token]);

  // 1) 로그인 사용자
  useEffect(() => {
    const fetchMe = async () => {
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
    fetchMe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 2) 자격증명 목록
  useEffect(() => {
    if (!me?.id) return;
    const loadCreds = async () => {
      setCredLoading(true);
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
      } finally {
        setCredLoading(false);
      }
    };
    loadCreds();
    // eslint-di sable-next-line react-hooks/exhaustive-deps
  }, [me?.id, authHeader]);

  const fetchResults = async (credName) => {
    if (!me?.id || !credName) return;
    setDataErr(null);

    const toSeries = (arr) =>
      (arr || [])
        .slice() // 복사
        .reverse() // 과거→현재
        .map((it) => ({
          ts: it.timestamp,
          risk: Number(it.risk),
          eventName: it.event_name,
        }))
        .filter((d) => Number.isFinite(d.risk));

    try {
      // initial_session=0
      let res = await fetch(
        `${API_BASE}/ueba-results/${me.id}?credential_name=${encodeURIComponent(credName)}&initial_session=0&limit=100&order=desc`,
        { headers: { 'Content-Type': 'application/json', ...authHeader } }
      );
      let items0 = await res.json();
      if (!res.ok) throw new Error(items0?.detail || `results(0) 실패 (${res.status})`);

      // initial_session=1
      res = await fetch(
        `${API_BASE}/ueba-results/${me.id}?credential_name=${encodeURIComponent(credName)}&initial_session=1&limit=100&order=desc`,
        { headers: { 'Content-Type': 'application/json', ...authHeader } }
      );
      let items1 = await res.json();
      if (!res.ok) throw new Error(items1?.detail || `results(1) 실패 (${res.status})`);

      setSeries0(toSeries(items0));
      setSeries1(toSeries(items1));
    } catch (e) {
      setDataErr(e.message);
    }
  };

  // 선택 변경 시 DB에서 최신 100개 조회
  useEffect(() => {
    setNextPage(null);
    setLastSync(null);
    if (selectedCred) fetchResults(selectedCred);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCred]);

  // 3) 선택 자격증명으로 S3 → DB 동기화
  const handleSyncS3 = async () => {
    if (!me?.id || !selectedCred) return;
    setMessage({ type: 'info', text: 'S3에서 JSON을 가져와 DB 업데이트 중...' });
    setSyncing(true);
    try {
      const res = await fetch(`${API_BASE}/results/${me.id}/import-s3`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({
          credential_name: selectedCred,
          max_files: 100,
          continuation_token: nextPage,
          dry_run: false,
        }),
      });
      const sum = await res.json();
      if (!res.ok) throw new Error(sum?.detail || `S3 적재 실패 (${res.status})`);
      setLastSync(sum.synced_at);
      setNextPage(sum.continuation_token);
      setMessage({
        type: sum.errors ? 'error' : 'success',
        text: `동기화 ${sum.errors ? '일부 실패' : '완료'}: 스캔=${sum.scanned}, 추가=${sum.imported}, 중복=${sum.skipped_existing}, 에러=${sum.errors}`,
      });
      // 동기화 후 그래프 재조회
      fetchResults(selectedCred);
    } catch (e) {
      setMessage({ type: 'error', text: e.message });
    } finally {
      setSyncing(false);
    }
  };

  if (meLoading) return <div style={{ padding: 24 }}>사용자 정보를 불러오는 중...</div>;
  if (meErr) return <div style={{ padding: 24, color: '#ef4444' }}>오류: {meErr}</div>;

  return (
    <div className="page" style={{ maxWidth: 1080, margin: '0 auto', padding: 24 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Dashboard</h1>
        <span role="status">마지막 동기화: {lastSync ? new Date(lastSync).toLocaleString() : "아직 없음"} {nextPage ? "(다음 페이지 있음)" : ""}</span>
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <label style={{ fontWeight: 600 }}>자격 증명 :</label>
        <select
          value={selectedCred}
          onChange={(e) => setSelectedCred(e.target.value)}
          disabled={credLoading || (creds?.length || 0) === 0}
          style={{ padding: '8px 10px', borderRadius: 8, border: '1px solid #d1d5db' }}
        >
          {(creds || []).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name} {c.region ? `(${c.region})` : ''}
            </option>
          ))}
        </select>

        <button
          onClick={handleSyncS3}
          disabled={syncing || !selectedCred}
          style={{ padding: '1px 5px', borderRadius: 8, border: '1px solid #2563eb', background: syncing ? '#93c5fd' : '#1e3a8a', color: '#fff' }}
        >
          {syncing ? '동기화 중...' : 'S3 동기화'}
        </button>

        {credErr && <div style={{ color: '#ef4444' }}>자격 증명 오류: {credErr}</div>}
        {message && (
          <div
            style={{
              padding: '8px 10px',
              borderRadius: 8,
              border: `1px solid ${message.type === 'error' ? '#ef4444' : message.type === 'info' ? '#60a5fa' : '#10b981'
                }`,
              background: message.type === 'error' ? '#fee2e2' : message.type === 'info' ? '#dbeafe' : '#d1fae5',
            }}
          >
            {message.text}
          </div>
        )}
      </div>

      {dataErr && <div style={{ color: '#ef4444', marginBottom: 12 }}>데이터 오류: {dataErr}</div>}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16 }}>
        <LineChart title="전체 세션" series={series0} />
        <ScatterChart title="초기 세션" series={series1} />
      </div>

      <div style={{ marginTop: 8, color: '#6b7280', fontSize: 12 }}>
        * 임계선: 50(경고, 주황 점선), 70(위험, 빨강 점선)
      </div>
    </div>
  );
}

export default Dashboard;
