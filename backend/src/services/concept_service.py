from sqlalchemy import select,func
from fastapi import HTTPException
from src.models import Concept
from src.services.study_service import get_study,lock_study

def list_concepts(db,study_id):return db.scalars(select(Concept).where(Concept.study_id==study_id).order_by(Concept.code)).all()
def create_concept(db,data):
    get_study(db,data.study_id)
    # The vertex set is part of frozen evidence; lock it so a run snapshot cannot
    # read concepts before this insert and pairs after it (or vice versa).
    study=lock_study(db,data.study_id)
    if db.scalar(select(Concept).where(Concept.study_id==data.study_id,Concept.code==data.code)):raise HTTPException(409,'该研究已有此作品编号')
    if db.scalar(select(func.count()).select_from(Concept).where(Concept.study_id==data.study_id))>=30:raise HTTPException(422,'每研究最多30项作品')
    study.evidence_version=(study.evidence_version or 0)+1
    item=Concept(**data.model_dump());db.add(item);db.commit();return item
