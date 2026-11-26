# Jetson Backpack integration

This directory versions the companion runtime needed by the optional native Backpack bridge in DAWN. Ordinary DAWN installations do not need these services. The bridge is enabled by `DAWN_BACKPACK_SOCKET`; leave it unset outside the Backpack installation.

## Native development layout

The prepared NX workspace has sibling `dawn/`, `backpack/`, `deps/` and private `run/` directories. Copy the files from this directory into the sibling `backpack/` directory before invoking its setup, build, validation or launch scripts. Those scripts intentionally retain the deployed layout; do not run `validate.sh` from this source directory. Private speech libraries, downloaded models and TensorRT engines remain in the prepared workspace, outside Git.

The existing installation uses the native `build_dev.sh` and `start_dev.sh` scripts, not Docker. Read `DEV_SETUP.md`, `RUNTIME.md`, `HOST_TOOLS.md`, `EVENTS.md` and `YOLO.md` for the feature boundaries. Some historical links refer to the parent JETSON-BACKPACK workspace's learning and hardware documents.

`dawn-dev.toml` is the non-secret development configuration: local Ollama, a loopback MQTT broker, simulated battery data, a restricted local tool list and HTTPS on port 3001. Provision `run/ssl/dawn.crt` and `run/ssl/dawn.key` privately before startup. Keep all real credentials, certificates/private keys, SQLite databases, models and generated engines outside this directory. Never copy the parent workspace's `secret.agent.env` here.

## Update and rollback

Keep the fork's `main` as the upstream reference and merge it into the Backpack integration branch. Review `src/dawn.c` hooks alongside changes to sessions, cancellation and model resolution. Preserve upstream authentication/security fixes and the Backpack attended-confirmation boundary. A text merge is not sufficient validation.

Before deployment, retain the previous source, native binaries, configuration, user units and consistent SQLite backups in a private directory under `run/`. Back up `run/data/auth.db`, `run/data/music.db`, `run/backpack.db`, `run/stat.db` and, once present, `run/data/music_queue.db`. Stop DAWN for the final database checkpoint before first starting the new version. New upstream database migrations mean binary rollback alone is insufficient: restore the matching pre-upgrade database snapshots while their writers are stopped. Preserve any post-upgrade data separately before restoring.

Build and validate a separate candidate workspace first. Run `sh backpack/validate.sh`, the selected upstream native tests and source invariant checks. Exercise database migrations against copied databases before touching live state. Verify HTTPS login/status behavior and service readiness after deployment. Retain the previous binary and database snapshots until acceptance; do not reboot or exercise real power actions as smoke tests.
