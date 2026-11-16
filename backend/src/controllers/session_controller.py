from src.services import session_service as service
def index(db,study_id):return service.list_sessions(db,study_id)
def summary(db,study_id):return service.pair_summary(db,study_id)
def submit(db,data):
    item,created=service.submit_session(db,data)
    return {**{k:getattr(item,k) for k in ('id','study_id','session_key','revision','status','quarantine_reason','choices','expected_pairs','content_digest','created_at','updated_at')},'created':created}
