# Third-party dependency notices

ControlSurface's original source is licensed under Apache-2.0. Package-manager dependencies and base container images retain their own licenses. No code or assets from the private research references are included in this repository.

This inventory highlights direct runtime dependencies and licenses that matter to binary distribution. It is not a claim that transitive packages or container images have been fully cleared for redistribution. Installed packages retain their upstream license and notice files; do not remove those files when packaging the application. Resolve the versions in the Python environment and `apps/web/package-lock.json` when auditing a specific build.

| Component | Use | Upstream license |
| --- | --- | --- |
| [Psycopg 3](https://www.psycopg.org/psycopg3/) (`psycopg`, `psycopg-binary`, `psycopg-pool`) | PostgreSQL driver and pool | LGPL-3.0-only |
| [Next.js](https://github.com/vercel/next.js) | Web application framework | MIT |
| [React](https://github.com/facebook/react) and React DOM | Web rendering | MIT |
| [sharp](https://github.com/lovell/sharp) | Transitive Next.js image-processing dependency | Apache-2.0 for sharp; bundled native libraries have separate terms |
| [sharp-libvips native packages](https://github.com/lovell/sharp-libvips/blob/main/THIRD-PARTY-NOTICES.md) | Transitive platform-specific image libraries | Includes LGPLv3 components and other licenses listed by the supplier |
| [FastAPI](https://github.com/fastapi/fastapi) and [Pydantic](https://github.com/pydantic/pydantic) | API and validation | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI server | BSD-3-Clause |
| [ClickHouse Connect](https://github.com/ClickHouse/clickhouse-connect) | Analytics client | Apache-2.0 |
| [OpenTelemetry Python](https://github.com/open-telemetry/opentelemetry-python) and [OTLP protocol definitions](https://github.com/open-telemetry/opentelemetry-proto) | SDK and telemetry protocol | Apache-2.0 |
| [gRPC](https://github.com/grpc/grpc) | OTLP/gRPC receiver | Apache-2.0 |
| [Protocol Buffers](https://github.com/protocolbuffers/protobuf) | OTLP messages | BSD-3-Clause |
| [argon2-cffi](https://github.com/hynek/argon2-cffi) | Password hashing | MIT |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | Deterministic evaluator | MIT |
| [Lucide](https://github.com/lucide-icons/lucide) | Generic UI icons | ISC |
| [TypeScript](https://github.com/microsoft/TypeScript) | Web type checking | Apache-2.0 |
| [Prettier](https://github.com/prettier/prettier) | Development formatting | MIT |
| [ESLint](https://github.com/eslint/eslint), [eslint-config-next](https://github.com/vercel/next.js), and [eslint-config-prettier](https://github.com/prettier/eslint-config-prettier) | Development linting | MIT |
| [Playwright Test](https://github.com/microsoft/playwright) | Authenticated browser testing; installed in the current web image but not invoked at runtime | Apache-2.0; separately downloaded browser binaries carry their own terms |
| [certifi](https://github.com/certifi/python-certifi) | Transitive CA bundle | MPL-2.0 |
| [caniuse-lite](https://github.com/browserslist/caniuse-lite) | Transitive browser compatibility data | CC-BY-4.0 |

The full [GNU LGPL-3.0 license](https://www.gnu.org/licenses/lgpl-3.0.html) applies to the identified LGPL components. In particular, publishing a Docker image or other binary bundle needs a separate review of accompanying licenses, notices, corresponding source/relinking arrangements, and the exact platform-specific packages in that artifact. The current repository does not publish such an image. Base images (`python:3.13-slim`, `node:22-alpine`, PostgreSQL, and ClickHouse) also require an artifact-specific notice review before redistribution.
