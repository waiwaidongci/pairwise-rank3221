"""Regression tests for session-grouped evidence (batch gb-0020).

Run from ``backend/`` with the app dependencies installed::

    pytest -q ../test-artifacts/gb-0020/

The tests exercise the service layer directly. They avoid Redis and the worker
loop; ``execute_run`` writes to ``ARTIFACTS_DIR`` which the fixture redirects.
"""
import os,sys,json
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/gb0020-test.db')
os.environ.setdefault('ARTIFACTS_DIR','/tmp/gb0020-artifacts')


_counter=[0]

@pytest.fixture()
def ctx(tmp_path,monkeypatch):
    # A fresh evidence set per test inside one throwaway SQLite database. Each
    # test gets its own study code so module-level engine caching is harmless.
    db_path=tmp_path/'db.sqlite'
    monkeypatch.setenv('DATABASE_URL',f'sqlite:///{db_path}')
    monkeypatch.setenv('ARTIFACTS_DIR',str(tmp_path/'artifacts'))
    from src.config.database import Base,engine,Session
    from src.models import ComparisonStudy,Concept,RankingRun,ReviewSession,ReviewSessionRevision
    import src.services.run_service as run_service
    run_service.redis=type('NoRedis',(),{'lpush':staticmethod(lambda *a,**k:None)})()
    Base.metadata.create_all(engine)
    _counter[0]+=1
    db=Session()
    study=ComparisonStudy(code=f'T{_counter[0]}',name='测试研究',context='',source_file='t.csv',evidence_version=0)
    db.add(study);db.flush()
    for i in range(4):
        db.add(Concept(study_id=study.id,code=f'C{i+1}',title=f'T{i+1}',medium=''))
    db.commit()
    ids=[c.id for c in db.query(Concept).filter_by(study_id=study.id).order_by(Concept.code)]
    yield type('Ctx',(),{'db':db,'study':study,'ids':ids,'run_service':run_service,
        'ReviewSession':ReviewSession,'ReviewSessionRevision':ReviewSessionRevision,'RankingRun':RankingRun})
    db.close()


def submit(ctx,key,rows,expected=None,study_id=None):
    from src.schemas.session import SessionInput
    from src.services import session_service
    choices=[{'left_id':ctx.ids[i],'right_id':ctx.ids[j],'winner':w} for i,j,w in rows]
    return session_service.submit_session(ctx.db,SessionInput(study_id=study_id or ctx.study.id,session_key=key,choices=choices,expected_pairs=expected or []))


def test_duplicate_session_is_counted_once(ctx):
    rows=[(0,1,'left'),(0,2,'left')]
    first,created=submit(ctx,'S-1',rows)
    again,created_again=submit(ctx,'S-1',rows)
    assert created is True and created_again is False
    assert first.id==again.id and again.revision==1
    assert ctx.db.query(ctx.ReviewSession).filter_by(study_id=ctx.study.id).count()==1
    assert ctx.db.query(ctx.ReviewSessionRevision).count()==0
    _,summary=__import__('src.services.session_service',fromlist=['pair_summary']).pair_summary(ctx.db,ctx.study.id),None
    # Reordering the same group is the same group, not a revision.
    submit(ctx,'S-1',list(reversed(rows)))
    assert ctx.db.query(ctx.ReviewSession).filter_by(study_id=ctx.study.id).one().revision==1


def test_revision_replaces_whole_group_and_keeps_history(ctx):
    submit(ctx,'S-1',[(0,1,'left'),(0,2,'left'),(1,2,'left')])
    revised,created=submit(ctx,'S-1',[(0,1,'right'),(2,3,'left')])
    assert created is False
    stored=ctx.db.query(ctx.ReviewSession).filter_by(study_id=ctx.study.id).one()
    assert stored.revision==2
    assert [(c['left_id'],c['right_id'],c['winner']) for c in stored.choices]==[(ctx.ids[0],ctx.ids[1],'right'),(ctx.ids[2],ctx.ids[3],'left')]
    history=ctx.db.query(ctx.ReviewSessionRevision).filter_by(session_id=stored.id).one()
    assert history.revision==1 and len(history.choices)==3


def test_missing_expected_pairs_quarantines_whole_group(ctx):
    expected=[{'left_id':ctx.ids[0],'right_id':ctx.ids[1]},{'left_id':ctx.ids[2],'right_id':ctx.ids[3]}]
    item,_=submit(ctx,'S-2',[(0,1,'left')],expected)
    assert item.status=='quarantined'
    assert '缺少' in item.quarantine_reason
    from src.services import session_service
    valid=session_service.session_rows(ctx.db,ctx.study.id,'valid')
    assert valid==[]


def test_contradictory_choices_quarantine_whole_group(ctx):
    item,_=submit(ctx,'S-3',[(0,1,'left'),(0,1,'right'),(2,3,'left')])
    assert item.status=='quarantined'
    assert '矛盾' in item.quarantine_reason
    # The full submitted group, including the conflicting row, is preserved.
    assert len(item.choices)==3


def test_reversed_orientation_is_not_a_contradiction(ctx):
    item,_=submit(ctx,'S-4',[(0,1,'left'),(1,0,'right')])
    assert item.status=='valid' and len(item.choices)==1


def test_self_comparison_is_rejected(ctx):
    with pytest.raises(HTTPException) as err:
        submit(ctx,'S-5',[(0,0,'left')])
    assert err.value.status_code==422


