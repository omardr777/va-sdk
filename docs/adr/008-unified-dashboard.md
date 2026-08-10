# ADR-008: Unified Dashboard (Dataset Studio + Voice Playground)

**Status:** Accepted  
**Date:** 2026-08-10

## Context

The frontend needs to serve two purposes: managing datasets and testing voice
tools. Separate tools vs. a unified dashboard.

## Decision

**Single React dashboard with two pages.** Left sidebar navigation between
Dataset Studio and Voice Playground. A persistent floating voice assistant
FAB is available on both pages.

## Rationale

1. **Workflow adjacency.** After generating a dataset, the developer tests it
   in the playground. Switching tabs is faster than switching apps.
2. **Shared components.** Auth setup, tool catalog, conversation log — reused
   across both pages.
3. **MVP scope.** Two pages in one app is cheaper to build and maintain than
   two separate apps.

## Consequences

- React 19 + Vite 8 + Tailwind CSS 4 (same as current VoiceTeller frontend).
- `@va-sdk/react` is a separate package — the floating FAB widget extracted
  for embedding into developer apps. The dashboard uses this widget
  internally as a reference implementation.
- Voice playground talks to a locally-running `va-sdk serve` instance.
