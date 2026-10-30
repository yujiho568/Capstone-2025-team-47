import React, { useEffect, useState } from 'react';

function Connect() {
  // ── 상태들 ───────────────────────────────────────────────
  const [me, setMe] = useState(null);          // { id, email, ... }
  const [loadingMe, setLoadingMe] = useState(true);
  const [meError, setMeError] = useState(null);

  const [form, setForm] = useState({
    name: 'default',
    accessKeyId: '',
    secretAccessKey: '',
    sessionToken: '',
    expiresAt: '',
    region: 'ap-northeast-2',
  });
  // a;ldskfjla;
  const [showSecret, setShowSecret] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [msg, setMsg] = useState(null); // { type: 'success'|'error'|'info', text: string }

  // ── 상수들 ───────────────────────────────────────────────
  const API_BASE = '/api/v1';
  const regions = ['ap-northeast-2', 'ap-northeast-1', 'us-east-1', 'us-west-2', 'eu-west-1'];


  // 토큰 가져오는 헬퍼 (프로덕션에 맞춰 교체)
  const getToken = () => localStorage.getItem('access_token');

  // ── 현재 로그인 사용자 불러오기 (/me) ───────────────────
  useEffect(() => {
    const fetchMe = async () => {
      setLoadingMe(true);
      setMeError(null);
      try {
        const res = await fetch(`${API_BASE}/users/me`, {
          headers: {
            'Content-Type': 'application/json',
            ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
          },
          credentials: 'include',
        });
        if (res.status === 401) {
          throw new Error('로그인이 필요합니다.');
        }
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || `me 조회 실패 (${res.status})`);
        setMe(data); // 기대 형식: { id: number, email: string, ... }
      } catch (e) {
        setMeError(e.message);
      } finally {
        setLoadingMe(false);
      }
    };
    fetchMe();
  }, []);

  // ── 입력 핸들러 & 검증 ───────────────────────────────────
  const onChange = (e) => {
    const { name, value } = e.target;
    setMsg(null);
    setForm(prev => ({ ...prev, [name]: value }));
  };

  const validate = () => {
    if (!form.name.trim()) return 'IAM 사용자를 입력하세요.';
    if (!form.accessKeyId.trim()) return 'Access Key ID를 입력하세요.';
    if (!form.secretAccessKey.trim()) return 'Secret Access Key를 입력하세요.';
    if (form.accessKeyId.length < 8) return 'Access Key ID가 너무 짧습니다.';
    if (form.sessionToken && !form.expiresAt) return '임시 자격증명의 만료 시각을 입력하세요.';
    if (form.expiresAt && !form.sessionToken) return 'Session token을 입력하세요.';
    if (form.expiresAt && new Date(form.expiresAt) <= new Date()) return '자격증명이 만료되었습니다.';
    if (form.secretAccessKey.length < 8) return 'Secret Access Key가 너무 짧습니다.';
    return null;
  };

  // ── “연결” 버튼: 테스트 → 저장 → S3 적재 ───────────────
  const handleConnect = async (e) => {
    e.preventDefault();
    setMsg(null);
    const err = validate();
    if (err) return setMsg({ type: 'error', text: err });
    if (!me?.id) return setMsg({ type: 'error', text: '로그인 정보를 불러오지 못했습니다.' });

    setConnecting(true);
    try {
      // 1) 연결 테스트
      setMsg({ type: 'info', text: '자격증명 테스트 중...' });
      let res = await fetch(`${API_BASE}/credentials/${me.id}/check`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
        body: JSON.stringify({
          accessKeyId: form.accessKeyId,
          secretAccessKey: form.secretAccessKey,
          sessionToken: form.sessionToken || null,
          expiresAt: form.expiresAt ? new Date(form.expiresAt).toISOString() : null,
          region: form.region,
        }),
      });
      let data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `연결 테스트 실패 (${res.status})`);

      // 2) DB 저장
      setMsg({ type: 'info', text: `테스트 성공(account=${data.account}). 자격증명 저장 중...` });
      res = await fetch(`${API_BASE}/credentials/${me.id}/store`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
        body: JSON.stringify({
          name: form.name,
          region: form.region,
          access_key_id: form.accessKeyId,     // snake_case
          secret_access_key: form.secretAccessKey,
          session_token: form.sessionToken || null,
          expires_at: form.expiresAt ? new Date(form.expiresAt).toISOString() : null,
        }),
      });
      data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `자격증명 저장 실패 (${res.status})`);
      setMsg({ type: 'info', text: 'S3에서 JSON 가져와 DB에 저장 중...' });
      res = await fetch(`${API_BASE}/results/${me.id}/import-s3`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
        body: JSON.stringify({
          credential_name: form.name,
          max_files: 100,
          dry_run: false,
        }),
      });
      const sum = await res.json();
      if (!res.ok) throw new Error(sum?.detail || `S3 적재 실패 (${res.status})`);

      setMsg({
        type: sum.errors ? 'error' : 'success',
        text: `마지막 동기화: ${new Date(sum.synced_at).toLocaleString()} / ${sum.errors ? '일부 실패' : '완료'}! 스캔:${sum.scanned}, 신규 저장:${sum.imported}, 중복:${sum.skipped_existing}, 에러:${sum.errors}\n다음 페이지: ${sum.continuation_token ? '있음' : '없음'}`,
      });
    } catch (e) {
      setMsg({ type: 'error', text: e.message });
    } finally {
      setForm(prev => ({ ...prev, accessKeyId: "", secretAccessKey: "", sessionToken: "", expiresAt: "" }));
      setConnecting(false);
    }
  };

  // ── 렌더링 ───────────────────────────────────────────────
  if (loadingMe) {
    return <div style={{ padding: 24 }}>사용자 정보를 불러오는 중...</div>;
  }
  if (meError) {
    return (
      <div style={{ padding: 24 }}>
        <div style={{ marginBottom: 12, color: '#ef4444' }}>오류: {meError}</div>
        <div>로그인 후 다시 시도하세요.</div>
      </div>
    );
  }

  return (
    <div className="page" style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Connect IAM Credential</h1>
      <div style={{ color: '#6b7280', marginBottom: 16 }}>
        해당 IAM 계정에 UEBA 구축이 완료되어야 합니다.
      </div>

      <form onSubmit={handleConnect} className="card" style={{ border: '1px solid #e5e7eb', borderRadius: 12, padding: 16 }}>
        <div style={{ display: 'grid', gap: 12 }}>
          <div>
            <label htmlFor="name" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>IAM 사용자</label>
            <input id="name" name="name" value={form.name} onChange={onChange}
              placeholder="default / test-acct / prod-acct"
              style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db' }} />
          </div>

          <div>
            <label htmlFor="accessKeyId" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Access Key ID</label>
            <input id="accessKeyId" name="accessKeyId" value={form.accessKeyId} onChange={onChange}
              placeholder="AKIA..." autoComplete="off"
              style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db' }} />
          </div>

          <div>
            <label htmlFor="secretAccessKey" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Secret Access Key</label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input id="secretAccessKey" name="secretAccessKey"
                type={showSecret ? 'text' : 'password'}
                value={form.secretAccessKey} onChange={onChange}
                placeholder="********" autoComplete="off"
                style={{ flex: 1, padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db' }} />
              <button type="button" onClick={() => setShowSecret(s => !s)}
                style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db', background: 'white' }}>
                {showSecret ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="sessionToken">Session token (임시 자격증명만)</label>
            <input id="sessionToken" name="sessionToken" type="password" autoComplete="off"
              value={form.sessionToken} onChange={onChange} style={{ width: '100%' }} />
          </div>
          <div>
            <label htmlFor="expiresAt">만료 시각 (현재 브라우저 시간대)</label>
            <input id="expiresAt" name="expiresAt" type="datetime-local"
              value={form.expiresAt} onChange={onChange} />
          </div>

          <div>
            <label htmlFor="region" style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Region</label>
            <select id="region" name="region" value={form.region} onChange={onChange}
              style={{ width: '100%', padding: '10px 12px', borderRadius: 8, border: '1px solid #d1d5db' }}>
              {regions.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button type="submit" disabled={connecting}
            style={{ padding: '10px 14px', borderRadius: 8, border: '1px solid #000000', background: connecting ? '#93c5fd' : '#1e3a8a', color: 'white' }}>
            {connecting ? '연결 중...' : '연결'}
          </button>
        </div>

        {msg && (
          <div role="alert" style={{
            marginTop: 14, padding: '10px 12px', borderRadius: 8,
            border: `1px solid ${msg.type === 'error' ? '#ef4444' : (msg.type === 'info' ? '#60a5fa' : '#10b981')}`,
            background: msg.type === 'error' ? '#fee2e2' : (msg.type === 'info' ? '#dbeafe' : '#d1fae5'),
            whiteSpace: 'pre-wrap'
          }}>
            {msg.text}
          </div>
        )}
      </form>
    </div>
  );
}

export default Connect;
