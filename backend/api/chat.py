"""backend/api/chat.py"""
from fastapi import APIRouter,HTTPException,Request;from fastapi.responses import StreamingResponse
from pydantic import BaseModel;from typing import Optional
from backend.api.utils import chat_utils as cu;from backend.api.middleware import auth_middleware as auth
from backend.api.chat_service import get_chat_service;from backend.core.models import ExecutionRole
router,SR=APIRouter(prefix="/api",tags=["chat"]),StreamingResponse

class ChatR(BaseModel):chatbot_id:str;message:str;session_id:Optional[str]=None;mode:Optional[str]=None;multi_sub_execution:Optional[bool]=None
class SessionR(BaseModel):chatbot_id:str;session_id:Optional[str]=None;mode:Optional[str]=None;active_level:int=1
class ToolR(BaseModel):message:str;context:Optional[dict]=None
class AgentR(BaseModel):message:str;session_id:str

def _d(r):return cu.get_chatbot_manager(r),cu.get_session_manager(r),cu.get_memory_manager(r),cu.get_ingestion_client(r)
def _cd(c):return{"id":c.id,"name":c.name,"description":c.description,"default_mode":c.role.value,"type":"parent"if c.sub_chatbots else"child"if c.parent_id else"standalone","sub_chatbots":[{"id":s.id}for s in c.sub_chatbots]if c.sub_chatbots else[],"parent_id":c.parent_id}
def _chk(ps,cid,m):
 if not(auth.check_chatbot_access(ps,cid)and auth.check_mode_permission(ps,cid,m)):raise HTTPException(403)

@router.get("/chatbots")
def l(r:Request):return[_cd(c)for c in cu.get_chatbot_manager(r).list_active()]

@router.post("/sessions")
def cs(b:SessionR,r:Request):
 u=auth.get_current_user(r);cbm,sm,_,_=_d(r);cb=cbm.get_active(b.chatbot_id)
 if not cb:raise HTTPException(404)
 return sm.create_session(b.chatbot_id,u["knox_id"],b.session_id,{b.chatbot_id:(b.mode or cb.role.value)}if(b.mode or cb.role.value)else None,b.active_level).to_dict()

@router.post("/chat")
async def c(b:ChatR,r:Request):
 u,cbm,sm,mm,ic=auth.get_current_user(r),*_d(r);sv=get_chat_service();cb=cbm.get_active(b.chatbot_id)
 if not cb:raise HTTPException(404)
 ss=sm.get_or_create(b.chatbot_id,u["knox_id"],b.session_id);md=cu.resolve_execution_mode(cb,ss,b.mode);_chk(auth.get_user_permissions(u),b.chatbot_id,md.value)
 if b.multi_sub_execution:cb.policy['multi_sub_execution']=b.multi_sub_execution
 async def g():
  async for e in sv.stream_chat_response(b.chatbot_id,b.message,ss.session_id,md,u,cu.create_executor(md,cb,ic,mm,cbm),cbm,sm,mm,b.multi_sub_execution):yield e
 return SR(g(),media_type="text/event-stream",headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@router.post("/tools/{cid}")
async def t(cid:str,b:ToolR,r:Request):
 u,cbm,_,_,ic=auth.get_current_user(r),*_d(r);sv=get_chat_service();cb=cbm.get_active(cid)
 if not cb:raise HTTPException(404)
 _chk(auth.get_user_permissions(u),cid,"tool")
 async def g():
  async for e in sv.stream_tool_response(cid,b.message,u,cu.create_executor(ExecutionRole.TOOL,cb,ic,None)):yield e
 return SR(g(),media_type="text/event-stream")

@router.post("/agents/{cid}")
async def a(cid:str,b:AgentR,r:Request):
 u,cbm,sm,mm,ic=auth.get_current_user(r),*_d(r);sv=get_chat_service();cb=cbm.get_active(cid)
 if not cb:raise HTTPException(404)
 _chk(auth.get_user_permissions(u),cid,"agent")
 ss=sm.get_or_create(cid,u["knox_id"],b.session_id)
 async def g():
  async for e in sv.stream_chat_response(cid,b.message,ss.session_id,ExecutionRole.AGENT,u,cu.create_executor(ExecutionRole.AGENT,cb,ic,mm,cbm),cbm,sm,mm):yield e
 return SR(g(),media_type="text/event-stream")

@router.get("/sessions/{sid}/history")
def h(sid:str,chatbot_id:str,r:Request):auth.get_current_user(r);return[m.to_dict()for m in cu.get_memory_manager(r).get_history(chatbot_id,sid)]

@router.delete("/sessions/{sid}")
def cl(sid:str,r:Request):auth.get_current_user(r);sm,mm=_d(r)[1],_d(r)[2];mm.clear_all_for_session(sid);sm.close_session(sid);return{"message":f"세션 {sid} 종료"}
