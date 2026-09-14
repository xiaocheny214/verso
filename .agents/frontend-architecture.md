# Frontend Architecture Guide for AI Agents

This document defines the architectural conventions, layer boundaries, domain module structuring, and lint enforcement rules for the Verso frontend. All AI agents working on this codebase must adhere strictly to these principles.

---

## 1. Architecture Overview & Layer Responsibilities

```text
src/
├── lib/                        # Business-agnostic utilities & infrastructure
│   ├── utils.ts                # General UI / classname helper (cn)
│   └── http.ts                 # Generic HTTP client (request)
│
├── model/                      # Data & domain layer (split by domain modules)
│   ├── auth/                   # Authentication & OAuth
│   ├── portrait/               # User portraits, strengths & profiles
│   ├── match/                  # Mutual matching & tickets
│   ├── exchange/               # 24-hour asynchronous exchanges & messages
│   └── common/                 # Cross-module generic contracts (ApiResponse)
│
├── components/                 # Pure UI components & visual presentations
│   ├── ui/                     # Primitives (Button, etc.)
│   ├── providers/              # Context & Query providers
│   └── *.tsx                   # Pure UI views (AppFrame, ReciprocityMark, etc.)
│
└── app/                        # Page assembly & routing (Next.js App Router)
```

---

## 2. Strict Dependency Direction

The dependency flow is strictly unidirectional:

```text
[ app/ (Page Assembly) ]
       │            │
       ▼            ▼
[ components/ (Pure UI) ]
       │
       ▼
[ model/<module> (Domain Module Root) ]
       │
       ▼
[ lib/ (Generic Infrastructure) ]
```

### Dependency Invariants:
1. **`lib/` is strictly business-agnostic**:
   - Contains only generic infrastructure and utilities.
   - Must **NEVER** import from `@/model`, `@/components`, or `@/app`.
   - Must **NEVER** contain domain entity types, business endpoints, or mock datasets.
2. **`components/` is pure UI**:
   - Responsible only for rendering and UI interactions; does not own network communication.
   - May import from `@/model/<module>` and `@/lib`.
   - Must **NEVER** reach into internal files of model modules (e.g., `@/model/*/*`).
3. **`model/` owns data & domain logic**:
   - Manages API communication, domain types, entities, and mock data.
   - Must **NEVER** import from `@/components` or `@/app` (completely agnostic of UI/DOM).
   - Must **NEVER** provide a global barrel export (`src/model/index.ts` does not exist).
4. **Unidirectional UI-Model dependency**:
   - `components -> model` is permitted.
   - `model -> components` is **strictly forbidden**.

---

## 3. Model Layer Decomposition & Naming Conventions

### Principle 1: Decompose by Domain Modules, Not Global Layers
- ❌ **Forbidden**: Top-level global layer directories such as `model/types/`, `model/api/`, `model/mock/`.
- ✅ **Required**: Modular decomposition by domain, e.g., `model/auth/`, `model/portrait/`, `model/match/`, `model/exchange/`.

### Principle 2: Suffix-Based File Naming (`XXX.type.ts`, `XXX.api.ts`, `XXX.mock.ts`)
- ❌ **Forbidden**: Generic file names like `type.ts`, `api.ts`, `mock.ts`.
- ✅ **Required**: Specific entity/feature prefix with role suffix:
  - `ticket.type.ts`, `ticket.api.ts`, `ticket.mock.ts`
  - `session.type.ts`, `session.api.ts`
  - `message.type.ts`, `message.api.ts`, `message.mock.ts`

### Principle 3: Avoid Redundant Module Names in Files
- ❌ **Forbidden**: Redundant prefix matching the parent module name, e.g., `match/match-ticket.ts`, `exchange/exchange-session.ts`.
- ✅ **Required**: Concise, distinct entity names within the module, e.g., `match/ticket.type.ts`, `exchange/session.type.ts`.

### Principle 4: Granular Entity Decomposition
Modules must not lump unrelated concepts together:
- `auth/`: Handles only business-agnostic authentication functions (e.g., OAuth URL).
- `portrait/`: Dedicated module for user capabilities, evidence sources, strengths, and user card profiles.
- `exchange/`: Distinctly decomposed into session lifecycle (`session.*`) and message communication (`message.*`).
- `match/`: Encapsulates match ticket requirements and conditions (`ticket.*`).
- For non-decomposable shared concepts, reflect the exact entity (e.g., `common/api-response.type.ts`).

### Principle 5: Priority of Type Definitions
All types required by the Model layer must be defined within the Model layer itself. Never import types from UI components.

---

## 4. Module `index.ts` Encapsulation Rules

Each domain module entry (`model/<module>/index.ts`) serves as an encapsulation boundary for that module:

1. **Pure Re-exports Only (No `import` statements)**:
   - ❌ **Forbidden**: Importing sub-files to construct or merge synthetic objects:
     ```ts
     // ❌ FORBIDDEN: Do not assemble composite objects in index.ts
     import { sessionApi } from "./session.api";
     import { messageApi } from "./message.api";
     export const exchangeApi = { ...sessionApi, ...messageApi };
     ```
   - ✅ **Required**: Pure `export` statements only:
     ```ts
     // ✅ CORRECT: Pure explicit exports
     export { demoMessages } from "./message.mock";
     export type { ExchangeMessage } from "./message.type";
     ```
2. **Minimal Exposure**:
   - Only export what is actually consumed by external callers. Internal-only helpers or unneeded artifacts must remain unexported.
3. **Module Root Imports for External Consumers**:
   - External callers (components, app pages) must import from the module root:
     ```ts
     import { demoMatch } from "@/model/match";
     import { demoUser } from "@/model/portrait";
     ```
   - Deep imports into module internals (e.g., `@/model/match/ticket.mock`) are prohibited.

---

## 5. Automated Lint Enforcement

These architectural boundaries are statically enforced via `oxlint` in `frontend/.oxlintrc.json`:

1. **Model layer isolation**:
   - `src/model/**` triggers an error if importing from `@/components` or `@/app`.
2. **Lib layer purity**:
   - `src/lib/**` triggers an error if importing from `@/model`, `@/components`, or `@/app`.
3. **Module internal protection**:
   - `src/components/**` and `src/app/**` trigger an error if importing from `@/model/*/*` or deeper subpaths.
