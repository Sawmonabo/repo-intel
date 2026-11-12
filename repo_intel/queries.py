from __future__ import annotations

import fnmatch
import json
import sqlite3
from . import derived
from .storage import Store

KINDS=('symbols','calls','callers','hierarchy','impact','imports','cycles','architecture','state',
       'coupling','history','cochange','duplicates','literals','patterns','dead','tests','runtime',
       'findings','files','runs','references','test_arcs','runtime_calls','literal_sites')


def choose_symbol(db,selector):
    if not selector:raise ValueError('A symbol ID or qualified name is required')
    rows=list(db.execute('SELECT * FROM symbols WHERE id=? OR qualified_name=? LIMIT 11',(selector,selector)))
    if not rows:rows=list(db.execute('SELECT * FROM symbols WHERE name=? LIMIT 11',(selector,)))
    if len(rows)!=1:
        raise ValueError(f'Symbol must resolve uniquely; found {len(rows)}. Candidates: '+
                         ', '.join(r['qualified_name']+' ['+r['id']+']' for r in rows[:10]))
    return rows[0]


def like(text):return '%'+text.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'


class QueryService:
    def __init__(self,store):self.store,self.settings=store,store.settings

    def run(self,kind,*,symbol=None,text='',limit=None,offset=0,depth=8,direction='incoming',run=None):
        if kind not in KINDS:raise ValueError(f'Unknown query kind {kind}; choose from {KINDS}')
        limit=self.settings.query_limit if limit is None else limit
        if type(limit) is not int or not 1<=limit<=self.settings.max_query_rows:raise ValueError('limit outside permitted range')
        if type(offset) is not int or not 0<=offset<=10000000:raise ValueError('Invalid offset')
        if type(depth) is not int or not 0<=depth<=100:raise ValueError('depth must be 0..100')
        if direction not in ('incoming','outgoing'):raise ValueError('direction must be incoming or outgoing')
        if len(text)>1024:raise ValueError('Search text too long')
        with self.store.read() as db:
            snapshot=Store.get(db,'snapshot');params=[];sql=None;items=[];cut=False;notes=[]
            if kind=='symbols':
                sql="SELECT id,qualified_name,name,kind,file,line,col,end_line,parent,params,decorators,is_test FROM symbols WHERE qualified_name LIKE ? ESCAPE '\\' ORDER BY qualified_name,file,line"
                params=[like(text)]
            elif kind in ('calls','callers'):
                s=choose_symbol(db,symbol) if symbol else None
                sql='''SELECT c.id,c.file,c.line,c.col,c.end_line,c.expression,c.arguments,
                    a.qualified_name AS caller,a.id AS caller_id,b.qualified_name AS target,b.id AS target_id,
                    CASE WHEN b.id IS NULL THEN 'unresolved' ELSE c.resolution END AS resolution
                    FROM calls c JOIN symbols a ON c.caller=a.id
                    LEFT JOIN call_targets t ON t.call=c.id LEFT JOIN symbols b ON b.id=t.target'''
                if s:
                    sql+=' WHERE '+('b.id=?' if kind=='callers' else 'a.id=?');params=[s['id']]
                elif text:
                    sql+=" WHERE c.expression LIKE ? ESCAPE '\\'";params=[like(text)]
                sql+=' ORDER BY c.file,c.line,c.col,b.id'
                notes=['Resolved means a static candidate, not proof of runtime dispatch. Unresolved calls remain visible.']
            elif kind=='references':
                sql="SELECT r.*,s.qualified_name AS owner_name FROM refs r JOIN symbols s ON s.id=r.owner WHERE r.name LIKE ? ESCAPE '\\'"
                params=[like(text)]
                if symbol:
                    target=choose_symbol(db,symbol)
                    sql+=' AND EXISTS(SELECT 1 FROM names n WHERE n.name=r.hint AND n.symbol=?)'
                    params.append(target['id'])
                sql+=' ORDER BY r.file,r.line,r.col'
                notes=['Syntactic references and known lexical target bindings; reflective/string-based usage is not resolved.']
            elif kind in ('hierarchy','impact'):
                s=choose_symbol(db,symbol)
                items,cut=derived.graph_walk(db,s,direction,depth,min(self.settings.max_graph_nodes,limit))
                if kind=='impact':
                    # File/state impact is separate from callable reachability: do not invent call edges.
                    shared=[dict(x) for x in db.execute('''SELECT DISTINCT a.resource,s.id,s.qualified_name,s.file,s.line
                        FROM accesses a JOIN accesses origin ON origin.resource=a.resource
                        JOIN symbols s ON s.id=a.owner WHERE origin.owner=? AND a.owner!=? LIMIT ?''',(s['id'],s['id'],limit+1))]
                    notes.append({'shared_state_dependents':shared[:limit],'truncated':len(shared)>limit})
                notes+=['Traversal is bounded and uses known static edges. Missing edges can hide impact. Import/config/runtime effects are not exhaustive.']
            elif kind=='imports':
                sql="SELECT i.*,f.module AS source_module FROM imports i JOIN files f ON f.path=i.file WHERE i.file LIKE ? ESCAPE '\\' ORDER BY i.file,i.line";params=[like(text)]
            elif kind=='cycles':
                groups,cut=derived.import_cycles(db,self.settings.max_graph_nodes,limit)
                for group in groups:
                    modules=[db.execute('SELECT module FROM files WHERE path=?',(x,)).fetchone()[0] for x in group]
                    items.append({'modules':sorted(set(modules)),'files':sorted(group),'kind':'strongly_connected_component'})
                notes=['Type-checking-only imports are excluded; conditional runtime imports remain possible edges.']
            elif kind=='architecture':
                items,cut=derived.architecture(db,self.settings,limit)
                notes=['No layering policy is inferred. Configure layers/boundaries in repo-intel.toml.' if not(self.settings.layers or self.settings.boundaries) else 'Configured policy evaluated against import facts.']
            elif kind=='state':
                sql="SELECT a.*,s.qualified_name AS owner_name FROM accesses a JOIN symbols s ON s.id=a.owner WHERE a.resource LIKE ? ESCAPE '\\' ORDER BY a.resource,a.file,a.line,a.mode";params=[like(text)]
                if symbol:
                    s=choose_symbol(db,symbol);sql=sql.replace(' ORDER BY',' AND a.owner=? ORDER BY');params.append(s['id'])
                notes=['Attribute/container method effects are candidates; arbitrary aliasing, cache servers and computed file identities are not fully modeled.']
            elif kind=='coupling':
                sql='''SELECT resource,count(DISTINCT owner) AS owners,count(*) AS access_sites FROM accesses
                       GROUP BY resource HAVING owners>1 ORDER BY owners DESC,resource'''
                notes=['Shared lexical resource or possible attribute identity, not proof of object-instance identity.']
            elif kind=='history':
                sql="SELECT path,count(*) AS commits,max(c.timestamp) AS last_changed FROM commit_files f JOIN commits c ON c.hash=f.commit_hash WHERE path LIKE ? ESCAPE '\\' GROUP BY path ORDER BY commits DESC,path";params=[like(text)]
                notes=[Store.get(db,'history_scope',{'status':'not_collected'})]
            elif kind=='cochange':
                if not text:raise ValueError('cochange requires text=repository-relative file path')
                sql='''SELECT other.path,count(*) AS together,
                    (SELECT count(*) FROM commit_files WHERE path=?) AS base_commits,
                    (SELECT count(*) FROM commit_files WHERE path=other.path) AS other_commits
                    FROM commit_files base JOIN commit_files other ON base.commit_hash=other.commit_hash
                    WHERE base.path=? AND other.path!=? GROUP BY other.path ORDER BY together DESC,other.path'''
                params=[text,text,text];notes=[Store.get(db,'history_scope',{'status':'not_collected'}),'Correlation is not causation; renames are not unified.']
            elif kind=='duplicates':
                s=choose_symbol(db,symbol) if symbol else None
                items,cut=derived.clones(db,s,limit,self.settings.clone_min_nodes)
                notes=['Whole-function AST signatures; near-miss retrieval requires a symbol. Imported jscpd block clones are in findings(kind=duplication). Neither proves interchangeable behavior.']
            elif kind=='literals':
                sql='''SELECT hash,kind,count(*) AS occurrences,count(DISTINCT file) AS files,min(length) AS length
                    FROM literals GROUP BY hash,kind HAVING files>1 ORDER BY occurrences DESC'''
                notes=['Literal contents are not stored; hashes intentionally avoid retaining possible secrets.']
            elif kind=='literal_sites':
                if not text:raise ValueError('literal_sites requires text=literal hash from literals query')
                sql='SELECT file,owner,line,kind,hash,length FROM literals WHERE hash=? ORDER BY file,line';params=[text]
                notes=['Values are hashed; inspect hash-validated source to determine whether repetition is intentional.']
            elif kind=='patterns':
                sql="SELECT p.*,s.qualified_name AS owner_name FROM patterns p LEFT JOIN symbols s ON s.id=p.owner WHERE p.rule LIKE ? ESCAPE '\\' ORDER BY p.file,p.line,p.col";params=[like(text)]
                notes=['Syntax-backed maintainability candidates, not automatic fixes or confirmed bugs.']
            elif kind=='dead':
                sql='''SELECT s.id,s.qualified_name,s.name,s.file,s.line,s.end_line,s.decorators,
                    'no_known_usage_candidate' AS classification FROM symbols s
                    WHERE s.kind='function' AND s.is_test=0 AND s.decorators='[]'
                    AND NOT EXISTS(SELECT 1 FROM call_targets t WHERE t.target=s.id)
                    AND NOT EXISTS(SELECT 1 FROM refs r JOIN names n ON n.name=r.hint WHERE n.symbol=s.id AND r.mode='read')
                    AND (SELECT COALESCE(sum(m.count),0) FROM mentions m WHERE m.term=s.name)<=1
                    ORDER BY s.file,s.line'''
                notes=['Not proof of dead code. Dynamic registration, consumers outside the repository, string construction and unindexed files can hide usage.']
            elif kind=='tests':
                s=choose_symbol(db,symbol) if symbol else None
                sql='''SELECT t.run,t.test,t.file,t.line,r.status AS run_status,r.producer FROM test_lines t
                    JOIN runs r ON r.id=t.run WHERE r.snapshot=?''';params=[snapshot]
                if s:sql+=' AND t.file=? AND t.line BETWEEN ? AND ?';params.extend([s['file'],s['line'],s['end_line']])
                if run:sql+=' AND t.run=?';params.append(run)
                sql+=' ORDER BY t.test,t.file,t.line'
                notes=['Observed test-context line execution is not assertion adequacy or proof. Definition/decorator lines can execute without calling the function. See runtime for actual invocations.']
            elif kind=='test_arcs':
                s=choose_symbol(db,symbol) if symbol else None
                sql='SELECT t.*,r.status AS run_status,r.producer FROM test_arcs t JOIN runs r ON r.id=t.run WHERE r.snapshot=?';params=[snapshot]
                if s:
                    sql+=' AND t.file=? AND ((t.source BETWEEN ? AND ?) OR (t.target BETWEEN ? AND ?))'
                    params.extend([s['file'],s['line'],s['end_line'],s['line'],s['end_line']])
                if run:sql+=' AND t.run=?';params.append(run)
                sql+=' ORDER BY t.test,t.file,t.source,t.target'
                notes=['Observed line transitions, not CFG proof. Negative endpoints follow coverage.py function-entry/exit conventions.']
            elif kind=='runtime_calls':
                sql="SELECT e.run,e.file,e.line,e.qualname,e.caller_file,e.caller_line,e.test,count(*) AS observed_calls,r.status AS run_status FROM runtime_events e JOIN runs r ON r.id=e.run WHERE r.snapshot=? AND e.event='call'"
                params=[snapshot]
                if run:sql+=' AND e.run=?';params.append(run)
                if text:sql+=" AND e.qualname LIKE ? ESCAPE '\\'";params.append(like(text))
                sql+=' GROUP BY e.run,e.file,e.line,e.qualname,e.caller_file,e.caller_line,e.test ORDER BY observed_calls DESC'
                notes=['Observed Python call-site evidence, separate from static candidate edges. Generator resumes can produce additional call events.']
            elif kind=='runtime':
                sql='''SELECT e.*,r.status AS run_status FROM runtime_events e JOIN runs r ON r.id=e.run
                    WHERE r.snapshot=?''';params=[snapshot]
                if run:sql+=' AND e.run=?';params.append(run)
                if text:sql+=" AND e.qualname LIKE ? ESCAPE '\\'";params.append(like(text))
                sql+=' ORDER BY e.run,e.seq';notes=['Sequence is collector observation order, not a cross-thread causal order. Python profile return events may represent generator suspension.']
            elif kind=='findings':
                sql='SELECT f.* FROM findings f WHERE EXISTS(SELECT 1 FROM evidence e JOIN runs r ON r.id=e.run WHERE e.finding=f.id AND r.snapshot=?'
                params=[snapshot]
                if run:sql+=' AND r.id=?';params.append(run)
                sql+=')'
                if text:sql+=" AND (f.kind LIKE ? ESCAPE '\\' OR f.rule LIKE ? ESCAPE '\\')";params.extend([like(text),like(text)])
                sql+=' ORDER BY f.file,f.line,f.id'
            elif kind=='files':
                sql="SELECT path,module,hash,size,status,error,language,lines FROM files WHERE path LIKE ? ESCAPE '\\' ORDER BY path";params=[like(text)]
            elif kind=='runs':
                sql='SELECT *,CASE WHEN snapshot=? THEN 1 ELSE 0 END AS current_snapshot FROM runs ORDER BY created DESC';params=[snapshot]
            if sql:
                rows=list(db.execute(sql+' LIMIT ? OFFSET ?',(*params,limit+1,offset)))
                cut=len(rows)>limit;items=[dict(r) for r in rows[:limit]]
            if kind=='findings':
                for item in items:
                    obs_sql='SELECT e.detail AS evidence,r.id AS run,r.producer,r.version,r.status FROM evidence e JOIN runs r ON r.id=e.run WHERE e.finding=? AND r.snapshot=?'
                    obs_params=[item['id'],snapshot]
                    if run:obs_sql+=' AND r.id=?';obs_params.append(run)
                    observations=[dict(x) for x in db.execute(obs_sql+' ORDER BY r.created DESC,r.id LIMIT 101',obs_params)]
                    item['observations']=observations[:100]
                    item['observations_truncated']=len(observations)>100
                    # Convenient representative fields; all observations remain distinct.
                    if observations:item.update(observations[0])
            if kind=='dead':
                items=[x for x in items if not x['name'].startswith('__') and not any(fnmatch.fnmatchcase(x['qualified_name'],p) for p in self.settings.entrypoints)]
            if kind=='cochange':
                for x in items:
                    x['jaccard']=x['together']/max(1,x['base_commits']+x['other_commits']-x['together'])
            failures=db.execute("SELECT count(*) FROM files WHERE status!='ok'").fetchone()[0]
            return {'snapshot':snapshot,'generation':Store.get(db,'generation'),
                    'query':kind,'items':items,'truncated':cut,
                    'next_offset':offset+limit if cut and sql else None,
                    'excluded_or_failed_files':failures,'limitations':notes}
