# server

Python control-plane service skeleton for:

- auth
- chat routing
- presence
- device registry
- future remote-session coordination

Current milestone:

- in-memory login dispatch
- in-memory device list response
- lightweight JSON persistence for conversation and remote-session runtime state
- conversation sync response
- message send and delivery response
- remote invite, reject, cancel, and approval flow
- relay assignment placeholder response

Run:

```powershell
python -m server.main
python -m server.main --tcp-server
python -m server.main --state-file .\server\data\runtime_state.json
```

`python -m server.main` runs the in-process dispatch demo.

`python -m server.main --tcp-server` runs the local line-delimited JSON TCP control plane on `127.0.0.1:8787`.

The default runtime state file is `server/data/runtime_state.json`. Conversations and remote-session
records are saved there so messages and remote-session state survive process restarts. Active login
sessions still remain in memory for now.
