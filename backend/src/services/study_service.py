from sqlalchemy import select
from fastapi import HTTPException
from src.models import ComparisonStudy

def lock_study(db,id):
    """Row-lock a study for a consistent evidence read or write.

    ``populate_existing`` refreshes the identity-map instance from the locked
    row. Without it a study object already loaded earlier in the request would
    keep a stale ``evidence_version``, and a concurrent commit could be lost.
    """
    return db.scalar(select(ComparisonStudy).where(ComparisonStudy.id==id).with_for_update().execution_options(populate_existing=True))

def list_studies(db):return db.scalars(select(ComparisonStudy).order_by(ComparisonStudy.id)).all()
def get_study(db,id):
    item=db.get(ComparisonStudy,id)
    if not item:raise HTTPException(404,'评议研究不存在')
    return item

def create_study(db,data):
    if db.scalar(select(ComparisonStudy).where(ComparisonStudy.code==data.code)):raise HTTPException(409,'研究编号已存在')
    item=ComparisonStudy(**data.model_dump(),evidence_version=0);db.add(item);db.commit();return item

def update_study(db,id,data):
    item=get_study(db,id)
    if db.scalar(select(ComparisonStudy).where(ComparisonStudy.code==data.code,ComparisonStudy.id!=id)):raise HTTPException(409,'研究编号已存在')
    # Metadata edits do not touch frozen evidence; the version is left untouched
    # so an in-flight snapshot of concepts/pairs stays valid.
    for k,v in data.model_dump().items():setattr(item,k,v)
    db.commit();return item
