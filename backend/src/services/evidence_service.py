"""Assemble a study's frozen evidence at one consistent version.

Two independent evidence sources coexist:

* legacy pair counts — anonymous per-pair totals of the pre-session era. They
  cannot be decomposed into reviewer sessions, so they keep the original
  independent-per-pair treatment and are never turned into fake session rows.
* valid review sessions — each contributes one resampling unit covering all of
  its pairs together.

The caller must hold the study row lock (``with_for_update``) while calling
``build_evidence`` so no evidence write can commit midway through the read.
"""
from sqlalchemy import select
from src.models import Concept,PairCount
from src.services.session_service import session_rows
from src.constants.enums import SessionStatus

LEGACY_METHOD='independent_pair_binomial'
SESSION_METHOD='session_group_binomial'

def _snapshot_concepts(db,study_id):
    return [{k:getattr(c,k) for k in ('id','code','title','medium')} for c in db.scalars(select(Concept).where(Concept.study_id==study_id).order_by(Concept.code))]

def build_evidence(db,study):
    """Return (snapshot_payload, evidence_version, session_units).

    ``session_units`` is the exact material the bootstrap will resample; it is
    stored in the snapshot so the run is reproducible without later session
    edits. Legacy counts are non-empty only when pair counts exist.
    """
    concepts=_snapshot_concepts(db,study.id)
    pairs=[{k:getattr(p,k) for k in ('id','left_id','right_id','left_wins','right_wins','source')} for p in db.scalars(select(PairCount).where(PairCount.study_id==study.id).order_by(PairCount.id))]
    units=[]
    for s in session_rows(db,study.id,SessionStatus.VALID):
        units.append({'session_id':s.id,'session_key':s.session_key,'revision':s.revision,
            'choices':[{'left_id':c['left_id'],'right_id':c['right_id'],'winner':c['winner']} for c in s.choices]})
    return {
        'concepts':concepts,
        'pairs':pairs,
        'sessions':units,
        'evidence_sources':{'legacy':{'method':LEGACY_METHOD,'pairs':len(pairs),'votes':sum(p['left_wins']+p['right_wins'] for p in pairs)},
            'sessions':{'method':SESSION_METHOD,'sessions':len(units),'choices':sum(len(u['choices']) for u in units)}},
    },int(study.evidence_version or 0),units
