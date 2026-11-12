from __future__ import annotations

import fnmatch
import json
import zlib
from collections import deque


def graph_walk(db, symbol, direction, max_depth, budget):
    visited={symbol['id']};queue=deque([(symbol['id'],0)])
    found=[];cut=False
    while queue:
        current,depth=queue.popleft()
        if depth>=max_depth:
            test=('SELECT 1 FROM call_targets t JOIN calls c ON c.id=t.call WHERE t.target=? LIMIT 1'
                  if direction=='incoming' else 'SELECT 1 FROM calls c JOIN call_targets t ON c.id=t.call WHERE c.caller=? LIMIT 1')
            if db.execute(test,(current,)).fetchone():cut=True
            continue
        if direction=='incoming':
            sql='''SELECT s.*,c.line AS call_line,c.col AS call_col,c.file AS call_file,c.resolution
                FROM call_targets t JOIN calls c ON c.id=t.call JOIN symbols s ON s.id=c.caller
                WHERE t.target=?'''
        else:
            sql='''SELECT s.*,c.line AS call_line,c.col AS call_col,c.file AS call_file,c.resolution
                FROM calls c JOIN call_targets t ON t.call=c.id JOIN symbols s ON s.id=t.target
                WHERE c.caller=?'''
        for row in db.execute(sql,(current,)):
            if row['id'] in visited:continue
            if len(visited)>=budget:cut=True;queue.clear();break
            visited.add(row['id'])
            found.append({'id':row['id'],'qualified_name':row['qualified_name'],'file':row['file'],
                          'line':row['line'],'depth':depth+1,'via_symbol':current,
                          'call_file':row['call_file'],'call_line':row['call_line'],
                          'call_col':row['call_col'],'resolution':row['resolution']})
            queue.append((row['id'],depth+1))
    return found,cut


def import_cycles(db,budget,limit):
    """Iterative Tarjan. Keep module bookkeeping, not the symbol/call graph, in RAM."""
    files=[r[0] for r in db.execute("SELECT path FROM files WHERE language='python' ORDER BY path LIMIT ?",(budget+1,))]
    truncated=len(files)>budget
    files=files[:budget];allowed=set(files)
    index={};low={};onstack=set();stack=[];counter=0;components=[]
    def adjacent(node):
        return iter([r[0] for r in db.execute('SELECT DISTINCT target_file FROM imports WHERE file=? AND type_only=0 AND target_file IS NOT NULL',(node,)) if r[0] in allowed])
    for root in files:
        if root in index:continue
        index[root]=low[root]=counter;counter+=1;stack.append(root);onstack.add(root)
        frames=[(root,adjacent(root))]
        while frames:
            node,neighbors=frames[-1]
            try:
                other=next(neighbors)
            except StopIteration:
                frames.pop()
                if frames:low[frames[-1][0]]=min(low[frames[-1][0]],low[node])
                if low[node]==index[node]:
                    component=[]
                    while True:
                        item=stack.pop();onstack.remove(item);component.append(item)
                        if item==node:break
                    self_edge=db.execute('SELECT 1 FROM imports WHERE file=? AND target_file=? AND type_only=0 LIMIT 1',(node,node)).fetchone()
                    if len(component)>1 or self_edge:
                        components.append(component)
                        if len(components)>=limit:
                            return components,True
                continue
            if other not in index:
                index[other]=low[other]=counter;counter+=1;stack.append(other);onstack.add(other)
                frames.append((other,adjacent(other)))
            elif other in onstack:low[node]=min(low[node],index[other])
    return components,truncated


def architecture(db,settings,limit):
    results=[]
    def layer(module):
        for i,spec in enumerate(settings.layers):
            if any(module==p or module.startswith(p+'.') or fnmatch.fnmatchcase(module,p) for p in spec.get('modules',[])):
                return i,spec.get('name',str(i))
        return None
    for row in db.execute('''SELECT i.*,f.module AS source_module,t.module AS target_module
        FROM imports i JOIN files f ON f.path=i.file JOIN files t ON t.path=i.target_file WHERE i.type_only=0'''):
        src,dst=row['source_module'],row['target_module']
        violation=None
        a,b=layer(src),layer(dst)
        if a and b and a[0]>b[0]:violation=f'Lower layer {a[1]} imports upper layer {b[1]}'
        for rule in settings.boundaries:
            if fnmatch.fnmatchcase(src,rule.get('from','')) and any(fnmatch.fnmatchcase(dst,p) for p in rule.get('deny',[])):
                violation='Configured dependency boundary violated'
        if violation:
            results.append({'file':row['file'],'line':row['line'],'source':src,'target':dst,'rule':'layer_violation','message':violation})
        if len(results)>=limit:return results,True
    return results,False


def clones(db,symbol,limit,min_tokens):
    if symbol:
        a=symbol
        rows=db.execute('''SELECT DISTINCT s.* FROM clone_bands b JOIN clone_bands other ON b.band=other.band
            JOIN symbols s ON s.id=other.symbol WHERE b.symbol=? AND s.id!=? LIMIT ?''',(a['id'],a['id'],limit+1))
        result=[]
        ta=json.loads(zlib.decompress(a['tokens'])) if a['tokens'] else [];sa={tuple(ta[i:i+5]) for i in range(max(0,len(ta)-4))}
        candidates=list(rows);truncated=len(candidates)>limit
        for b in candidates[:limit]:
            tb=json.loads(zlib.decompress(b['tokens'])) if b['tokens'] else [];sb={tuple(tb[i:i+5]) for i in range(max(0,len(tb)-4))}
            similarity=len(sa&sb)/max(1,len(sa|sb))
            if similarity>=0.7:
                result.append({'kind':'structural_candidate','similarity':round(similarity,4),
                    'first':{'id':a['id'],'file':a['file'],'line':a['line'],'end_line':a['end_line']},
                    'second':{'id':b['id'],'file':b['file'],'line':b['line'],'end_line':b['end_line']},
                    'complete_tokens':bool(a['tokens_complete'] and b['tokens_complete'])})
        return result,truncated
    groups=list(db.execute('''SELECT normalized_hash,count(*) AS n FROM symbols WHERE kind='function'
        AND token_count>=? GROUP BY normalized_hash HAVING n>1 ORDER BY n DESC LIMIT ?''',(min_tokens,limit+1)))
    results=[]
    for g in groups[:limit]:
        members=[dict(r) for r in db.execute('SELECT id,qualified_name,file,line,end_line FROM symbols WHERE normalized_hash=? ORDER BY file,line LIMIT 101',(g[0],))]
        results.append({'kind':'renamed_ast_equivalent_candidate','signature':g[0],'count':g[1],
                        'members':members[:100],'members_truncated':len(members)>100})
    return results,len(groups)>limit