def test_foreign_concept_is_rejected(ctx):
    from src.schemas.session import SessionInput
    from src.services import session_service
    with pytest.raises(HTTPException) as err:
        session_service.submit_session(ctx.db,SessionInput(study_id=ctx.study.id,session_key='S-6',
            choices=[{'left_id':ctx.ids[0],'right_id':99999,'winner':'left'}],expected_pairs=[]))
    assert err.value.status_code==422


def test_quarantined_sessions_never_reach_a_snapshot(ctx):
    from src.schemas.pair import PairInput
    from src.schemas.run import RunInput
    from src.services import pair_service
    from src.services import session_service
    for i in range(3):
        pair_service.create_pair(ctx.db,PairInput(study_id=ctx.study.id,left_id=ctx.ids[i],right_id=ctx.ids[i+1],left_wins=6,right_wins=4))
    submit(ctx,'S-OK',[(0,1,'left'),(2,3,'left')])
    submit(ctx,'S-BAD',[(0,1,'left')],[{'left_id':ctx.ids[0],'right_id':ctx.ids[1]},{'left_id':ctx.ids[2],'right_id':ctx.ids[3]}])
    run=ctx.run_service.create_run(ctx.db,RunInput(name='R1',study_id=ctx.study.id,ridge=1.0,repeats=50,seed=1))
    assert [s['session_key'] for s in run.snapshot['sessions']]==['S-OK']
    assert run.snapshot['evidence_sources']['sessions']['sessions']==1
    assert run.snapshot['evidence_sources']['legacy']['pairs']==3
    ctx.run_service.execute_run(ctx.db,run.id)
    done=ctx.db.get(ctx.RankingRun,run.id)
    assert done.status=='completed',done.error
    assert set(done.result['rank_ranges'])=={'session_grouped','per_pair'}
    assert done.result['primary_range']=='session_grouped'


def test_session_revision_bumps_evidence_version(ctx):
    submit(ctx,'S-1',[(0,1,'left')])
    ctx.db.refresh(ctx.study)
    v1=ctx.study.evidence_version
    submit(ctx,'S-1',[(0,1,'right')])
    ctx.db.refresh(ctx.study)
    assert ctx.study.evidence_version==v1+1


def test_legacy_only_range_fields_match_old_layout(ctx):
    from src.schemas.pair import PairInput
    from src.schemas.run import RunInput
    from src.services import pair_service
    for i in range(3):
        pair_service.create_pair(ctx.db,PairInput(study_id=ctx.study.id,left_id=ctx.ids[i],right_id=ctx.ids[i+1],left_wins=7,right_wins=5))
    run=ctx.run_service.create_run(ctx.db,RunInput(name='Legacy',study_id=ctx.study.id,ridge=1.0,repeats=50,seed=2))
    ctx.run_service.execute_run(ctx.db,run.id)
    result=ctx.db.get(ctx.RankingRun,run.id).result
    assert result['evidence_sources']['sessions']['sessions']==0
    for c in result['concepts']:
        assert c['range_session']==c['range_pair']
        assert c['rank_low']==c['range_session']['low']


def test_export_keeps_legacy_layout_for_history_and_extended_for_new(ctx):
    from src.schemas.pair import PairInput
    from src.schemas.proposal import ProposalInput,ReviewInput
    from src.schemas.run import RunInput
    from src.services import pair_service,proposal_service
    for i in range(3):
        pair_service.create_pair(ctx.db,PairInput(study_id=ctx.study.id,left_id=ctx.ids[i],right_id=ctx.ids[i+1],left_wins=6,right_wins=4))
    submit(ctx,'S-1',[(0,1,'left')])
    run=ctx.run_service.create_run(ctx.db,RunInput(name='Export',study_id=ctx.study.id,ridge=1.0,repeats=50,seed=2))
    ctx.run_service.execute_run(ctx.db,run.id)
    done=ctx.db.get(ctx.RankingRun,run.id)
    user=type('U',(),{'email':'admin@x.local'})()
    ids=[c['id'] for c in done.result['concepts']]
    p=proposal_service.create_proposal(ctx.db,ProposalInput(name='P export',run_id=done.id,left_id=ids[0],right_id=ids[1],extra_votes=30,rationale='依据名次范围提出补票。'))
    proposal_service.review_proposal(ctx.db,p.id,ReviewInput(status='approved',reviewer_note='同意补充评议'),user)
    lines=proposal_service.export_proposal(ctx.db,p.id).lstrip('﻿').splitlines()
    assert lines[2].startswith('evidence_legacy_pairs')
    header_line=next(line for line in lines if line.startswith('code,title'))
    assert 'session_rank_q025' in header_line and 'rank_q025' in header_line
    # A historical result (no rank_ranges/evidence_sources) exports the old layout.
    result=dict(done.result)
    for key in ('rank_ranges','evidence_sources','primary_range','version','draw_diagnostics'):result.pop(key,None)
    result['concepts']=[{k:v for k,v in c.items() if k not in ('range_session','range_pair')} for c in result['concepts']]
    done.result=result;ctx.db.commit()
    legacy=proposal_service.export_proposal(ctx.db,p.id).lstrip('﻿').splitlines()
    assert legacy[2]=='code,title,ability_sum_zero,average_rank,rank_q025,rank_q975,first_place_share,rank_frequency'
