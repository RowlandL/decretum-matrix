# Hermes Studio Group Chat 调用排查札记

Use this reference when the user asks how Hermes Studio rooms, same-room profiles, or `@profile` wakeups are invoked.

## Durable lesson

Do **not** assume Hermes Studio group-chat rooms use the public OpenAI-compatible API Server (`/v1/chat/completions`) or the MCP `chat-run` endpoint. In the observed Studio build, room chat is a separate Studio surface:

- REST endpoints manage rooms and room agents.
- Socket.IO namespace `/group-chat` carries real-time join/message events.
- Mention routing happens inside the group-chat server pipeline after messages are saved.

## Official-docs lookup order

1. Load the Hermes/Court skills that govern the task.
2. Query Hermes Studio OpenAPI through the MCP docs tool when the user asks for API/manual docs.
3. Check the public Hermes docs at `https://hermes-agent.nousresearch.com/docs` for API Server, Open WebUI, gateway, and multi-profile guidance.
4. If OpenAPI/docs mention group chat but do not expose `/api/hermes/group-chat/*`, treat Studio group chat as an internal/underdocumented Web UI feature and inspect the local Studio bundle before making claims.

## Observed local Studio surfaces

From `dist/server/index.js` and `dist/client/assets/js/GroupChatView-*.js` in the Hermes Studio Web UI bundle:

- `POST /api/hermes/group-chat/rooms`
- `GET /api/hermes/group-chat/rooms`
- `GET /api/hermes/group-chat/rooms/:roomId`
- `GET /api/hermes/group-chat/rooms/join/:code`
- `POST /api/hermes/group-chat/rooms/:roomId/agents`
- `GET /api/hermes/group-chat/rooms/:roomId/agents`
- `DELETE /api/hermes/group-chat/rooms/:roomId/agents/:agentId`
- `POST /api/hermes/group-chat/rooms/:roomId/clear-context`
- `PUT /api/hermes/group-chat/rooms/:roomId/config`
- `POST /api/hermes/group-chat/rooms/:roomId/compress`

Socket.IO:

- namespace: `/group-chat`
- browser user auth includes token plus `userId`, `name`, `description`, optional `authUserId`
- user join: `emit("join", { roomId, name, description })`
- user message: `emit("message", { roomId, id, content })`
- agent sockets also use `/group-chat`, but authenticate with `source: "agent"` and an internal `agentSocketSecret`

## Pitfalls

- Do not claim public documentation fully specifies Studio rooms unless the current docs actually expose the room endpoints.
- Do not use `/api/chat-run/runs` or `/v1/chat/completions` as proof of same-room `@profile` routing; those are different execution surfaces.
- When testing `@profile`, send one bounded Socket.IO room message, then observe actual room messages/agent replies. Do not simulate responses for other profiles.
- If the docs are incomplete, say so plainly and distinguish: “official public docs” vs “local bundled Studio implementation.”

## Suggested verification shape

A future bounded probe should:

1. Resolve the current room id and participant agents through the group-chat REST endpoints, local Studio bundle, or approved room-state store. Do not assume normal Hermes profile `state.db` contains `gc_*` room tables.
2. Resolve the actual Studio server port first; do not hard-code a remembered port from another session.
3. Connect to `/group-chat` as a user socket with an authenticated token. If the socket reaches the namespace but returns `Unauthorized`, record `runtime_degraded/auth_blocked` and stop rather than treating it as a router failure.
4. `join` the target room.
5. `message` a compact wakeup request mentioning target profiles.
6. Read back actual room messages and report responders/non-responders.
7. If no approved token is available, ask the user to send the same wake message manually from the Studio room UI; do not simulate replies.
8. Record Shiguan evidence without looping on silent profiles.

Session-specific reproduction notes are retained in shared Shiguan at `references/audits/historical-probes/group-chat-user-origin-probe-20260702.md`, outside portable skill copies. That bounded Socket.IO probe found that agent-origin `@` did not recursively wake profiles, `8648` was not a valid server endpoint, `8748` reached `/group-chat` but returned `Unauthorized`, and MCP OpenAPI did not expose group-chat endpoints in that build.
