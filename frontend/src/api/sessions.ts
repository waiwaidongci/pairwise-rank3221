import {request} from './client';import type {ReviewSession,SessionSummary} from '../types/domain';
export const list=(study_id:number)=>request<ReviewSession[]>('/sessions'+`?study_id=${study_id}`);
export const summary=(study_id:number)=>request<SessionSummary[]>('/sessions/summary'+`?study_id=${study_id}`);
export const submit=(data:unknown)=>request<ReviewSession & {created:boolean}>('/sessions',{method:'PUT',body:JSON.stringify(data)});
