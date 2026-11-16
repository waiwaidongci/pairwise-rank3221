"""Anonymous reviewer sessions: whole-group validation and replace-on-revise.

Legacy ``pair_counts`` rows remain the only evidence of the pre-session era and
keep the old per-pair treatment. A session is never split into its pairs, so one
reviewer choosing many pairs contributes one resampling unit, not several
independent votes.
"""
import hashlib,json
from sqlalchemy import select
from fastapi import HTTPException
from src.models import Concept,PairCount,ReviewSession,ReviewSessionRevision
from src.constants.enums import SessionStatus
from src.services.study_service import get_study,lock_study

def _digest(choices,expected,order_sensitive=False):
    # Valid groups are order-insensitive: resubmitting the same group in a
    # different order is the same group, so it must not create a spurious
    # revision. A contradictory group keeps submission order so two different
    # conflicting submissions never collide on the same digest.
    if order_sensitive:
        canonical={'choices':[[c['left_id'],c['right_id'],c['winner']] for c in choices],
            'expected_pairs':[[p['left_id'],p['right_id']] for p in expected]}
    else:
        canonical={'choices':sorted((min(c['left_id'],c['right_id']),max(c['left_id'],c['right_id']),c['winner']=='left' if c['left_id']<=c['right_id'] else c['winner']=='right') for c in choices),
            'expected_pairs':sorted((min(p['left_id'],p['right_id']),max(p['left_id'],p['right_id'])) for p in expected)}
    return hashlib.sha256(json.dumps(canonical,separators=(',',':')).encode()).hexdigest()

def _pair_key(a,b):return (min(a,b),max(a,b))

def _validate_expected(db,study_id,expected):
    if expected is None:return []
    if not isinstance(expected,list) or len(expected)>300:raise HTTPException(422,'期望作品对最多300项')
    ids={c.id for c in db.scalars(select(Concept).where(Concept.study_id==study_id))}
    out=[]
    for raw_pair in expected:
        p=raw_pair.model_dump() if hasattr(raw_pair,'model_dump') else raw_pair
        if not isinstance(p,dict):raise HTTPException(422,'期望作品对格式无效')
        a,b=p.get('left_id'),p.get('right_id')
        if isinstance(a,bool) or isinstance(b,bool) or not isinstance(a,int) or not isinstance(b,int):raise HTTPException(422,'期望作品对格式无效')
        if a==b or a not in ids or b not in ids:raise HTTPException(422,'期望作品对必须引用本研究的两项不同作品')
        out.append({'left_id':a,'right_id':b})
    if len({_pair_key(p['left_id'],p['right_id']) for p in out})!=len(out):raise HTTPException(422,'期望作品对重复')
    return out

def _validate_choices(db,study_id,raw):
    """Return (recorded choices, full submitted list, contradictory).

    ``recorded`` collapses an identical repeat (same side of the same pair);
    ``full`` keeps every submitted row in order so a contradictory group is
    preserved verbatim on the audit copy instead of being silently resolved.
    """
    if not isinstance(raw,list) or not 1<=len(raw)<=300:raise HTTPException(422,'每份会话须提交1–300个选择')
    ids={c.id for c in db.scalars(select(Concept).where(Concept.study_id==study_id))}
    seen={};out=[];full=[];contradictory=False
    for raw_item in raw:
        item=raw_item.model_dump() if hasattr(raw_item,'model_dump') else raw_item
        if not isinstance(item,dict):raise HTTPException(422,'选择须为含左右作品与胜方的对象')
        left,right,winner=item.get('left_id'),item.get('right_id'),item.get('winner')
        if isinstance(left,bool) or isinstance(right,bool) or not isinstance(left,int) or not isinstance(right,int):raise HTTPException(422,'作品标识须为整数')
        if winner not in ('left','right'):raise HTTPException(422,'胜方须为 left 或 right')
        if left==right:raise HTTPException(422,'同一匿名会话不能出现作品自比')
        if left not in ids or right not in ids:raise HTTPException(422,'选择引用了本研究之外的作品')
        key=_pair_key(left,right);full.append({'left_id':left,'right_id':right,'winner':winner})
        # Compare the winner as a *side of the unordered pair*, not as a raw
        # left/right label: (A,B,"left") and (B,A,"left") select different
        # sides and are a contradiction, while (A,B,"left") and (B,A,"right")
        # both select A.
        first_won=(winner=='left')==(left==key[0])
        if key in seen:
            if seen[key]!=first_won:contradictory=True
            continue
        seen[key]=first_won;out.append({'left_id':left,'right_id':right,'winner':winner})
    return out,full,contradictory

