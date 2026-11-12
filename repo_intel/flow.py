"""Demand-driven statement CFG and lexical reaching definitions.

This intentionally does not advertise heap/alias, interprocedural taint, exception,
short-circuit expression or framework semantics. Unsupported constructs stay visible.
"""
from __future__ import annotations

import ast
import collections
import io
import json
import time
import tokenize

from .config import digest, safe_path
from .queries import choose_symbol
from .storage import Store
from .syntax import expression


class Names(ast.NodeVisitor):
    def __init__(self):
        self.uses, self.defs = set(), set()

    def visit_Name(self,node):
        (self.uses if isinstance(node.ctx,ast.Load) else self.defs).add(node.id)

    def visit_FunctionDef(self,node):
        self.defs.add(node.name)
        for item in node.decorator_list+node.args.defaults+[x for x in node.args.kw_defaults if x]:
            self.visit(item)
    visit_AsyncFunctionDef=visit_FunctionDef

    def visit_ClassDef(self,node):
        self.defs.add(node.name)
        for item in node.decorator_list+node.bases:
            self.visit(item)

    def visit_Lambda(self,node):
        pass

    def visit_AugAssign(self,node):
        self.visit(node.target)
        if isinstance(node.target,ast.Name):
            self.uses.add(node.target.id)
        self.visit(node.value)

    def visit_Import(self,node):
        self.defs.update(x.asname or x.name.split('.')[0] for x in node.names)

    def visit_ImportFrom(self,node):
        self.defs.update(x.asname or x.name for x in node.names if x.name!='*')


class Flow:
    def __init__(self,repo):
        self.repo=repo

    def run(self,symbol: str,*,max_nodes=1000,max_facts=100000,max_seconds=5.0):
        if type(max_nodes) is not int or not 1<=max_nodes<=5000:
            raise ValueError('max_nodes must be 1..5000')
        if type(max_facts) is not int or not 1<=max_facts<=1000000:
            raise ValueError('max_facts must be 1..1000000')
        if not isinstance(max_seconds,(int,float)) or not 0<max_seconds<=60:
            raise ValueError('max_seconds must be in (0,60]')
        deadline=time.monotonic()+max_seconds
        with self.repo.store.read() as db:
            selected=choose_symbol(db,symbol)
            if selected['kind']!='function':
                raise ValueError('Local flow requires a function symbol')
            file=safe_path(self.repo.root,selected['file'])
            if file.stat().st_size>self.repo.settings.max_file_bytes:
                raise ValueError('Source file exceeds parser budget')
            source=file.read_bytes()
            expected=db.execute('SELECT hash FROM files WHERE path=?',(selected['file'],)).fetchone()[0]
            if digest(source)!=expected:
                raise ValueError('Source is stale; index first')
            encoding=tokenize.detect_encoding(io.BytesIO(source).readline)[0]
            tree=ast.parse(source.decode(encoding),filename=str(file))
            function=next((node for node in ast.walk(tree) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
                           and node.lineno==selected['line'] and node.col_offset==selected['col']),None)
            if function is None:
                raise ValueError('Indexed function cannot be found in source')
            call_sites=[]
            for row in db.execute('''SELECT c.*,s.qualified_name AS target_name,s.params AS formal_parameters
                FROM calls c LEFT JOIN call_targets t ON t.call=c.id LEFT JOIN symbols s ON s.id=t.target
                WHERE c.caller=? ORDER BY c.line,c.col LIMIT 1001''',(selected['id'],)):
                call_sites.append({'file':row['file'],'line':row['line'],'column_zero_based':row['col'],
                    'expression':row['expression'],'target_name':row['target_name'],
                    'resolution':row['resolution'],'actual_arguments':json.loads(row['arguments']),
                    'formal_parameter_names':json.loads(row['formal_parameters'] or '[]'),
                    'limitations':['argument_expressions_not_alias_proof','varargs_and_implicit_receiver_binding_not_evaluated']})
            snapshot=Store.get(db,'snapshot')
        builder=Builder(function,max_nodes,max_facts,deadline)
        result=builder.build()
        return {'snapshot':snapshot,'symbol':selected['id'],'qualified_name':selected['qualified_name'],
                'file':selected['file'],'source_hash':expected,**result,
                'call_sites':call_sites[:1000],'call_sites_truncated':len(call_sites)>1000}


