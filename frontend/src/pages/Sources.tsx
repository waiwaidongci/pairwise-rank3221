import {useEffect,useState} from 'react';
import {studyStore,loadStudies} from '../stores/studies';
import {inputStore,loadInputs,addConcept,savePair} from '../stores/inputs';
import {sessionStore,loadSessions,submitSession} from '../stores/sessions';
import {authStore,canEdit} from '../stores/auth';
import {useTask} from '../hooks/useTask';
import PageHeading from '../components/common/PageHeading';
import ErrorNotice from '../components/common/ErrorNotice';
import StudySelect from '../components/StudySelect';
import type {Pair,SessionChoice} from '../types/domain';

type Draft=SessionChoice;
const blank=(left:number,right:number):Draft=>({left_id:left,right_id:right,winner:'left'});

export default function Sources(){
const {selected}=studyStore.use(),{concepts,pairs}=inputStore.use(),{sessions,summary}=sessionStore.use(),{user}=authStore.use();
const {error,busy,perform}=useTask();
const [edit,setEdit]=useState<Pair|null>(null),[success,setSuccess]=useState('');
const [sessionKey,setSessionKey]=useState(''),[draft,setDraft]=useState<Draft[]>([]),[expected,setExpected]=useState<string[]>([]),[editingSession,setEditingSession]=useState<number|null>(null),[formOpen,setFormOpen]=useState(false);
const pairKey=(a:number,b:number)=>`${Math.min(a,b)}-${Math.max(a,b)}`;
const resetSessionForm=()=>{setSessionKey('');setDraft([]);setExpected([]);setEditingSession(null);setFormOpen(false)};
const title=(id:number)=>{const c=concepts.find(c=>c.id===id);return c?c.code+' '+c.title:String(id)};
useEffect(()=>{perform(loadStudies)},[]);
useEffect(()=>{if(selected){setEdit(null);setSuccess('');resetSessionForm();perform(()=>Promise.all([loadInputs(selected),loadSessions(selected)]).then(()=>undefined))}},[selected]);

const valid=sessions.filter(s=>s.status==='valid'),quarantined=sessions.filter(s=>s.status!=='valid');
const loadForRevision=(id:number)=>{const s=sessions.find(x=>x.id===id);if(!s)return;setEditingSession(id);setFormOpen(true);setSessionKey(s.session_key);setDraft(s.choices.map(c=>({...c})));setExpected(s.expected_pairs.map(p=>pairKey(p.left_id,p.right_id)));setSuccess('')};

return <>
<PageHeading no="02" title="票数核对" sub="按匿名评议会话录入整组选择；同一评议人的多对选择只算一个独立单位。"/>
<StudySelect/>
<ErrorNotice error={error}/>{success&&<p role="status" className="success">{success}</p>}
<section className="input-spread">
<div>
<h2 className="ruled-title">匿名作品名录 <small>{concepts.length}项</small></h2>
<div className="concept-index">{concepts.map(c=><div key={c.id}><b>{c.code}</b><span>{c.title}<small>{c.medium}</small></span></div>)}</div>
{!concepts.length&&<p className="empty">请先登记至少两项作品，再录入比较票数。</p>}
{canEdit(user)&&<details className="edit-fold"><summary>＋ 登记作品方案</summary>
<form onSubmit={e=>{e.preventDefault();const f=e.currentTarget,d=new FormData(f);perform(async()=>{await addConcept({...Object.fromEntries(d),study_id:selected},selected);f.reset();setSuccess('作品已登记，可录入新的成对票数。')})}}>
<label>作品编号<input name="code" minLength={2} required/></label>
<label>匿名标题<input name="title" minLength={2} required/></label>
<label>媒介<input name="medium"/></label>
<button disabled={busy}>登记作品</button>
</form></details>}
<aside className="margin-note"><b>核对边界</b>
<p>自比、负票、非整数、空票边和重复无向边会被拒绝。零胜票可以存在，只要该对总票数为正。</p>
<p>连通性基于全部已登记作品；孤立作品会导致任务失败。修改票数后请重新排队，既有快照保留。</p>
<p>旧汇总票无法还原到会话，仍按逐对独立计票参与；它们不会被伪造成会话明细。</p></aside>
</div>
<div>
<h2 className="ruled-title">旧汇总票数台账 <small>{pairs.length}对</small></h2>
{canEdit(user)&&<details className="edit-fold" open={!!edit}>
<summary>{edit?'编辑比较 #'+edit.id:'＋ 录入一组成对票数（无会话来源）'}</summary>
<form key={edit?.id||'new'} className="form-grid" onSubmit={e=>{e.preventDefault();const d=new FormData(e.currentTarget);perform(async()=>{await savePair({study_id:selected,left_id:Number(d.get('left_id')),right_id:Number(d.get('right_id')),left_wins:Number(d.get('left_wins')),right_wins:Number(d.get('right_wins')),source:d.get('source')},selected,edit?.id);setEdit(null);setSuccess('票数已保存；已有研究快照不会被改写。')})}}>
<label>左侧作品<select name="left_id" defaultValue={edit?.left_id||concepts[0]?.id}>{concepts.map(c=><option key={c.id} value={c.id}>{c.code} {c.title}</option>)}</select></label>
<label>右侧作品<select name="right_id" defaultValue={edit?.right_id||concepts[1]?.id}>{concepts.map(c=><option key={c.id} value={c.id}>{c.code} {c.title}</option>)}</select></label>
<label>选择左侧的票数<input name="left_wins" type="number" min="0" max="1000" step="1" defaultValue={edit?.left_wins||0} required/></label>
<label>选择右侧的票数<input name="right_wins" type="number" min="0" max="1000" step="1" defaultValue={edit?.right_wins||0} required/></label>
<label className="full">票数来源<input name="source" defaultValue={edit?.source||''}/></label>
<div className="button-row"><button className="primary" disabled={busy}>保存票数</button>{edit&&<button type="button" onClick={()=>setEdit(null)}>取消编辑</button>}</div>
</form></details>}
<div className="table-scroll"><table><thead><tr><th>作品对</th><th>左票</th><th>右票</th><th>总票</th>{canEdit(user)&&<th/>}</tr></thead>
<tbody>{pairs.map(p=><tr key={p.id}><td><b>{title(p.left_id)}</b><small>对 {title(p.right_id)}</small></td><td>{p.left_wins}</td><td>{p.right_wins}</td><td>{p.left_wins+p.right_wins}</td>{canEdit(user)&&<td><button className="small-button" onClick={()=>setEdit(p)}>编辑</button></td>}</tr>)}</tbody>
</table></div>{!pairs.length&&<p className="empty">还没有旧汇总票。若有可还原到会话的选择，请使用下方“匿名评议会话”。</p>}
</div>
</section>

<section className="session-section">
<div className="session-form-panel">
<h2 className="ruled-title">匿名评议会话 <small>{valid.length}份有效 / {quarantined.length}份隔离</small></h2>
<p className="muted">一份会话提交一整组选择，可一次覆盖多对作品。重复提交同一会话不会重复入账；修订会整组替换，旧版本留存于修订历史。</p>
{canEdit(user)&&<details className="edit-fold" open={formOpen} onToggle={e=>setFormOpen(e.currentTarget.open)}>
<summary>{editingSession?`修订会话 ${sessionKey}（整组替换）`:'＋ 录入一份评议会话'}</summary>
<form onSubmit={e=>{e.preventDefault();const choiceRows=draft;if(!choiceRows.length){setSuccess('');return}perform(async()=>{
  const result=await submitSession({study_id:selected,session_key:sessionKey,choices:choiceRows,expected_pairs:expected.map(k=>{const[a,b]=k.split('-').map(Number);return {left_id:a,right_id:b}})});
  await loadSessions(selected);resetSessionForm();
  setSuccess(result.status==='valid'?`会话 ${result.session_key} 已入账（第${result.revision}版），旧版本已留档。`:`会话 ${result.session_key} 已隔离，未入账：${result.quarantine_reason}`);
})}}>
<label>会话标识（匿名）<input value={sessionKey} onChange={e=>setSessionKey(e.target.value)} placeholder="例如 S-2026-014" minLength={2} maxLength={80} pattern="[A-Za-z0-9_.:-]+" required/></label>
<div className="choice-list">
{!draft.length&&<p className="empty">尚未添加选择。一份会话至少包含一个作品对选择。</p>}
{draft.map((row,i)=><div className="choice-row" key={i}>
<select aria-label={`第${i+1}个选择的左侧作品`} value={row.left_id} onChange={e=>setDraft(draft.map((r,k)=>k===i?{...r,left_id:Number(e.target.value)}:r))}>{concepts.map(c=><option key={c.id} value={c.id}>{c.code} {c.title}</option>)}</select>
<span>对</span>
<select aria-label={`第${i+1}个选择的右侧作品`} value={row.right_id} onChange={e=>setDraft(draft.map((r,k)=>k===i?{...r,right_id:Number(e.target.value)}:r))}>{concepts.map(c=><option key={c.id} value={c.id}>{c.code} {c.title}</option>)}</select>
<select aria-label={`第${i+1}个选择的胜方`} value={row.winner} onChange={e=>setDraft(draft.map((r,k)=>k===i?{...r,winner:e.target.value as 'left'|'right'}:r))}><option value="left">左侧胜</option><option value="right">右侧胜</option></select>
<button type="button" className="small-button" onClick={()=>setDraft(draft.filter((_,k)=>k!==i))}>移除</button>
</div>)}
</div>
<div className="button-row"><button type="button" onClick={()=>setDraft([...draft,blank(concepts[0]?.id||0,concepts[1]?.id||0)])} disabled={!concepts.length}>＋ 再加一个选择</button></div>
<details className="edit-fold"><summary>期望作品对（可选；缺任一对则整组隔离）</summary>
<div className="expected-grid">{concepts.flatMap((a,i)=>concepts.slice(i+1).map(b=>{const k=pairKey(a.id,b.id);return <label key={k} className="check"><input type="checkbox" checked={expected.includes(k)} onChange={e=>setExpected(e.target.checked?[...expected,k]:expected.filter(x=>x!==k))}/>{a.code} × {b.code}</label>}))}</div>
</details>
<div className="button-row"><button className="primary" disabled={busy||!sessionKey||!draft.length}>{editingSession?'整组替换该会话':'提交整组会话'}</button>{editingSession&&<button type="button" onClick={resetSessionForm}>取消修订</button>}</div>
</form></details>}
<aside className="margin-note"><b>隔离规则</b><p>缺少期望作品对，或同一会话对同一作品对给出矛盾选择，整组隔离且不入账；不会只丢掉冲突的一行。</p><p>会话标识只是匿名编号，不含评审人身份；审计只记录操作者与路径。</p></aside>
</div>
<div className="session-ledger">
<h2 className="ruled-title">会话登记簿</h2>
{!sessions.length&&<p className="empty">还没有会话。旧汇总票继续按原方法参与，但无法补造会话明细。</p>}
{valid.length>0&&<><h3 className="subhead">有效会话 <small>{valid.length}</small></h3><div className="table-scroll"><table><thead><tr><th>会话</th><th>版本</th><th>选择数</th><th>状态</th><th/></tr></thead><tbody>{valid.map(s=><tr key={s.id}><td><b>{s.session_key}</b><small>{s.choices.length}个作品对</small></td><td>第{s.revision}版</td><td>{s.choices.length}</td><td><span className="status completed">有效</span></td><td>{canEdit(user)&&<button className="small-button" onClick={()=>loadForRevision(s.id)}>修订</button>}</td></tr>)}</tbody></table></div></>}
{quarantined.length>0&&<><h3 className="subhead">隔离会话 <small>{quarantined.length}</small></h3><div className="table-scroll"><table><thead><tr><th>会话</th><th>版本</th><th>隔离原因</th><th/></tr></thead><tbody>{quarantined.map(s=><tr key={s.id}><td><b>{s.session_key}</b></td><td>第{s.revision}版</td><td className="error-text">{s.quarantine_reason}</td><td>{canEdit(user)&&<button className="small-button" onClick={()=>loadForRevision(s.id)}>修订</button>}</td></tr>)}</tbody></table></div></>}
<h3 className="subhead">每对汇总 <small>{summary.length}对</small></h3>
<div className="table-scroll"><table><thead><tr><th>作品对</th><th>旧汇总票</th><th>会话选择</th><th>会话数</th><th>合计</th></tr></thead>
<tbody>{summary.map(r=><tr key={`${r.left_id}-${r.right_id}`}><td><b>{r.left_code} × {r.right_code}</b>{r.source&&<small>来源 {r.source}</small>}</td><td>{r.legacy_left_wins} / {r.legacy_right_wins}</td><td>{r.session_left_wins} / {r.session_right_wins}</td><td>{r.session_count}</td><td>{r.legacy_left_wins+r.legacy_right_wins+r.session_left_wins+r.session_right_wins}</td></tr>)}</tbody></table></div>
{!summary.length&&<p className="empty">尚无任何证据。登记旧汇总票或提交会话后才能排队研究。</p>}
<aside className="margin-note">旧汇总票列与会话选择列始终分开显示：前者无法拆分为会话，重采样时仍逐对独立；后者按会话成组。</aside>
</div>
</section>
</>}
