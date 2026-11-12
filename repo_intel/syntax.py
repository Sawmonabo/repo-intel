from __future__ import annotations

import ast
import hashlib
import json
import zlib
from dataclasses import dataclass, field


def dotted(node: ast.AST | None) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted(node.value)
        return f'{prefix}.{node.attr}' if prefix else ''
    return ''


def expression(node: ast.AST | None, maximum: int = 400) -> str:
    if node is None:
        return ''
    try:
        return ast.unparse(node)[:maximum]
    except (RecursionError, ValueError):
        return '<expression-too-deep>'


def import_base(node: ast.ImportFrom, module: str, package: bool) -> str:
    if not node.level:
        return node.module or ''
    parts = module.split('.') if package else module.split('.')[:-1]
    if node.level > len(parts) + 1:
        return '<invalid-relative>'
    keep = len(parts) - node.level + 1
    return '.'.join(parts[:keep] + ([node.module] if node.module else []))


@dataclass
class Scope:
    id: str
    qualified: str
    kind: str
    parent: 'Scope | None'
    bindings: dict[str, tuple[str | None, str]] = field(default_factory=dict)
    assigned: set[str] = field(default_factory=set)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)
    paths: dict[str, str] = field(default_factory=dict)

    def lookup(self, name: str) -> tuple[str | None, str]:
        if name in self.globals:
            outer = self
            while outer.parent:
                outer = outer.parent
            return outer.bindings.get(name, (outer.qualified+'.'+name, 'lexical'))
        if name in self.bindings:
            return self.bindings[name]
        if name in self.assigned:
            return None, 'unresolved'
        if self.parent:
            outer = self.parent
            # Class namespaces are not lexical enclosing scopes for method bodies.
            if self.kind == 'function' and outer.kind == 'class':
                outer = outer.parent
            return outer.lookup(name) if outer else (None, 'unresolved')
        return None, 'unresolved'

    def resolve(self, node: ast.AST) -> tuple[str | None, str]:
        name = dotted(node)
        if not name:
            return None, 'unresolved'
        first, *rest = name.split('.')
        if first in ('self','cls') and self.kind == 'function' and self.parent and self.parent.kind=='class':
            return '.'.join([self.parent.qualified]+rest), 'possible_receiver'
        base, reason = self.lookup(first)
        if base:
            return '.'.join([base]+rest), reason
        return None, 'unresolved'


class Bindings(ast.NodeVisitor):
    """Collect lexical declarations, without descending into nested scopes."""
    def __init__(self, scope: Scope, module: str, package: bool):
        self.scope,self.module,self.package=scope,module,package

    def visit_Name(self,node):
        if isinstance(node.ctx,(ast.Store,ast.Del)):
            self.scope.assigned.add(node.id)

    def visit_Global(self,node):
        self.scope.globals.update(node.names)

    def visit_Nonlocal(self,node):
        self.scope.nonlocals.update(node.names)

    def visit_FunctionDef(self,node):
        self.scope.bindings[node.name]=(self.scope.qualified+'.'+node.name,'lexical')
        self.scope.assigned.add(node.name)

    visit_AsyncFunctionDef=visit_FunctionDef
    visit_ClassDef=visit_FunctionDef

    def visit_Lambda(self,node):
        pass

    def visit_Import(self,node):
        for a in node.names:
            self.scope.bindings[a.asname or a.name.split('.')[0]]=(a.name if a.asname else a.name.split('.')[0],'import')

    def visit_ImportFrom(self,node):
        base=import_base(node,self.module,self.package)
        for a in node.names:
            if a.name!='*':
                self.scope.bindings[a.asname or a.name]=(f'{base}.{a.name}'.strip('.'),'import')

    def prepare(self, body, arguments=None):
        for node in body:
            self.visit(node)
        for name in self.scope.globals | self.scope.nonlocals:
            self.scope.assigned.discard(name)
        if arguments:
            for arg in arguments.posonlyargs+arguments.args+arguments.kwonlyargs:
                self.scope.assigned.add(arg.arg)
                self.scope.bindings[arg.arg]=(None,'unresolved')
            for arg in (arguments.vararg,arguments.kwarg):
                if arg:
                    self.scope.assigned.add(arg.arg);self.scope.bindings[arg.arg]=(None,'unresolved')
        # Direct assignment aliases are marked possible, never exact resolution.
        for node in body:
            if isinstance(node,(ast.Assign,ast.AnnAssign)) and node.value is not None:
                value=node.value
                target,reason=self.scope.resolve(value.func if isinstance(value,ast.Call) else value)
                targets=node.targets if isinstance(node,ast.Assign) else [node.target]
                for t in targets:
                    if isinstance(t,ast.Name) and target:
                        self.scope.bindings[t.id]=(target,'possible_assignment')
                    if isinstance(t,ast.Name) and isinstance(value,ast.Call) and dotted(value.func).endswith('Path') and value.args and isinstance(value.args[0],ast.Constant) and isinstance(value.args[0].value,str):
                        self.scope.paths[t.id]=value.args[0].value


def fingerprint(node: ast.AST, max_tokens: int):
    names={}
    def norm(n):
        if n not in names: names[n]=f'v{len(names)}'
        return names[n]
    def walk(value, normalized=False, field_name=''):
        if isinstance(value,ast.AST):
            yield type(value).__name__
            for key,item in ast.iter_fields(value):
                if key in ('type_comment','returns','decorator_list'):
                    continue
                if key=='name' and isinstance(value,(ast.FunctionDef,ast.AsyncFunctionDef)):
                    item='<function>'
                if normalized and ((isinstance(value,ast.Name) and key=='id') or (isinstance(value,ast.arg) and key=='arg')):
                    item=norm(item)
                yield key
                yield from walk(item,normalized,key)
        elif isinstance(value,list):
            yield '['
            for item in value:
                yield from walk(item,normalized,field_name)
            yield ']'
        else:
            yield repr(value)
    exact=hashlib.sha256()
    for token in walk(node): exact.update(token.encode('utf-8'));exact.update(b'\0')
    normalized=hashlib.sha256();tokens=[];count=0
    for token in walk(node,True):
        normalized.update(token.encode('utf-8'));normalized.update(b'\0');count+=1
        if len(tokens)<max_tokens:tokens.append(token)
    # Four min-wise shingle signatures retrieve candidates. Not semantic equivalence.
    shingles=sorted(set(hashlib.blake2s('\0'.join(tokens[i:i+5]).encode(),digest_size=8).hexdigest()
                        for i in range(max(0,len(tokens)-4))))
    bands=shingles[:4]
    return exact.hexdigest(),normalized.hexdigest(),zlib.compress(json.dumps(tokens,separators=(',',':')).encode(),level=1),count,int(count<=max_tokens),bands