def _quarantine_reason(choices,expected,contradictory):
    if contradictory:return '同一作品对在同一会话出现矛盾选择，整组已隔离'
    if not expected:return ''
    declared=[_pair_key(p['left_id'],p['right_id']) for p in expected]
    submitted={_pair_key(c['left_id'],c['right_id']) for c in choices}
    missing=[p for p in declared if p not in submitted]
    if missing:return f'缺少{len(missing)}个期望作品对，整组已隔离'
    return ''

def list_sessions(db,study_id):
    get_study(db,study_id)
    return db.scalars(select(ReviewSession).where(ReviewSession.study_id==study_id).order_by(ReviewSession.session_key)).all()

def get_session(db,id):
    item=db.get(ReviewSession,id)
    if not item:raise HTTPException(404,'评议会话不存在')
    return item

def submit_session(db,data):
    """Create or whole-group replace one session. An unchanged resubmit is a no-op."""
    get_study(db,data.study_id)
    # Serialize evidence writes for this study so two revisions of the same
    # session key (or a session write racing run creation) cannot interleave.
    study=lock_study(db,data.study_id)
    expected=_validate_expected(db,study.id,data.expected_pairs)
    choices,full,contradictory=_validate_choices(db,study.id,data.choices)
    recorded=full if contradictory else choices
    digest=_digest(recorded,expected,order_sensitive=contradictory)
    reason=_quarantine_reason(choices,expected,contradictory)
    status=SessionStatus.QUARANTINED if reason else SessionStatus.VALID
    existing=db.scalar(select(ReviewSession).where(ReviewSession.study_id==study.id,ReviewSession.session_key==data.session_key).with_for_update())
    if existing and existing.content_digest==digest and existing.status==status and existing.quarantine_reason==reason:
        # The exact same group arrived twice: keep one accounting unit, no revision.
        db.commit()
        return existing,False
    if existing:
        db.add(ReviewSessionRevision(session_id=existing.id,revision=existing.revision,status=existing.status,quarantine_reason=existing.quarantine_reason,choices=existing.choices,expected_pairs=existing.expected_pairs,content_digest=existing.content_digest))
        existing.revision=existing.revision+1
        existing.choices=recorded;existing.expected_pairs=expected
        existing.status=status;existing.quarantine_reason=reason;existing.content_digest=digest
        item=existing
        created=False
    else:
        item=ReviewSession(study_id=study.id,session_key=data.session_key,revision=1,choices=recorded,expected_pairs=expected,status=status,quarantine_reason=reason,content_digest=digest)
        db.add(item);created=True
    study.evidence_version=(study.evidence_version or 0)+1
    db.commit()
    return item,created

def session_rows(db,study_id,status=None):
    query=select(ReviewSession).where(ReviewSession.study_id==study_id)
    if status:query=query.where(ReviewSession.status==status)
    rows=db.scalars(query.order_by(ReviewSession.session_key)).all()
    return rows

def pair_summary(db,study_id):
    """Per unordered pair: legacy tally, valid-session selection counts, totals."""
    concepts={c.id:c for c in db.scalars(select(Concept).where(Concept.study_id==study_id))}
    legacy={}
    for p in db.scalars(select(PairCount).where(PairCount.study_id==study_id)):
        key=_pair_key(p.left_id,p.right_id)
        if p.left_id==key[0]:first,second=p.left_wins,p.right_wins
        else:first,second=p.right_wins,p.left_wins
        legacy[key]={'first_wins':first,'second_wins':second,'source':p.source,'pair_id':p.id}
    session_counts={}
    for s in session_rows(db,study_id,SessionStatus.VALID):
        for c in s.choices:
            key=_pair_key(c['left_id'],c['right_id'])
            first_won=(c['winner']=='left')==(c['left_id']==key[0])
            slot=session_counts.setdefault(key,{'first_wins':0,'second_wins':0,'sessions':0})
            slot['first_wins' if first_won else 'second_wins']+=1
            slot['sessions']+=1
    summary=[]
    for key in sorted(set(legacy)|set(session_counts)):
        l=legacy.get(key,{'first_wins':0,'second_wins':0,'source':'','pair_id':None})
        s=session_counts.get(key,{'first_wins':0,'second_wins':0,'sessions':0})
        name=lambda id:concepts[id].code if id in concepts else str(id)
        summary.append({'left_id':key[0],'right_id':key[1],'left_code':name(key[0]),'right_code':name(key[1]),
            'legacy_left_wins':l['first_wins'],'legacy_right_wins':l['second_wins'],
            'session_left_wins':s['first_wins'],'session_right_wins':s['second_wins'],
            'session_count':s['sessions'],'source':l['source']})
    return summary
