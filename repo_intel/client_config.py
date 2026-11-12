"""Generate configuration fragments; never overwrite an agent's existing settings."""
from __future__ import annotations

import json
import shlex
import sys


def configuration(repo,transport='shared',port=8765,token_path=None):
    executable=sys.executable
    if transport=='shared':
        args=['-m','repo_intel','proxy','--url',f'http://127.0.0.1:{port}/mcp',
              '--token-file',str(token_path or repo.store.state/'mcp-token'),'--timeout','900']
        note='Start one repo-intel serve http process for this worktree. All proxies share that process and its SQLite store.'
    elif transport=='stdio':
        args=['-m','repo_intel','--repo',str(repo.root),'--state',str(repo.store.state),'serve','stdio','--allow-refresh']
        note='Each native client launches a small process; no resident full graph is loaded. Use shared transport for one central service.'
    else:raise ValueError('transport must be shared or stdio')
    command=[executable,*args]
    return {'claude':{'mcpServers':{'repo-intel':{'type':'stdio','command':executable,'args':args}}},
            'codex_toml':'[mcp_servers.repo-intel]\ncommand = '+json.dumps(executable)+'\nargs = '+json.dumps(args)+'\ntool_timeout_sec = 900\n',
            'registration_commands_posix':{
                'claude':'claude mcp add --transport stdio repo-intel -- '+shlex.join(command),
                'codex':'codex mcp add repo-intel -- '+shlex.join(command)},
            'note':note,'no_model_api_credentials':True,
            'client_e2e_validation':'Protocol tested; authenticated Claude Code/Codex clients were not available in the build environment'}
