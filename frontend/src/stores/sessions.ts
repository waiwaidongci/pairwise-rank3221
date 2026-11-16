import {createStore} from '../utils/store';import * as api from '../api/sessions';import type {ReviewSession,SessionSummary} from '../types/domain';
export const sessionStore=createStore<{sessions:ReviewSession[];summary:SessionSummary[]}>({sessions:[],summary:[]});
export async function loadSessions(study:number){const [sessions,summary]=await Promise.all([api.list(study),api.summary(study)]);sessionStore.set({sessions,summary});}
export async function submitSession(data:unknown){const result=await api.submit(data);return result;}
