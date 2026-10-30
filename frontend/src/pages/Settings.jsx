import React, { useEffect, useState } from 'react';

function Settings() {
  const API_BASE = '/api/v1';

  const [me, setMe] = useState(null);
  const [meLoading, setMeLoading] = useState(true);
  const [meErr, setMeErr] = useState(null);

  // [{ name, region, created_at, access_key_id_last4, has_secret, quarantine?: {applied, policy_name, reason_code, reason_message}}]
  const [creds, setCreds] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [msg, setMsg] = useState(null); // {type:'success'|'error'|'info', text}
  const [busyName, setBusyName] = useState(null); // 현재 작업 중인 credential 이름

  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};

  // 1) 로그인 사용자
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

  // 2) 자격증명 목록 + 각 항목의 Quarantine 상태 병합
  const loadCreds = async ({ clearMsg = true } = {}) => {
    if (!me?.id) return;
    setLoading(true);
    setErr(null);
    if (clearMsg) setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/credentials/${me.id}/list`, {
        headers: { 'Content-Type': 'application/json', ...authHeader },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `credentials 실패 (${res.status})`);

      // 각 자격증명에 대해 quarantine 조회
      const withQ = await Promise.all(
        (data || []).map(async (c) => {
          try {
            const qr = await fetch(`${API_BASE}/credentials/${me.id}/${encodeURIComponent(c.name)}/quarantine`, {
              headers: { 'Content-Type': 'application/json', ...authHeader },
            });
            const q = await qr.json();
            return {
              ...c,
              quarantine: q?.applied !== undefined
                ? q
                : { applied: null, policy_name: 'QuarantineDenyAll' },
            };
          } catch {
            return { ...c, quarantine: { applied: null, policy_name: 'QuarantineDenyAll', reason_message: '조회 실패' } };
          }
        })
      );

      setCreds(withQ);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (me?.id) loadCreds();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me?.id]);

  // 3) 삭제
  const handleDelete = async (name) => {
    if (!me?.id || !name) return;
    if (!window.confirm(`정말로 '${name}' 자격증명을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.`)) return;

    setMsg({ type: 'info', text: `'${name}' 삭제 중...` });
    setBusyName(name);
    try {
      const res = await fetch(`${API_BASE}/credentials/${me.id}/${encodeURIComponent(name)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', ...authHeader },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || `삭제 실패 (${res.status})`);
      }
      setMsg({ type: 'success', text: `'${name}' 삭제 완료` });
      await loadCreds({ clearMsg: false });
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setBusyName(null);
    }
  };

  // 4) 차단 적용/해제
  const applyQuarantine = async (name) => {
    if (!me?.id || !name) return;
    setMsg({ type: 'info', text: `'${name}' 차단 적용 중...` });
    setBusyName(name);
    try {
      const res = await fetch(`${API_BASE}/credentials/${me.id}/${encodeURIComponent(name)}/quarantine/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.reason_message || data?.detail || `차단 적용 실패 (${res.status})`);
      setMsg({ type: 'success', text: `'${name}' 차단 적용 완료` });
      await loadCreds({ clearMsg: false }); // ✅ 메시지 유지
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setBusyName(null);
    }
  };

  const removeQuarantine = async (name) => {
    if (!me?.id || !name) return;
    setMsg({ type: 'info', text: `'${name}' 차단 해제 중...` });
    setBusyName(name);
    try {
      const res = await fetch(`${API_BASE}/credentials/${me.id}/${encodeURIComponent(name)}/quarantine`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', ...authHeader },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.reason_message || data?.detail || `차단 해제 실패 (${res.status})`);
      setMsg({ type: 'success', text: `'${name}' 차단 해제 완료` });
      await loadCreds({ clearMsg: false }); // ✅ 메시지 유지
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setBusyName(null);
    }
  };

  const fmtDate = (iso) => {
    if (!iso) return '-';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const renderStatus = (q) => {
    const applied = q?.applied;
    if (applied === true) {
      return <span style={badgeStyle('#ef4444', '#fee2e2', '#991b1b')}>차단</span>;
    }
    if (applied === false) {
      return <span style={badgeStyle('#10b981', '#d1fae5', '#065f46')}>정상</span>;
    }
    return <span style={badgeStyle('#f59e0b', '#fef3c7', '#92400e')}>확인불가</span>;
  };

  const badgeStyle = (border, bg, color) => ({
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 999,
    border: `1px solid ${border}`,
    background: bg,
    color,
    fontSize: 12,
    fontWeight: 600,
  });

  if (meLoading) {
    return (
      <div style={{ padding: 20 }}>
        <h1>Settings</h1>
        <p>사용자 정보를 불러오는 중...</p>
      </div>
    );
  }
  if (meErr) {
    return (
      <div style={{ padding: 20 }}>
        <h1>Settings</h1>
        <p style={{ color: '#ef4444' }}>오류: {meErr}</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 20, maxWidth: 1000, margin: '0 auto' }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 25 }}>AWS Credentials</h1>
      </div>

      {err && (
        <div style={{ marginBottom: 12, padding: '8px 10px', borderRadius: 8, border: '1px solid #ef4444', background: '#fee2e2', color: '#991b1b' }}>
          {err}
        </div>
      )}
      {msg && (
        <div style={{
          marginBottom: 12, padding: '8px 10px', borderRadius: 8,
          border: `1px solid ${msg.type === 'error' ? '#ef4444' : msg.type === 'info' ? '#60a5fa' : '#10b981'}`,
          background: msg.type === 'error' ? '#fee2e2' : msg.type === 'info' ? '#dbeafe' : '#d1fae5',
          color: msg.type === 'error' ? '#991b1b' : msg.type === 'info' ? '#1e3a8a' : '#065f46'
        }}>
          {msg.text}
        </div>
      )}

      <div style={{ overflowX: 'auto', border: '1px solid #e5e7eb', borderRadius: 12 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
          <thead style={{ background: '#f9fafb' }}>
            <tr>
              <th style={th}>이름</th>
              <th style={th}>리전</th>
              <th style={th}>Access Key (마스킹)</th>
              <th style={th}>생성일</th>
              <th style={th}>상태</th>
              <th style={th}>작업</th>
            </tr>
          </thead>
          <tbody>
            {(!creds || creds.length === 0) ? (
              <tr>
                <td colSpan={7} style={{ padding: 16, textAlign: 'center', color: '#6b7280' }}>
                  등록된 자격증명이 없습니다.
                </td>
              </tr>
            ) : (
              creds.map((c) => {
                const applied = c?.quarantine?.applied;
                const reasonText = (c?.quarantine?.reason_code
                  ? `${c.quarantine.reason_code}: ${c.quarantine.reason_message || ''}`
                  : (c?.quarantine?.reason_message || '')).trim();

                return (
                  <tr key={c.name} style={{ borderTop: '1px solid #f3f4f6' }}>
                    <td style={td}><b>{c.name}</b></td>
                    <td style={td}>{c.region || '-'}</td>
                    <td style={{ ...td, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
                      {c.access_key_id_last4 ? `**** **** **** ${c.access_key_id_last4}` : '-'}
                    </td>
                    <td style={td}>{fmtDate(c.created_at)}</td>
                    <td style={td}>
                      {renderStatus(c.quarantine)}
                      {applied === null && reasonText && (
                        <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
                          {reasonText}
                        </div>
                      )}
                    </td>
                    <td style={{ ...td, whiteSpace: 'nowrap' }}>
                      {/* 상태에 따라 액션 버튼 분기 */}
                      {applied === true ? (
                        <button
                          onClick={() => removeQuarantine(c.name)}
                          disabled={busyName === c.name || loading}
                          style={{
                            padding: '6px 10px',
                            borderRadius: 8,
                            border: '1px solid #2563eb',
                            background: '#1e3a8a',
                            color: '#fff',
                            marginRight: 8,
                            opacity: (busyName === c.name || loading) ? 0.7 : 1
                          }}
                        >
                          {busyName === c.name ? '처리 중...' : '차단 해제'}
                        </button>
                      ) : (
                        <button
                          onClick={() => applyQuarantine(c.name)}
                          disabled={busyName === c.name || loading}
                          style={{
                            padding: '6px 10px',
                            borderRadius: 8,
                            border: '1px solid #dc2626',
                            background: '#ef4444',
                            color: '#fff',
                            marginRight: 8,
                            opacity: (busyName === c.name || loading) ? 0.7 : 1
                          }}
                        >
                          {busyName === c.name ? '처리 중...' : '차단 적용'}
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(c.name)}
                        disabled={busyName === c.name || loading}
                        style={{
                          padding: '6px 10px',
                          borderRadius: 8,
                          border: '1px solid #d00505ff',
                          background: '#fee2e2',
                          color: '#991b1b',
                          opacity: (busyName === c.name || loading) ? 0.7 : 1
                        }}
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const th = { textAlign: 'left', padding: 10, borderBottom: '1px solid #e5e7eb', whiteSpace: 'nowrap' };
const td = { padding: 10, verticalAlign: 'top' };

export default Settings;
