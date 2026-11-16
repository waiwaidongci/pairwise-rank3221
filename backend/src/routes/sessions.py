from fastapi import APIRouter,Depends,Response,status
from src.config.database import get_db
from src.utils.auth import current_user,editor
from src.schemas.session import SessionInput,SessionSubmitOut
from src.controllers import session_controller as controller
router=APIRouter(prefix='/sessions',tags=['sessions'])
@router.get('')
def index(study_id:int,db=Depends(get_db),user=Depends(current_user)):return controller.index(db,study_id)
@router.get('/summary')
def summary(study_id:int,db=Depends(get_db),user=Depends(current_user)):return controller.summary(db,study_id)
@router.put('',response_model=SessionSubmitOut)
def submit(data:SessionInput,response:Response,db=Depends(get_db),user=Depends(editor)):
    result=controller.submit(db,data)
    response.status_code=status.HTTP_201_CREATED if result['created'] else status.HTTP_200_OK
    return result
