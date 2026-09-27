# Third-party dependency notices

Original ControlSurface source is licensed under Apache-2.0. Dependencies, container base images, database images, and optional browser binaries retain their own licenses and notices. Installed packages keep their upstream license metadata; distributors must preserve applicable license and notice files.

This inventory highlights direct runtime dependencies and important transitive/native components. It was reconciled on 2026-09-27 with the installed Python metadata, installed standalone-web package metadata, and Alpine package-license metadata in the locally built Linux/amd64 release-candidate images. It is not legal advice.

| Component | Runtime purpose | License |
| --- | --- | --- |
| FastAPI, Pydantic, Starlette | HTTP API and validation | MIT |
| Uvicorn | ASGI server | BSD-3-Clause |
| Psycopg, Psycopg Binary, Psycopg Pool | PostgreSQL access and pooling | LGPL-3.0-only |
| ClickHouse Connect | ClickHouse client | Apache-2.0 |
| OpenTelemetry Python and OTLP protocol definitions | SDK and telemetry protocol | Apache-2.0 |
| gRPC | OTLP/gRPC receiver | Apache-2.0 |
| Protocol Buffers | OTLP messages | BSD-3-Clause |
| argon2-cffi and argon2-cffi-bindings | Password hashing | MIT |
| jsonschema | Deterministic schema evaluation | MIT |
| Next.js | Web framework | MIT |
| React and React DOM | Web rendering | MIT |
| Lucide | Generic interface icons | ISC |
| sharp | Next.js image processing | Apache-2.0; bundled native libraries have separate terms |
| sharp/libvips platform packages | Native image libraries | Multiple licenses, including LGPL components; see the supplier's bundled notices |
| certifi | CA bundle | MPL-2.0 |
| caniuse-lite | Browser compatibility data | CC-BY-4.0 |

Development/test dependencies include TypeScript (Apache-2.0), ESLint and Prettier (MIT), Ruff (MIT), mypy (MIT), pytest (MIT), and Playwright Test (Apache-2.0). Playwright and its downloaded browser are used by CI/development and are **not copied into the standalone web runtime image**.

The backend runtime resolution is pinned in `services/controlplane/runtime-constraints.txt`; the web dependency graph is locked by `apps/web/package-lock.json`. The release-candidate scan on 2026-09-27 found no known vulnerabilities in the pinned Python runtime manifest or npm runtime graph. That result is time-specific and must be repeated for a release artifact.

## Binary and container distribution

The repository does not publish container images. Exact package inventories have been reviewed, but publishing a binary or image still requires bundling applicable license texts and notices and satisfying corresponding-source/relinking obligations. In particular:

- LGPL terms apply to identified database/native components. Review the exact linkage and distribution method.
- `sharp` platform packages carry supplier-maintained third-party notices for libvips and its dependencies.
- The pinned Python and Node application images contain Alpine packages under MIT, BSD, MPL, Apache, GPL, and LGPL terms. PostgreSQL and ClickHouse images also contain operating-system and bundled packages beyond this table.
- Downloaded test-browser binaries have their own bundled license notices and are not application runtime dependencies.

The full GNU LGPL-3.0 text is available at <https://www.gnu.org/licenses/lgpl-3.0.html>. Upstream package metadata and license files remain authoritative.
