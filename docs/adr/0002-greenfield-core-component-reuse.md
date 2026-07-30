# Greenfield scenario core, reuse at component level only

Existing CTI implementations (BECTI, KP Liberation, Warlords) were considered as a base. We build our own scenario core instead, because the project's top objectives are automated testability and agentic development — existing CTIs keep state in-process and have no test seams, and retrofitting seams into them costs more than a greenfield core. Reuse happens at component level: CBA, HEMTT, vanilla assets, and ideas or licence-compatible snippets from BECTI/KP Liberation, never their architecture.

A driving requirement: the player must be able to play as Commander or as squad leader (both sides AI-commanded), so the AI Commander must be a complete peer of the human — no existing CTI treats it that way.
