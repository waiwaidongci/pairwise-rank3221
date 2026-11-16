"""Conditional bootstrap with two explicit resampling schemes.

Evidence can arrive in two forms, and they are never mixed up:

* legacy pair totals — anonymous aggregate counts whose reviewer sessions cannot
  be reconstructed. They keep the original treatment: a binomial draw per pair
  with the pair total fixed. They are never expanded into fake session rows.
* review sessions — one reviewer's group of pair choices. A session is one
  resampling unit; all of its choices are drawn together. Sampling whole
  sessions with replacement keeps repeated choices by the same reviewer from
  being counted as independent votes.

Each repeat yields two rank distributions over the same frozen evidence:
``session_grouped`` (primary; whole sessions) and ``per_pair`` (the original
naive scheme applied to combined per-pair totals). When no sessions exist both
schemes coincide, so historical legacy-only studies keep their old reading.
"""
from collections import Counter
import hashlib,json
import numpy as np
from scipy.special import expit
from src.services.comparison_graph import prepare_graph
from src.services.bt_solver import fit_bt,average_ranks

RANGE_SESSION='session_grouped'
RANGE_PAIR='per_pair'
METHOD_VERSION='session-grouped-cluster-bootstrap-v2'

def _collect_evidence(pairs,sessions):
    """Combine orientations into unordered pairs, keeping legacy and session parts apart."""
    combined={};legacy={};session_choices={}
    for p in pairs:
        a,b=p['left_id'],p['right_id'];key=(min(a,b),max(a,b))
        first_wins=p['left_wins'] if a==key[0] else p['right_wins']
        second_wins=p['right_wins'] if a==key[0] else p['left_wins']
        for bucket in (combined,legacy):
            rec=bucket.setdefault(key,{'left_id':key[0],'right_id':key[1],'left_wins':0,'right_wins':0})
            rec['left_wins']+=first_wins;rec['right_wins']+=second_wins
        combined[key]['source']=combined[key].get('source') or p.get('source','')
    for unit_index,unit in enumerate(sessions):
        for choice in unit.get('choices') or []:
            key=(min(choice['left_id'],choice['right_id']),max(choice['left_id'],choice['right_id']))
            low_won=(choice['winner']=='left')==(choice['left_id']==key[0])
            rec=combined.setdefault(key,{'left_id':key[0],'right_id':key[1],'left_wins':0,'right_wins':0,'source':'review session'})
            rec['left_wins' if low_won else 'right_wins']+=1
            session_choices.setdefault(key,[]).append((unit_index,low_won))
    for rec in combined.values():rec.setdefault('source','')
    return list(combined.values()),legacy,session_choices

def _align_edges(ordered,graph_edges,combined,legacy,session_choices):
    """Re-key evidence onto the canonical graph edge order used by ``prepare_graph``."""
    aligned=[]
    for e in graph_edges:
        first_id=ordered[e['i']]['id'];second_id=ordered[e['j']]['id']
        key=(min(first_id,second_id),max(first_id,second_id));first_is_low=first_id==key[0]
        comb=combined.get(key,{'left_wins':0,'right_wins':0})
        leg=legacy.get(key,{'left_wins':0,'right_wins':0})
        session=[(unit_index,low_won if first_is_low else not low_won) for unit_index,low_won in session_choices.get(key,[])]
        aligned.append({'i':e['i'],'j':e['j'],
            'pair_total':comb['left_wins']+comb['right_wins'],
            'pair_first':comb['left_wins'] if first_is_low else comb['right_wins'],
            'legacy_total':leg['left_wins']+leg['right_wins'],
            'legacy_first':leg['left_wins'] if first_is_low else leg['right_wins'],
            'session_choices':session})
    return aligned

def _payload(aligned,wins,totals):
    return [{'i':e['i'],'j':e['j'],'wins':int(w),'total':int(t)} for e,w,t in zip(aligned,wins,totals)]

