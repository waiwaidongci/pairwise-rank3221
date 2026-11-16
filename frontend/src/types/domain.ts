export interface User{id:number;name:string;email:string;role:'admin'|'analyst'|'viewer'}
export interface Study{id:number;code:string;name:string;context:string;source_file:string;evidence_version?:number}
export interface Concept{id:number;study_id?:number;code:string;title:string;medium:string}
export interface Pair{id:number;study_id:number;left_id:number;right_id:number;left_wins:number;right_wins:number;source:string}
export interface SessionChoice{left_id:number;right_id:number;winner:'left'|'right'}
export interface ReviewSession{id:number;study_id:number;session_key:string;revision:number;status:'valid'|'quarantined';quarantine_reason:string;choices:SessionChoice[];expected_pairs:{left_id:number;right_id:number}[];content_digest:string;created_at:string;updated_at:string;created?:boolean}
export interface SessionSummary{left_id:number;right_id:number;left_code:string;right_code:string;legacy_left_wins:number;legacy_right_wins:number;session_left_wins:number;session_right_wins:number;session_count:number;source:string}
export interface RankRange{low:number;median:number;high:number;first_share:number;frequency:Record<string,number>}
export interface RankRow extends Concept{ability:number;rank:number;rank_low:number;rank_median:number;rank_high:number;first_share:number;rank_frequency:Record<string,number>;comparisons:number;range_session?:RankRange;range_pair?:RankRange}
export interface Draw{repeat:number;wins:number[];totals:number[];abilities:number[];ranks:number[];first_share:number[];gradient_max:number;zero_total_edges?:number;pair:{wins:number[];totals:number[];abilities:number[];ranks:number[];first_share:number[];gradient_max:number}}
export interface RankRangeMeta{label:string;primary:boolean;available:boolean;sessions?:number;note:string}
export interface EvidenceSources{legacy?:{method:string;pairs:number;votes:number};sessions?:{method:string;sessions:number;choices:number}}
export interface Snapshot{study:Study;concepts:Concept[];pairs:Pair[];sessions?:{session_id:number;session_key:string;revision:number;choices:SessionChoice[]}[];evidence_sources?:EvidenceSources;evidence_version?:number}
export interface DrawDiagnostics{draws_with_zero_total_edges:number;max_zero_total_edges:number;note:string}
export interface Result{concepts:RankRow[];probabilities:(number|null)[][];graph:{vertices:number;edges:number;votes:number;connected:boolean;degree:number[]};diagnostic:{objective:number;gradient_max:number;iterations:number;optimizer_success:boolean;optimizer_message:string;centering_sum:number;acceptance:string};ridge:number;repeats:number;seed:number;draws:Draw[];edge_totals:number[];edge_order:{i:number;j:number;wins:number;total:number}[];fingerprint:string;snapshot:Snapshot;method?:string;primary_range?:string;rank_ranges?:Record<string,RankRangeMeta>;evidence_sources?:EvidenceSources;draw_diagnostics?:DrawDiagnostics}
export interface Run{id:number;name:string;study_id:number;ridge:number;repeats:number;seed:number;status:'queued'|'running'|'completed'|'failed';error:string;result:Result;created_at:string;snapshot:Snapshot}
export interface Proposal{id:number;name:string;run_id:number;left_id:number;right_id:number;extra_votes:number;rationale:string;status:'draft'|'approved'|'rejected';reviewer_note:string;reviewed_by:string;created_at:string}