class Builder:
    def __init__(self,function,max_nodes,max_facts,deadline):
        self.function=function; self.max_nodes=max_nodes; self.max_facts=max_facts; self.deadline=deadline
        self.nodes=[];self.edges=[];self.unsupported=set();self.budget=None

    def node(self,kind,node=None,uses=(),defs=()):
        if len(self.nodes)>=self.max_nodes or time.monotonic()>self.deadline:
            raise OverflowError('cfg_node_or_time_budget')
        ident=len(self.nodes)
        self.nodes.append({'id':ident,'kind':kind,'line':getattr(node,'lineno',self.function.lineno),
                           'column_zero_based':getattr(node,'col_offset',0),
                           'uses':sorted(uses),'defs':sorted(defs),
                           'text':expression(node,200) if node else kind})
        return ident

    def edge(self,source,target,kind='next'):
        self.edges.append({'from':source,'to':target,'kind':kind})

    def block(self,body,following,break_to=None,continue_to=None):
        first=following
        for stmt in reversed(body):
            names=Names()
            if isinstance(stmt,ast.If):
                names.visit(stmt.test)
                header=self.node('branch',stmt.test,names.uses,names.defs)
                yes=self.block(stmt.body,first,break_to,continue_to)
                no=self.block(stmt.orelse,first,break_to,continue_to)
                self.edge(header,yes,'true');self.edge(header,no,'false');first=header
            elif isinstance(stmt,(ast.For,ast.While)):
                names.visit(stmt.iter if isinstance(stmt,ast.For) else stmt.test)
                if isinstance(stmt,ast.For):names.visit(stmt.target)
                header=self.node('loop',stmt,names.uses,names.defs)
                body_start=self.block(stmt.body,header,first,header)
                otherwise=self.block(stmt.orelse,first,break_to,continue_to)
                self.edge(header,body_start,'true');self.edge(header,otherwise,'false')
                # Label back edges even for loops whose final statement is a branch.
                for edge in self.edges:
                    if edge['to']==header and edge['from']!=header and edge['kind']=='next':edge['kind']='loop'
                first=header
            else:
                if isinstance(stmt,(ast.Try,ast.TryStar,ast.With,ast.AsyncWith,ast.Match,ast.AsyncFor)):
                    self.unsupported.add(type(stmt).__name__)
                names.visit(stmt)
                current=self.node(type(stmt).__name__,stmt,names.uses,names.defs)
                if isinstance(stmt,ast.Return):self.edge(current,1,'return')
                elif isinstance(stmt,ast.Raise):
                    self.unsupported.add('Raise');self.edge(current,1,'unmodeled_exception')
                elif isinstance(stmt,ast.Break):self.edge(current,break_to if break_to is not None else first,'break')
                elif isinstance(stmt,ast.Continue):self.edge(current,continue_to if continue_to is not None else first,'continue')
                else:self.edge(current,first)
                first=current
        return first

    def build(self):
        args=self.function.args
        params=[x.arg for x in args.posonlyargs+args.args+args.kwonlyargs]
        params += [x.arg for x in (args.vararg,args.kwarg) if x]
        try:
            self.node('entry',defs=params);self.node('exit')
            first=self.block(self.function.body,1)
            self.edge(0,first)
        except (OverflowError,RecursionError) as exc:
            self.budget=str(exc) or 'recursion_budget'
        if isinstance(self.function,ast.AsyncFunctionDef):self.unsupported.add('AsyncFunctionDef')
        # Lexical dataflow is meaningful only for reachable normal-flow nodes.
        outgoing=collections.defaultdict(list);incoming=collections.defaultdict(list)
        for edge in self.edges:
            outgoing[edge['from']].append(edge['to']);incoming[edge['to']].append(edge['from'])
        reachable=set();queue=collections.deque([0] if self.nodes else [])
        while queue:
            node=queue.popleft()
            if node in reachable:continue
            reachable.add(node);queue.extend(outgoing[node])
        states={node:set() for node in reachable}
        queue=collections.deque(sorted(reachable));queued=set(queue);facts=0;iterations=0
        while queue:
            if time.monotonic()>self.deadline:
                self.budget='dataflow_time_budget';break
            node=queue.popleft();queued.discard(node);iterations+=1
            previous=set()
            for pred in incoming[node]:previous.update(states.get(pred,()))
            defs=set(self.nodes[node]['defs'])
            after={item for item in previous if item[1] not in defs}
            after.update((node,name) for name in defs)
            new_total=facts+len(after)-len(states[node])
            if new_total>self.max_facts:
                self.budget='dataflow_fact_budget';break
            if after!=states[node]:
                facts=new_total;states[node]=after
                for successor in outgoing[node]:
                    if successor not in queued:queue.append(successor);queued.add(successor)
        data_edges=[];unbound=[]
        for node in sorted(reachable):
            previous=set()
            for pred in incoming[node]:previous.update(states.get(pred,()))
            for name in self.nodes[node]['uses']:
                matches=[source for source,value in previous if value==name]
                if not matches:unbound.append({'node':node,'name':name,'meaning':'external_or_unknown_definition'})
                for source in matches:
                    if len(data_edges)>=self.max_facts:
                        self.budget='output_fact_budget';break
                    data_edges.append({'from':source,'to':node,'name':name,'kind':'lexical_may_reach'})
        return {'scope':'statement_level_normal_control_flow_and_lexical_values',
                'analysis_complete':not self.unsupported and self.budget is None,
                'budget_stop':self.budget,'unsupported_constructs':sorted(self.unsupported),
                'nodes':self.nodes,'control_edges':self.edges,'data_edges':data_edges,
                'unbound_uses':unbound,'syntactically_unreachable_nodes':[n['id'] for n in self.nodes if n['id'] not in reachable],
                'fixedpoint_iterations':iterations,
                'limitations':['Not a global taint or heap-alias analysis',
                               'Implicit exception edges and expression-level short-circuit paths are not modeled',
                               'Unsupported compound statements are opaque conservative syntax nodes, not sound transfer models',
                               'A lexical may-reach edge is not proof that a runtime value reaches another operation']}
