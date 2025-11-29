# IF AI Buddy TUI Design Overview

## Layout Goals
- **Stage: Two-column, fixed left, tabbed right**: Dynamic TUI Textual framing, left column streams the vanilla transcript from the dFrotz engine; right column hosts AI companion commentary, guidance.
- **Persistent Integrated Status/Command/Pallette Footer**: Integrated horizontal band that combines player input with a compact status dashboard.
- **Clear top/bottom framing**: default `Header`/`Footer` widgets remain for title + key bindings, but the core experience lives between them.

## Main Stage
| Region | Purpose | Widgets/Notes |
| --- | --- | --- |
| Left column | Raw game transcript (command echo + engine output) | Scrollable log (Textual `Log`/`RichLog`), monospaced font, light divider |
| Right column | AI buddy narration 

### Optional tabs (not to be implemented yet)
| Items tree | Top-levels: Player Inventory, World, Destroyed | kepps track of discovered items tracking last / current location or used/destroyed/inaccesible state
| Visited Rooms list | List of visited rooms sorted by recency and the action 'verb' that moved the player from the previous room
| Achievements list | List of inferred completed significant game milestones
| Todo List | list of inferred / suggested meta-actions the buddy suggests the player to tackle
| Log file viewer | optional low-level game log viewer. Some are json should use a simplified json viewer.


Additional UI notes:
- Add subtle `Rule` between columns.
- Allow right column to switch between “Narration” and the other tabs

## Footer Strip (Input + Status + Palette)
Single horizontal, partitioned container 
1. **Command Input**
   - Textual `Input` widget, always focused after actions.
   - Placeholder text changes depending on mode (normal game input vs. game system input ).
2. **Status Bar**
   - Composite of mini-panels showing:
     - Player (clickable) – triggers player rename/game restart workflow.
     - Room – latest heading parsed from transcript.
     - Moves / Score – parsed every turn.
     - Engine status – Ready / Busy / Error from REST interactions.
     - AI status – Idle / Working / Error based on narration lifecycle.
     - Palette stub – placeholder for future color/theme picker (`^P palette`).
   - Each widget carries semantic color classes: `status-ok` (green), `status-busy` (blue), `status-error` (red).

## Additional Status Update Rules
- **Engine status**: Busy when awaiting REST response; Ready after success; Error on REST failure.
- **AI status**: Working when narration requested; Ready when narration returns; Idle when no narration; Error if LLM call fails.
- **Palette**: Integrated, categorized List of game system actions like quit game plus general verbs like look, inventory, etc.
- **Player name**: button label updates after rename flow; clicking prompts for new name and restarts session.

## Future Enhancements
- **Optional Tabs**: We will only scaffold/placeholders for the optional tabs, but we will implement the UI element even if initially empty(ie. Tree UI widget)
- **Docked side panels**: Inventory, map, quest goals via `Tabs` or `ContentSwitcher`.
- **Collapsible overlays**: help/about, command palette, AI personality tweaks.
- **Theme picker**: connect “Palette” status cell to quick theme cycling.
- **Diagnostics panel**: optional `Log` or `DataTable` showcasing latency, RU cost, etc.

This document captures the structural and behavioral design requirements so implementation can iterate without losing the UX vision.
