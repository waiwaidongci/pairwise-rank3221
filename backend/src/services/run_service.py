import json,os
from pathlib import Path
from sqlalchemy import select,func
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import RankingRun
from src.services.evidence_service import build_evidence
from src.services.study_service import lock_study
from src.services.rank_bootstrap import analyze_ranking
from src.constants.enums import RunStatus
redis=Redis.from_url(REDIS_URL)
def list_runs(db):return db.scalars(select(RankingRun).order_by(RankingRun.id.desc())).all()
def get_run(db,id):
    item=db.get(RankingRun,id)
    if not item:raise HTTPException(404,'拟合任务不存在')
    return item

def create_run(db,data):
    name_taken=db.scalar(select(RankingRun).where(RankingRun.name==data.name))
    if name_taken:raise HTTPException(409,'任务名称已存在')
    if db.scalar(select(func.count()).select_from(RankingRun).where(RankingRun.status.in_(['queued','running'])))>=3:raise HTTPException(429,'已有3项活动任务，请等待完成')
    # Hold the study row lock across the whole evidence read. Session writes and
    # legacy pair edits take the same lock, so the frozen snapshot always belongs
    # to exactly one evidence version even if a revision commits concurrently.
    study=lock_study(db,data.study_id)
    if not study:raise HTTPException(404,'评议研究不存在')
    evidence,version,units=build_evidence(db,study)
    snapshot={'study':{'id':study.id,'code':study.code,'name':study.name,'source_file':study.source_file,'evidence_version':version},
        **evidence}
    # An empty or disconnected evidence set is still frozen and queued; the
    # worker fails it with a traceable error rather than the API rejecting it.
    item=RankingRun(**data.model_dump(),snapshot=snapshot,status=RunStatus.QUEUED)
    db.add(item)
    # No version re-check is needed: the row lock is held until commit, so any
    # concurrent revision blocks and lands entirely before or after this read.
    db.commit()
    # Database is authoritative; worker scans queued tasks even if Redis notification fails.
    try:redis.lpush('pairwise:runs',str(item.id))
    except Exception:pass
    return item

def execute_run(db,id):
    item=get_run(db,id)
    if item.status not in ('queued','running'):return
    item.status=RunStatus.RUNNING;db.commit()
    try:
        result=analyze_ranking(item.snapshot,item.ridge,item.repeats,item.seed,lambda:Path('/tmp/heartbeat').touch())
        artifacts=Path(os.getenv('ARTIFACTS_DIR','/artifacts'))
        artifacts.mkdir(parents=True,exist_ok=True)
        (artifacts/f'run-{id}.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
        item.result=result;item.error='';item.status=RunStatus.COMPLETED;db.commit()
    except Exception as exc:
        db.rollback();item=get_run(db,id);item.status=RunStatus.FAILED;item.error=str(exc)[:600];db.commit()
