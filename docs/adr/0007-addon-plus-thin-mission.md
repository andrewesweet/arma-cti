# Addon mod with thin per-map missions, not a mission-packaged CTI

Classic CTIs ship as a single mission PBO. We instead put all logic in a HEMTT-built addon (`@arma-cti`); each map gets a near-empty mission (slots, description.ext) plus its manifest. Chosen for HEMTT lint/build integration, CBA macro support, file-patching dev loop, and zero logic duplication per map. Cost: the client must launch with the mod loaded — acceptable for personal use.
