from datetime import datetime
from sqlalchemy import String,ForeignKey,UniqueConstraint,Integer,DateTime,JSON
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base

class ReviewSession(Base):
    """One anonymous reviewer session, stored as a whole replaceable group.

    A session contributes at most one independent resampling unit. ``choices``
    keeps every submitted pair in recorded orientation; ``status='quarantined'``
    sessions never enter the tally or the bootstrap.
    """
    __tablename__='review_sessions'
    id:Mapped[int]=mapped_column(primary_key=True)
    study_id:Mapped[int]=mapped_column(ForeignKey('comparison_studies.id'))
    session_key:Mapped[str]=mapped_column(String(80))
    revision:Mapped[int]=mapped_column(default=1)
    status:Mapped[str]=mapped_column(String(20),default='valid')
    quarantine_reason:Mapped[str]=mapped_column(String(600),default='')
    # [{"left_id":int,"right_id":int,"winner":"left"|"right"}]
    choices:Mapped[list]=mapped_column(JSON,default=list)
    expected_pairs:Mapped[list]=mapped_column(JSON,default=list)
    content_digest:Mapped[str]=mapped_column(String(64),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow)
    __table_args__=(UniqueConstraint('study_id','session_key'),)

class ReviewSessionRevision(Base):
    """Append-only copy of every superseded session group."""
    __tablename__='review_session_revisions'
    id:Mapped[int]=mapped_column(primary_key=True)
    session_id:Mapped[int]=mapped_column(ForeignKey('review_sessions.id'))
    revision:Mapped[int]=mapped_column()
    status:Mapped[str]=mapped_column(String(20))
    quarantine_reason:Mapped[str]=mapped_column(String(600),default='')
    choices:Mapped[list]=mapped_column(JSON,default=list)
    expected_pairs:Mapped[list]=mapped_column(JSON,default=list)
    content_digest:Mapped[str]=mapped_column(String(64),default='')
    replaced_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint('session_id','revision'),)
