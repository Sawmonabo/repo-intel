from __future__ import annotations

import ast
import collections
import json
import re
from .config import Settings, digest, identity
from .syntax import Scope, Bindings, dotted, expression, fingerprint, import_base


class Extractor(ast.NodeVisitor):
    """One-file collector. It never imports or executes the analyzed program."""
    def __init__(self, conn, path: str, module: str, file_hash: str, settings: Settings):
        self.db,self.path,self.module,self.hash,self.settings=conn,path,module,file_hash,settings
        self.package=path.endswith('/__init__.py') or path=='__init__.py'
        self.scope=None;self.ordinals=collections.Counter();self.conditional=0;self.type_only=0;self.loops=0

    def sid(self, qualified, kind):
        self.ordinals[(qualified,kind)]+=1
        return identity(self.path,qualified,kind,self.ordinals[(qualified,kind)])

    def site(self, node, kind, suffix=''):
        return identity(self.path,self.hash,self.scope.id,kind,getattr(node,'lineno',1),getattr(node,'col_offset',0),suffix)

    def pattern(self,node,rule,detail):
        self.db.execute('INSERT OR IGNORE INTO patterns VALUES(?,?,?,?,?,?,?)',
                        (self.site(node,'pattern',rule),self.path,self.scope.id,node.lineno,node.col_offset,rule,detail))

    def access(self,node,resource,kind,mode,certainty='lexical'):
        self.db.execute('INSERT OR IGNORE INTO accesses VALUES(?,?,?,?,?,?,?,?,?)',
            (self.site(node,'access',resource+mode),self.path,self.scope.id,node.lineno,node.col_offset,resource,kind,mode,certainty))

    def symbol(self,node,qualified,kind,parent):
        sid=self.sid(qualified,kind)
        params=[]
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            params=[x.arg for x in node.args.posonlyargs+node.args.args+node.args.kwonlyargs]
        decorators=[expression(x) for x in getattr(node,'decorator_list',[])]
        is_test=int(getattr(node,'name','').startswith('test_') or '/tests/' in '/'+self.path)
        fp=(None,None,None,0,1,[])
        if kind=='function':fp=fingerprint(node,self.settings.clone_max_tokens)
        self.db.execute('INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (sid,self.path,qualified,getattr(node,'name',self.module),kind,parent,
             getattr(node,'lineno',1),getattr(node,'col_offset',0),getattr(node,'end_lineno',1) or 1,
             getattr(node,'end_col_offset',0),json.dumps(params),json.dumps(decorators),is_test,*fp[:5]))
        if kind=='function' and fp[3]>=self.settings.clone_min_nodes:
            self.db.executemany('INSERT OR IGNORE INTO clone_bands VALUES(?,?)',((b,sid) for b in fp[5]))
        return sid

    def collect(self,text):
        tree=ast.parse(text,filename=self.path,type_comments=True)
        tree.end_lineno=max(1,len(text.splitlines()))
        mid=self.symbol(tree,self.module,'module',None)
        self.scope=Scope(mid,self.module,'module',None)
        Bindings(self.scope,self.module,self.package).prepare(tree.body)
        # Module assignments are explicitly shared state, not unresolved locals.
        for name in self.scope.assigned:
            self.scope.bindings.setdefault(name,(self.module+'.'+name,'lexical'))
        self.visit(tree)

    def definition(self,node,kind):
        parent=self.scope
        q=parent.qualified+'.'+node.name
        sid=self.symbol(node,q,kind,parent.id)
        # Definition-time calls belong to enclosing scope, not function body.
        for deco in node.decorator_list:
            self.visit(deco)
        if kind=='function':
            for val in node.args.defaults+node.args.kw_defaults:
                if val:self.visit(val)
            for arg in node.args.posonlyargs+node.args.args+node.args.kwonlyargs:
                if arg.annotation:self.visit(arg.annotation)
            if node.returns:self.visit(node.returns)
        else:
            for base in node.bases:self.visit(base)
            for keyword in node.keywords:self.visit(keyword.value)
        self.scope=Scope(sid,q,kind,parent)
        Bindings(self.scope,self.module,self.package).prepare(node.body,node.args if kind=='function' else None)
        if kind=='function':
            if any(isinstance(x,ast.Constant) and isinstance(x.value,bool) for x in node.args.defaults+node.args.kw_defaults if x):
                self.pattern(node,'mode_flag','Boolean default parameter: verify whether separate behaviors belong together')
            if len(node.body)==1 and isinstance(node.body[0],ast.Return) and isinstance(node.body[0].value,ast.Call):
                self.pattern(node,'forwarding_wrapper','Single-call forwarding wrapper; may protect an intentional contract')
        for deco in node.decorator_list:
            if any(x in expression(deco) for x in ('skip','xfail')):
                self.pattern(deco,'skipped_test','Skip/xfail decorator; inspect condition and reason')
        for stmt in node.body:self.visit(stmt)
        self.scope=parent

    def visit_FunctionDef(self,node):self.definition(node,'function')
    visit_AsyncFunctionDef=visit_FunctionDef
    def visit_ClassDef(self,node):self.definition(node,'class')

    def visit_Lambda(self,node):
        self.pattern(node,'dynamic_scope','Lambda body is not assigned an independent callable identity')
        # Still collect syntax, but suppress parent lexical binding of lambda args.
        old=self.scope
        self.scope=Scope(old.id,old.qualified,'function',old)
        Bindings(self.scope,self.module,self.package).prepare([],node.args)
        self.visit(node.body)
        self.scope=old

    def resource(self,node):
        name=dotted(node)
        if isinstance(node,ast.Subscript):return self.resource(node.value)
        if not name:return None
        first,*rest=name.split('.')
        cur=self.scope
        if first in ('self','cls') and cur.parent and cur.parent.kind=='class' and rest:
            return 'attribute:'+cur.parent.qualified+'.'+'.'.join(rest),'attribute','possible_instance'
        while cur:
            if first in cur.globals:
                return 'global:'+self.module+'.'+name,'global','lexical'
            if first in cur.bindings:
                target,reason=cur.bindings[first]
                if target and (cur.kind=='module' or reason=='import'):
                    return 'global:'+'.'.join([target]+rest),'global',('possible_attribute' if rest else 'lexical')
                return None
            if first in cur.assigned:return None
            cur=cur.parent
        if rest:return 'attribute:'+self.scope.qualified+':'+name,'attribute','unresolved_receiver'
        return None

    def visit_Name(self,node):
        mode='write' if isinstance(node.ctx,(ast.Store,ast.Del)) else 'read'
        target,_=self.scope.resolve(node)
        self.db.execute('INSERT OR IGNORE INTO refs VALUES(?,?,?,?,?,?,?,?)',
            (self.site(node,'ref',node.id+mode),self.path,self.scope.id,node.lineno,node.col_offset,node.id,target,mode))
        resource=self.resource(node)
        if resource:self.access(node,resource[0],resource[1],mode,resource[2])

    def visit_Attribute(self,node):
        target,_=self.scope.resolve(node)
        mode='write' if isinstance(node.ctx,(ast.Store,ast.Del)) else 'read'
        self.db.execute('INSERT OR IGNORE INTO refs VALUES(?,?,?,?,?,?,?,?)',
            (self.site(node,'ref',dotted(node)+mode),self.path,self.scope.id,node.lineno,node.col_offset,node.attr,target,mode))
        resource=self.resource(node)
        if resource:self.access(node,resource[0],resource[1],mode,resource[2])
        self.visit(node.value)

    def visit_Subscript(self,node):
        name=dotted(node.value)
        mode='write' if isinstance(node.ctx,(ast.Store,ast.Del)) else 'read'
        if name.endswith('environ') and isinstance(node.slice,ast.Constant) and isinstance(node.slice.value,str):
            self.access(node,'env:'+node.slice.value,'environment',mode,'literal_key')
        else:
            resource=self.resource(node.value)
            if resource:self.access(node,resource[0],resource[1],mode,resource[2])
        self.generic_visit(node)

    def visit_AugAssign(self,node):
        resource=self.resource(node.target)
        if resource:self.access(node,resource[0],resource[1],'read',resource[2])
        self.generic_visit(node)

    def visit_Call(self,node):
        target,reason=self.scope.resolve(node.func)
        args={'positional':[expression(x) for x in node.args],
              'keywords':{x.arg or '**':expression(x.value) for x in node.keywords}}
        self.db.execute('INSERT OR IGNORE INTO calls VALUES(?,?,?,?,?,?,?,?,?,?)',
            (self.site(node,'call'),self.path,self.scope.id,node.lineno,node.col_offset,node.end_lineno,
             expression(node.func),target,reason,json.dumps(args)))
        name=dotted(node.func)
        if name in ('open','io.open','builtins.open') and node.args:
            p=node.args[0]
            key=p.value if isinstance(p,ast.Constant) and isinstance(p.value,str) else '<dynamic:'+expression(p)+'>'
            mode='r'
            if len(node.args)>1 and isinstance(node.args[1],ast.Constant):mode=str(node.args[1].value)
            for kw in node.keywords:
                if kw.arg=='mode' and isinstance(kw.value,ast.Constant):mode=str(kw.value.value)
            rw='read_write' if '+' in mode else ('write' if any(x in mode for x in 'wax') else 'read')
            self.access(node,'file:'+key,'file',rw,'literal_path' if isinstance(p,ast.Constant) else 'dynamic_path')
        if name.endswith(('getenv','environ.get')) and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str):
            self.access(node,'env:'+node.args[0].value,'environment','read','literal_key')
        if isinstance(node.func,ast.Attribute):
            attr=node.func.attr
            obj=node.func.value
            resource=self.resource(obj)
            mutations={'append','extend','insert','pop','remove','clear','update','setdefault','add','discard','set','delete','write'}
            if resource:self.access(node,resource[0],resource[1],'write' if attr in mutations else 'read','possible_method_effect')
            if isinstance(obj,ast.Name) and obj.id in self.scope.paths and attr in ('read_text','read_bytes','write_text','write_bytes','unlink'):
                self.access(node,'file:'+self.scope.paths[obj.id],'file','read' if attr.startswith('read') else 'write','literal_path')
        if self.loops and name.endswith(('sleep','wait')):
            self.pattern(node,'sleep_loop','Sleep/wait within a loop; inspect retry/backoff policy')
        if name.endswith(('.skip','.xfail')):
            self.pattern(node,'skipped_test','Runtime skip/xfail call')
        self.generic_visit(node)

    def visit_Import(self,node):
        for alias in node.names:
            self.add_import(node,alias.name,None,alias.asname)
            if self.scope.kind=='module':
                self.db.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?)',
                    (self.path,self.module+'.'+(alias.asname or alias.name.split('.')[0]),alias.name if alias.asname else alias.name.split('.')[0]))

    def add_import(self,node,module,imported,alias):
        self.db.execute('INSERT OR IGNORE INTO imports VALUES(?,?,?,?,?,?,?,?,?,?)',
            (self.site(node,'import',module+str(imported)+str(alias)),self.path,self.scope.id,node.lineno,module,imported,alias,int(self.type_only>0),int(self.conditional>0),None))

    def visit_ImportFrom(self,node):
        base=import_base(node,self.module,self.package)
        for alias in node.names:
            self.add_import(node,base,alias.name,alias.asname)
            if alias.name=='*':
                self.pattern(node,'unresolved_star_import','Star import is recorded but exports are not guessed')
            elif self.scope.kind=='module':
                self.db.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?)',
                    (self.path,self.module+'.'+(alias.asname or alias.name),(base+'.'+alias.name).strip('.')))

    def visit_If(self,node):
        if any(isinstance(x,ast.Compare) and any(isinstance(c,ast.Constant) for c in x.comparators) for x in ast.walk(node.test)):
            self.pattern(node,'literal_branch','Branch compares against a literal; this is not inherently a defect')
        self.visit(node.test)
        typing_guard=dotted(node.test).endswith('TYPE_CHECKING')
        self.conditional+=1
        if typing_guard:self.type_only+=1
        for x in node.body:self.visit(x)
        if typing_guard:self.type_only-=1
        for x in node.orelse:self.visit(x)
        self.conditional-=1

    def visit_ExceptHandler(self,node):
        if all(isinstance(x,(ast.Pass,ast.Continue)) or (isinstance(x,ast.Return) and (x.value is None or isinstance(x.value,ast.Constant) and x.value.value is None)) for x in node.body):
            self.pattern(node,'swallowed_exception','Exception handler discards the exception without propagation')
        if self.loops:self.pattern(node,'retry_loop','Exception handler in loop: inspect retry and termination behavior')
        self.generic_visit(node)

    def loop(self,node):
        self.loops+=1;self.generic_visit(node);self.loops-=1
    visit_For=loop
    visit_AsyncFor=loop
    visit_While=loop

    def visit_Constant(self,node):
        value=node.value
        if (isinstance(value,str) and len(value)>=3) or (type(value) in (int,float) and value not in (0,1)):
            # Literal values can be secrets. Persist their hash and size, not their contents.
            encoded=repr(value)
            self.db.execute('INSERT OR IGNORE INTO literals VALUES(?,?,?,?,?,?)',
                (self.path,self.scope.id,node.lineno,type(value).__name__,digest(encoded),len(encoded)))