def _rank_stats(rank_matrix,share_matrix):
    q=np.quantile(rank_matrix,[.025,.5,.975],axis=0)
    out=[]
    for i in range(rank_matrix.shape[1]):
        freq=Counter(str(float(x)) for x in rank_matrix[:,i])
        out.append({'low':float(q[0,i]),'median':float(q[1,i]),'high':float(q[2,i]),
            'first_share':float(share_matrix[:,i].mean()),
            'frequency':dict(sorted(freq.items(),key=lambda kv:float(kv[0])))})
    return out

def analyze_ranking(snapshot,ridge,repeats,seed,heartbeat=None):
    if not isinstance(repeats,int) or not 50<=repeats<=200:raise ValueError('bootstrap重复须为50–200')
    concepts=snapshot['concepts'];session_units=snapshot.get('sessions') or []
    combined,legacy,session_choices=_collect_evidence(snapshot.get('pairs') or [],session_units)
    if not combined:raise ValueError('比较图无票')
    ordered,edges,graph=prepare_graph(concepts,combined);n=len(ordered)
    combined_by_key={(r['left_id'],r['right_id']):r for r in combined}
    aligned=_align_edges(ordered,edges,combined_by_key,legacy,session_choices)
    totals=np.array([e['pair_total'] for e in aligned],dtype=int)
    observed=np.array([e['pair_first']/e['pair_total'] for e in aligned])
    legacy_totals=np.array([e['legacy_total'] for e in aligned],dtype=int)
    legacy_p=np.array([e['legacy_first']/e['legacy_total'] if e['legacy_total'] else 0. for e in aligned])
    unit_choices=[[] for _ in session_units]
    for edge_index,e in enumerate(aligned):
        for unit_index,first_won in e['session_choices']:unit_choices[unit_index].append((edge_index,first_won))
    theta,diagnostic=fit_bt(n,_payload(aligned,[e['pair_first'] for e in aligned],totals),ridge)
    point_rank,_=average_ranks(theta)
    rng=np.random.default_rng(seed)
    session_ranks=[];session_shares=[];pair_ranks=[];pair_shares=[];draws=[]
    zero_total_draws=0;max_zero_total=0
    for b in range(repeats):
        # Per-pair scheme: fixed combined pair total, empirical win proportion.
        pair_wins=rng.binomial(totals,observed)
        pair_values,pair_diag=fit_bt(n,_payload(aligned,pair_wins,totals),ridge)
        pr,ps=average_ranks(pair_values);pair_ranks.append(pr);pair_shares.append(ps)
        if session_units:
            # Session-grouped scheme: legacy counts per pair, sessions resampled whole.
            legacy_wins=np.where(legacy_totals>0,rng.binomial(legacy_totals,legacy_p),0)
            session_wins=np.zeros(len(aligned),dtype=int);session_totals=np.zeros(len(aligned),dtype=int)
            for unit_index in rng.integers(0,len(session_units),size=len(session_units)):
                for edge_index,first_won in unit_choices[int(unit_index)]:
                    session_totals[edge_index]+=1
                    if first_won:session_wins[edge_index]+=1
            s_wins=legacy_wins+session_wins;s_totals=legacy_totals+session_totals
            # A cluster draw can lose every observation of a session-only pair.
            # The fit still runs under the positive ridge, but that replicate has
            # no direct evidence for the pair, so the count is reported rather
            # than hidden.
            missing=int(np.sum(s_totals==0))
            if missing:
                zero_total_draws+=1;max_zero_total=max(max_zero_total,missing)
            session_values,session_diag=fit_bt(n,_payload(aligned,s_wins,s_totals),ridge)
            sr,ss=average_ranks(session_values);session_ranks.append(sr);session_shares.append(ss)
            grouped={'wins':s_wins.tolist(),'totals':s_totals.tolist(),'zero_total_edges':missing,'abilities':session_values.tolist(),'ranks':sr.tolist(),'first_share':ss.tolist(),'gradient_max':session_diag['gradient_max']}
        else:
            # No sessions: both schemes are the same method. Reuse the draw so
            # the two displayed ranges are identical rather than needlessly noisy.
            session_ranks.append(pr);session_shares.append(ps)
            grouped={'wins':pair_wins.tolist(),'totals':totals.tolist(),'zero_total_edges':0,'abilities':pair_values.tolist(),'ranks':pr.tolist(),'first_share':ps.tolist(),'gradient_max':pair_diag['gradient_max']}
        draws.append({'repeat':b+1,**grouped,
            'pair':{'wins':pair_wins.tolist(),'totals':totals.tolist(),'abilities':pair_values.tolist(),'ranks':pr.tolist(),'first_share':ps.tolist(),'gradient_max':pair_diag['gradient_max']}})
        if heartbeat:heartbeat()
    session_stats=_rank_stats(np.asarray(session_ranks),np.asarray(session_shares))
    pair_stats=_rank_stats(np.asarray(pair_ranks),np.asarray(pair_shares))
    rows=[]
    for i,c in enumerate(ordered):
        s=session_stats[i];p=pair_stats[i]
        rows.append({**c,'ability':float(theta[i]),'rank':float(point_rank[i]),'comparisons':graph['degree'][i],
            # Primary fields keep the historical names so old consumers (export,
            # proposal rationale) keep reading the recommended range.
            'rank_low':s['low'],'rank_median':s['median'],'rank_high':s['high'],'first_share':s['first_share'],'rank_frequency':s['frequency'],
            'range_session':s,'range_pair':p})
    matrix=[[None if i==j else float(expit(theta[i]-theta[j])) for j in range(n)] for i in range(n)]
    canonical={'version':METHOD_VERSION,'snapshot':snapshot,'ridge':ridge,'repeats':repeats,'seed':seed}
    fingerprint=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return {'version':METHOD_VERSION,'concepts':rows,'probabilities':matrix,'graph':graph,'diagnostic':diagnostic,
        'ridge':ridge,'repeats':repeats,'seed':seed,'draws':draws,
        'edge_totals':totals.tolist(),'edge_order':[{'i':e['i'],'j':e['j'],'wins':e['pair_first'],'total':e['pair_total']} for e in aligned],
        'fingerprint':fingerprint,'snapshot':snapshot,
        'rank_ranges':{
            RANGE_SESSION:{'label':'会话成组重采样','primary':True,'available':True,'sessions':len(session_units),'note':'整份会话连同其全部选择一起重采样；同一评议人的相关选择只计一个重采样单位。' if session_units else '无会话证据：沿用逐对固定总票重采样，与逐对口径一致。'},
            RANGE_PAIR:{'label':'逐对独立重采样','primary':False,'available':True,'note':'旧汇总口径：每对总票固定、按观测比例独立抽样；若有会话，会话内的选择被拆开当作独立票。它不反映同一评议人选择间的相关，因此不能据此声称范围更准确；两种口径并列展示。'}},
        'evidence_sources':snapshot.get('evidence_sources') or {
            'legacy':{'method':'independent_pair_binomial','pairs':len(snapshot.get('pairs') or []),'votes':sum(p['left_wins']+p['right_wins'] for p in snapshot.get('pairs') or [])},
            'sessions':{'method':'session_group_binomial','sessions':len(session_units),'choices':sum(len(u.get('choices') or []) for u in session_units)}},
        'draw_diagnostics':{'draws_with_zero_total_edges':zero_total_draws,'max_zero_total_edges':max_zero_total,
            'note':'会话成组重采样可能让某个仅由会话覆盖的作品对在某次重复中失去全部观察；该类重复仍以正ridge拟合，但该对没有直接证据。逐对口径保持每对总票固定，不会出现此情形。' if zero_total_draws else '所有重复均保留了每个作品对的至少一处证据。'},
        'method':METHOD_VERSION,'primary_range':RANGE_SESSION,
        'tie_rule':'average rank for abilities within 1e-8; first share split equally among tied first',
        'interval':'2.5%/97.5% empirical rank quantiles, linearly interpolated; not posterior or simultaneous confidence limits',
        'resampling':('legacy pair totals: independent Binomial(n_ij, observed wins_ij/n_ij) with pair total fixed; review sessions: whole sessions drawn with replacement as clusters, all choices of a drawn session applied together' if session_units else 'independent Binomial(n_ij, observed wins_ij/n_ij), fixed pair totals; no review sessions present')}
