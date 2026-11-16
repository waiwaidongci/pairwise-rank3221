from datetime import datetime
from sqlalchemy import String,ForeignKey,UniqueConstraint,DateTime,JSON,Double
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class ComparisonStudy(Base):
    __tablename__='comparison_studies'
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(40),unique=True)
    name:Mapped[str]=mapped_column(String(140))
    context:Mapped[str]=mapped_column(String(1000),default='')
    source_file:Mapped[str]=mapped_column(String(140),default='')
    # Incremented on every evidence write (legacy pair counts, concepts, sessions)
    # while the study row lock is held. Run creation read-modify-freezes evidence
    # under that same lock, so a snapshot always belongs to one committed version;
    # the frozen value is recorded in the run snapshot for traceability.
    evidence_version:Mapped[int]=mapped_column(default=0)
